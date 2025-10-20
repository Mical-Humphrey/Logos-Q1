"""Main orchestration loop for live trading."""

from __future__ import annotations

import datetime as dt
import logging
import textwrap
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional

from logos.logging_setup import attach_live_runtime_handler, detach_handler

from .broker_base import BrokerAdapter, OrderIntent, OrderState
from .data_feed import Bar, DataFeed, FetchError
from .report import append_account, append_order, append_position, append_trade, write_session_summary
from .risk import RiskContext, RiskLimits, check_circuit_breakers, check_order_limits, compute_drawdown_bps
from .session_manager import SessionPaths
from .state import append_event, load_state, save_state
from .time import TimeProvider, SystemTimeProvider
from logos.paths import RUNS_LIVE_TRADES_DIR

logger = logging.getLogger(__name__)


@dataclass
class LoopConfig:
    symbol: str
    strategy: str
    interval: str
    kill_switch_file: Optional[str] = None
    max_loops: Optional[int] = None


OrderGenerator = Callable[[List[Bar], float], Iterable[OrderIntent]]


class LiveRunner:
    """Coordinates the data feed, broker, and risk layers."""

    def __init__(
        self,
        broker: BrokerAdapter,
        feed: DataFeed,
        order_generator: OrderGenerator,
        session: SessionPaths,
        risk_limits: RiskLimits,
        time_provider: TimeProvider | None = None,
        loop_config: LoopConfig | None = None,
    ) -> None:
        self.broker = broker
        self.feed = feed
        self.order_generator = order_generator
        self.session = session
        self.risk_limits = risk_limits
        self.time_provider = time_provider or SystemTimeProvider()
        self.loop_config = loop_config or LoopConfig(symbol="UNKNOWN", strategy="UNKNOWN", interval="1m")
        self._state = load_state(session.state_file, session.session_id)
        if getattr(self.broker, "bootstrap_positions", None) and self._state.positions:
            try:
                self.broker.bootstrap_positions(self._state.positions)  # type: ignore[attr-defined]
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning("Failed to bootstrap positions into broker: %s", exc)
        self._starting_equity: Optional[float] = None
        self._live_log_handler = attach_live_runtime_handler()
        self._stopped = False
        self._halt_reason = "completed"
        self._started_at: Optional[dt.datetime] = None
        self._stopped_at: Optional[dt.datetime] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(self) -> None:
        logger.info("Starting live runner for %s/%s", self.loop_config.symbol, self.loop_config.strategy)
        loops = 0
        last_bar_dt = None
        if self._state.last_bar_iso:
            last_bar_dt = dt.datetime.fromisoformat(self._state.last_bar_iso)
        while not self._stopped:
            if self.loop_config.max_loops is not None and loops >= self.loop_config.max_loops:
                self._halt_reason = "max_loops_reached"
                break
            now = self.time_provider.utc_now()
            if self._started_at is None:
                self._started_at = now
            account_snapshot = self.broker.get_account()
            if self._starting_equity is None:
                self._starting_equity = account_snapshot.equity
            if self._state.equity <= 0:
                self._state.equity = account_snapshot.equity
            if self._state.peak_equity < account_snapshot.equity:
                self._state.peak_equity = account_snapshot.equity
            positions = self.broker.get_positions()
            position_qty = next((pos.quantity for pos in positions if pos.symbol == self.loop_config.symbol), 0.0)
            last_ts = (last_bar_dt or now).timestamp()
            risk_ctx = RiskContext(
                equity=account_snapshot.equity,
                position_quantity=position_qty,
                realized_drawdown_bps=compute_drawdown_bps(
                    account_snapshot.equity,
                    self._state.peak_equity or account_snapshot.equity,
                ),
                consecutive_rejects=self._state.consecutive_rejects,
                last_bar_ts=last_ts,
                now_ts=now.timestamp(),
            )
            decision = check_circuit_breakers(self.risk_limits, risk_ctx)
            if not decision.allowed:
                logger.warning("Halting loop due to circuit breaker: %s", decision.reason)
                self._halt_reason = decision.reason
                append_event(
                    {
                        "type": "circuit_breaker",
                        "reason": decision.reason,
                        "ts": now.timestamp(),
                        "equity": account_snapshot.equity,
                        "position": position_qty,
                    },
                    self.session.state_events_file,
                )
                self._state.equity = account_snapshot.equity
                self._state.positions[self.loop_config.symbol] = {
                    "qty": position_qty,
                    "avg_price": next((pos.avg_price for pos in positions if pos.symbol == self.loop_config.symbol), 0.0),
                    "unrealized": next((pos.unrealized_pnl for pos in positions if pos.symbol == self.loop_config.symbol), 0.0),
                }
                self._persist_state()
                break
            try:
                bars = self.feed.fetch_bars(self.loop_config.symbol, self.loop_config.interval, last_bar_dt)
            except FetchError as exc:
                logger.error("Data feed failure: %s", exc)
                append_event({"type": "feed_error", "reason": str(exc)}, self.session.state_events_file)
                self._halt_reason = "feed_error"
                break
            if not bars:
                logger.debug("No new bars for %s", self.loop_config.symbol)
                if self._halt_reason == "completed":
                    self._halt_reason = "no_new_bars"
                break
            for bar in bars:
                self._process_bar(bar)
                last_bar_dt = bar.dt
            self._state.last_bar_iso = last_bar_dt.isoformat() if last_bar_dt else None
            self._persist_state()
            loops += 1
        detach_handler(self._live_log_handler)
        self._stopped_at = self.time_provider.utc_now()
        summary = textwrap.dedent(
            f"""
            # Session {self.session.session_id}

            ## Metadata
            - Symbol: {self.loop_config.symbol}
            - Strategy: {self.loop_config.strategy}
            - Started: {(self._started_at or self._stopped_at).isoformat()}
            - Stopped: {self._stopped_at.isoformat()}
            - Halt Reason: {self._halt_reason}

            ## Metrics
            - Final Equity: {self._state.equity:.2f}
            - Peak Equity: {self._state.peak_equity:.2f}
            - Realized PnL: {self._state.realized_pnl:.2f}
            - Drawdown (bps): {compute_drawdown_bps(self._state.equity, self._state.peak_equity or self._state.equity):.0f}
            """
        ).strip()
        write_session_summary(self.session.session_report, summary)
        logger.info("Live runner stopped")

    def stop(self) -> None:
        if self._halt_reason == "completed":
            self._halt_reason = "stop_requested"
        self._stopped = True

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _process_bar(self, bar: Bar) -> None:
        ts = bar.dt.timestamp()
        self.broker.on_market_data(bar.symbol, bar.close, ts)
        broker_positions = {pos.symbol: pos.quantity for pos in self.broker.get_positions()}
        position_qty = broker_positions.get(bar.symbol, 0.0)
        intents = list(self.order_generator([bar], position_qty))
        order_map = {}
        account = self.broker.get_account()
        if self._starting_equity is None:
            self._starting_equity = account.equity
        for intent in intents:
            signed_qty = intent.quantity if intent.side == "buy" else -intent.quantity
            ctx = RiskContext(
                equity=account.equity,
                position_quantity=position_qty,
                realized_drawdown_bps=compute_drawdown_bps(self._state.equity or account.equity, self._state.peak_equity or account.equity),
                consecutive_rejects=self._state.consecutive_rejects,
                last_bar_ts=bar.dt.timestamp(),
                now_ts=ts,
            )
            decision = check_order_limits(self.loop_config.symbol, signed_qty, bar.close, self.risk_limits, ctx)
            if not decision.allowed:
                logger.warning("Order rejected by risk: %s", decision.reason)
                self._state.consecutive_rejects += 1
                append_event({"type": "order_reject", "reason": decision.reason, "ts": ts}, self.session.state_events_file)
                continue
            try:
                order = self.broker.place_order(intent)
            except Exception as exc:  # pragma: no cover - guardrail
                logger.exception("Order placement failed: %s", exc)
                self._state.consecutive_rejects += 1
                continue
            order_map[order.order_id] = order
            self._state.open_orders[order.order_id] = {
                "symbol": order.intent.symbol,
                "side": order.intent.side,
                "qty": order.intent.quantity,
                "state": order.state.value,
            }
            append_order(
                self.session.orders_file,
                ts=bar.dt,
                session_id=self.session.session_id,
                id=order.order_id,
                symbol=order.intent.symbol,
                strategy=self.loop_config.strategy,
                side=order.intent.side,
                order_type=order.intent.order_type,
                qty=order.intent.quantity,
                limit_price=order.intent.limit_price,
                state=order.state.value,
                reject_reason=order.reject_reason,
                broker_order_id=order.broker_order_id,
            )
            if order.state == OrderState.REJECTED:
                self._state.consecutive_rejects += 1
            else:
                self._state.consecutive_rejects = 0
            if order.state in {OrderState.FILLED, OrderState.CANCELED, OrderState.REJECTED}:
                self._state.open_orders.pop(order.order_id, None)
        for fill in self.broker.poll_fills():
            linked_order = order_map.get(fill.order_id)
            order_type = linked_order.intent.order_type if linked_order else "market"
            side = linked_order.intent.side if linked_order else "buy"
            self._state.open_orders.pop(fill.order_id, None)
            append_trade(
                self.session.trades_file,
                ts=dt.datetime.fromtimestamp(fill.ts, tz=dt.timezone.utc),
                id=fill.fill_id,
                session_id=self.session.session_id,
                symbol=bar.symbol,
                strategy=self.loop_config.strategy,
                side=side,
                qty=fill.quantity,
                price=fill.price,
                fees=fill.fees,
                slip_bps=fill.slip_bps,
                order_type=order_type,
            )
            daily_trade_path = RUNS_LIVE_TRADES_DIR / f"{bar.symbol}_{dt.datetime.fromtimestamp(fill.ts, tz=dt.timezone.utc).strftime('%Y%m%d')}.csv"
            append_trade(
                daily_trade_path,
                ts=dt.datetime.fromtimestamp(fill.ts, tz=dt.timezone.utc),
                id=fill.fill_id,
                session_id=self.session.session_id,
                symbol=bar.symbol,
                strategy=self.loop_config.strategy,
                side=side,
                qty=fill.quantity,
                price=fill.price,
                fees=fill.fees,
                slip_bps=fill.slip_bps,
                order_type=order_type,
            )
        self._update_state_from_broker(bar)

    def _update_state_from_broker(self, bar: Bar) -> None:
        account = self.broker.get_account()
        positions = self.broker.get_positions()
        pos_dict = {}
        for pos in positions:
            pos_dict[pos.symbol] = {"qty": pos.quantity, "avg_price": pos.avg_price, "unrealized": pos.unrealized_pnl}
            append_position(
                self.session.positions_file,
                ts=dt.datetime.fromtimestamp(account.ts, tz=dt.timezone.utc),
                session_id=self.session.session_id,
                symbol=pos.symbol,
                strategy=self.loop_config.strategy,
                qty=pos.quantity,
                avg_price=pos.avg_price,
                unrealized_pnl=pos.unrealized_pnl,
            )
        append_account(
            self.session.account_file,
            ts=dt.datetime.fromtimestamp(account.ts, tz=dt.timezone.utc),
            session_id=self.session.session_id,
            symbol=self.loop_config.symbol,
            strategy=self.loop_config.strategy,
            cash=account.cash,
            equity=account.equity,
            buying_power=account.buying_power,
            currency=account.currency,
        )
        self._state.positions = pos_dict
        self._state.equity = account.equity
        if self._state.peak_equity < account.equity:
            self._state.peak_equity = account.equity
        if self._starting_equity is not None:
            self._state.realized_pnl = account.equity - self._starting_equity

    def _persist_state(self) -> None:
        save_state(self._state, self.session.state_file)
        append_event({"type": "state", "equity": self._state.equity}, self.session.state_events_file)

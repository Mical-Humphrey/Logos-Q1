"""Main orchestration loop for live trading."""

from __future__ import annotations

import datetime as dt
import json
import logging
import textwrap
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional

from logos.logging_setup import attach_live_runtime_handler, detach_handler
from logos.window import Window
from logos.orchestrator import (
    MetricsRecorder,
    OrderRouter,
    OrderRequest,
    FillReport,
    Scheduler,
    StrategySpec as OrchestratorStrategySpec,
)

from .broker_base import BrokerAdapter, OrderIntent, OrderState
from .data_feed import Bar, DataFeed, FetchError
from .report import (
    append_account,
    append_order,
    append_position,
    append_trade,
    write_session_summary,
)
from .risk import (
    RiskContext,
    RiskLimits,
    check_circuit_breakers,
    check_order_limits,
    compute_drawdown_bps,
)
from .session_manager import SessionPaths
from .state import append_event, load_state, save_state
from .time import TimeProvider, SystemTimeProvider, interval_to_timedelta
from logos.paths import RUNS_LIVE_TRADES_DIR
from logos.portfolio.capacity import compute_adv_notional, compute_participation

logger = logging.getLogger(__name__)


@dataclass
class LoopConfig:
    symbol: str
    strategy: str
    interval: str
    window: Window
    kill_switch_file: Optional[str] = None
    max_loops: Optional[int] = None
    orchestrator_time_budget_fraction: float = 0.25
    orchestrator_jitter_seconds: float = 0.0
    orchestrator_router_rate_limit: int = 5
    orchestrator_router_max_inflight: int = 256
    orchestrator_metrics_window: int = 512
    orchestrator_snapshot_interval_s: int = 30
    orchestrator_scheduler_seed: Optional[int] = None


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
        if loop_config is None:
            raise ValueError("LiveRunner requires loop_config with window")
        self.loop_config = loop_config
        self._window = loop_config.window
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
        self._marks: Dict[str, float] = {}
        self._volume_history: Dict[str, deque[float]] = {}
        self._current_day: Optional[dt.date] = None
        self._day_open_equity: float = 0.0
        self._daily_turnover: float = 0.0
        self._strategy_daily_loss: Dict[str, float] = {}
        self._cooldown_days_remaining: int = 0
        self._strategy_name = self.loop_config.strategy
        self._cadence = interval_to_timedelta(self.loop_config.interval)
        budget_fraction = max(0.01, self.loop_config.orchestrator_time_budget_fraction)
        self._time_budget = max(
            dt.timedelta(milliseconds=50), self._cadence * budget_fraction
        )
        jitter_seconds = max(0.0, self.loop_config.orchestrator_jitter_seconds)
        jitter_seconds = min(jitter_seconds, self._cadence.total_seconds())
        jitter = dt.timedelta(seconds=jitter_seconds)
        window_start_utc = self._window.start.tz_convert("UTC").to_pydatetime()
        self._logical_time = window_start_utc
        self._scheduler = Scheduler(
            now=window_start_utc,
            seed=self.loop_config.orchestrator_scheduler_seed,
        )
        orchestrator_spec = OrchestratorStrategySpec(
            name=self._strategy_name,
            cadence=self._cadence,
            time_budget=self._time_budget,
            jitter=jitter,
            heartbeat_timeout=self._cadence * 3,
        )
        self._scheduler.register(orchestrator_spec, start_at=window_start_utc)
        metrics_window = max(8, int(self.loop_config.orchestrator_metrics_window))
        self._metrics = MetricsRecorder(window=metrics_window)
        self._router = OrderRouter(
            rate_limit_per_sec=max(
                1, int(self.loop_config.orchestrator_router_rate_limit)
            ),
            max_inflight=max(1, int(self.loop_config.orchestrator_router_max_inflight)),
        )
        self._metrics_file = self.session.orchestrator_metrics_file
        self._router_state_file = self.session.router_state_file
        snapshot_seconds = max(
            0, int(self.loop_config.orchestrator_snapshot_interval_s)
        )
        self._router_snapshot_interval = dt.timedelta(seconds=snapshot_seconds)
        self._last_router_snapshot_at: Optional[dt.datetime] = None
        self._pending_skip = False
        self._iteration_start_logical: Optional[dt.datetime] = None
        self._iteration_queue_depth = 0
        self._client_seq = 0
        self._last_bar_dt: Optional[dt.datetime] = None
        if self._state.last_bar_iso:
            try:
                self._last_bar_dt = dt.datetime.fromisoformat(self._state.last_bar_iso)
            except ValueError:  # pragma: no cover - defensive
                logger.warning(
                    "Invalid last_bar_iso in state: %s", self._state.last_bar_iso
                )
                self._last_bar_dt = None
        self._load_router_snapshot()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(self) -> None:
        logger.info(
            "Starting live runner for %s/%s",
            self.loop_config.symbol,
            self.loop_config.strategy,
        )
        window_start_dt = self._window.start.tz_convert("UTC").to_pydatetime()
        window_end_dt = self._window.end.tz_convert("UTC").to_pydatetime()
        loops = 0
        while not self._stopped:
            if (
                self.loop_config.max_loops is not None
                and loops >= self.loop_config.max_loops
            ):
                self._halt_reason = "max_loops_reached"
                break
            if not self._acquire_slot():
                continue
            iteration_start_wall = dt.datetime.now(dt.timezone.utc)
            should_continue = True
            try:
                should_continue = self._run_iteration(window_start_dt, window_end_dt)
                if should_continue:
                    loops += 1
            finally:
                iteration_end_wall = dt.datetime.now(dt.timezone.utc)
                self._complete_slot(iteration_start_wall, iteration_end_wall)
            if not should_continue:
                break
        detach_handler(self._live_log_handler)
        self._stopped_at = self.time_provider.utc_now()
        self._persist_router_state()
        self._emit_metrics(self._stopped_at or dt.datetime.now(dt.timezone.utc))
        orchestrator_snapshot = self._metrics.snapshot(
            timestamp=self._stopped_at or dt.datetime.now(dt.timezone.utc)
        )
        summary = textwrap.dedent(
            f"""
            # Session {self.session.session_id}

            ## Metadata
            - Symbol: {self.loop_config.symbol}
            - Strategy: {self.loop_config.strategy}
            - Window: {self._window.start.isoformat()} → {self._window.end.isoformat()}
            - Started: {(self._started_at or self._stopped_at).isoformat()}
            - Stopped: {self._stopped_at.isoformat()}
            - Halt Reason: {self._halt_reason}

            ## Metrics
            - Final Equity: {self._state.equity:.2f}
            - Peak Equity: {self._state.peak_equity:.2f}
            - Realized PnL: {self._state.realized_pnl:.2f}
            - Drawdown (bps): {compute_drawdown_bps(self._state.equity, self._state.peak_equity or self._state.equity):.0f}
            - Orchestrator p95 Latency (s): {orchestrator_snapshot['p95_latency_s']:.3f}
            - Orchestrator Skip Rate: {orchestrator_snapshot['skip_rate']:.3%}
            """
        ).strip()
        write_session_summary(self.session.session_report, summary)
        logger.info("Live runner stopped")

    def _acquire_slot(self) -> bool:
        strategy = self._strategy_name
        next_run_at = self._scheduler.next_run(strategy)
        if self._logical_time < next_run_at:
            self._logical_time = next_run_at
        due = self._scheduler.due(self._logical_time)
        queue_depth = len(due)
        self._iteration_queue_depth = queue_depth
        self._metrics.record_queue_depth(queue_depth)
        if strategy not in due:
            if self._pending_skip:
                self._metrics.record_tick(strategy, latency_s=0.0, skipped=True)
                self._pending_skip = False
                self._emit_metrics(self._logical_time)
            self._logical_time += self._cadence
            return False
        self._iteration_start_logical = self._logical_time
        self._scheduler.mark_start(strategy, self._logical_time)
        return True

    def _run_iteration(
        self, window_start_dt: dt.datetime, window_end_dt: dt.datetime
    ) -> bool:
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
        position_qty = next(
            (
                pos.quantity
                for pos in positions
                if pos.symbol == self.loop_config.symbol
            ),
            0.0,
        )
        last_ts = (self._last_bar_dt or now).timestamp()
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
                "avg_price": next(
                    (
                        pos.avg_price
                        for pos in positions
                        if pos.symbol == self.loop_config.symbol
                    ),
                    0.0,
                ),
                "unrealized": next(
                    (
                        pos.unrealized_pnl
                        for pos in positions
                        if pos.symbol == self.loop_config.symbol
                    ),
                    0.0,
                ),
            }
            self._persist_state()
            return False
        try:
            bars = self.feed.fetch_bars(
                self.loop_config.symbol, self.loop_config.interval, self._last_bar_dt
            )
        except FetchError as exc:
            logger.error("Data feed failure: %s", exc)
            append_event(
                {"type": "feed_error", "reason": str(exc)},
                self.session.state_events_file,
            )
            self._halt_reason = "feed_error"
            return False
        filtered: list[Bar] = []
        for bar in bars:
            if bar.dt < window_start_dt:
                continue
            if bar.dt >= window_end_dt:
                self._halt_reason = "window_complete"
                self._stopped = True
                break
            filtered.append(bar)
        bars = filtered
        if not bars:
            logger.debug("No new bars for %s", self.loop_config.symbol)
            if self._halt_reason == "completed":
                self._halt_reason = "no_new_bars"
            return False
        for bar in bars:
            self._process_bar(bar)
            self._last_bar_dt = bar.dt
            if self._stopped:
                break
        if self._stopped:
            return False
        self._state.last_bar_iso = (
            self._last_bar_dt.isoformat() if self._last_bar_dt else None
        )
        self._persist_state()
        return True

    def _complete_slot(self, start_wall: dt.datetime, end_wall: dt.datetime) -> None:
        if self._iteration_start_logical is None:
            return
        runtime_seconds = max(0.0, (end_wall - start_wall).total_seconds())
        finish_time = self._iteration_start_logical + dt.timedelta(
            seconds=runtime_seconds
        )
        strategy = self._strategy_name
        self._scheduler.mark_finish(strategy, finish_time)
        self._scheduler.record_heartbeat(strategy, finish_time)
        over_budget = runtime_seconds > self._time_budget.total_seconds()
        self._pending_skip = over_budget
        self._metrics.record_tick(
            strategy,
            latency_s=runtime_seconds,
            skipped=over_budget,
        )
        self._emit_metrics(finish_time)
        self._maybe_snapshot_router(end_wall)
        self._logical_time += self._cadence
        self._iteration_start_logical = None

    def _emit_metrics(self, timestamp: dt.datetime) -> None:
        if not self._metrics_file:
            return
        snapshot = self._metrics.snapshot(timestamp=timestamp)
        try:
            with self._metrics_file.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(snapshot) + "\n")
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to write orchestrator metrics: %s", exc)

    def _maybe_snapshot_router(self, when: dt.datetime) -> None:
        if self._router_snapshot_interval.total_seconds() <= 0:
            return
        if (
            self._last_router_snapshot_at is not None
            and (when - self._last_router_snapshot_at) < self._router_snapshot_interval
        ):
            return
        try:
            self._router.save(self._router_state_file)
            self._last_router_snapshot_at = when
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to persist router snapshot: %s", exc)

    def _persist_router_state(self) -> None:
        try:
            self._router.save(self._router_state_file)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to persist router snapshot: %s", exc)

    def _load_router_snapshot(self) -> None:
        if not self._router_state_file.exists():
            return
        try:
            restored = OrderRouter.load(self._router_state_file)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Unable to restore router snapshot: %s", exc)
            return
        snapshot = restored.snapshot()
        if (
            snapshot.rate_limit_per_sec
            != self.loop_config.orchestrator_router_rate_limit
        ):
            logger.warning(
                "Router snapshot rate limit mismatch; ignoring persisted state"
            )
            return
        if snapshot.max_inflight != self.loop_config.orchestrator_router_max_inflight:
            logger.warning(
                "Router snapshot inflight limit mismatch; ignoring persisted state"
            )
            return
        self._router = restored
        self._last_router_snapshot_at = dt.datetime.now(dt.timezone.utc)

    def _reconcile_router(self, reports: List[FillReport]) -> None:
        if not reports:
            return
        result = self._router.reconcile(reports)
        if result.unknown_fills:
            logger.error("Router halted due to unknown fills: %s", result.unknown_fills)
        if self._router.halted():
            self._metrics.record_error("router_halted")
            self._halt_reason = "router_halted"
            self._stopped = True

    def _build_router_request(
        self, intent: OrderIntent, bar: Bar, client_id: str
    ) -> OrderRequest:
        price = intent.limit_price if intent.limit_price is not None else bar.close
        signed_qty = intent.quantity if intent.side == "buy" else -intent.quantity
        timestamp = self._iteration_start_logical or dt.datetime.now(dt.timezone.utc)
        return OrderRequest(
            strategy_id=self._strategy_name,
            symbol=intent.symbol,
            quantity=signed_qty,
            price=price,
            client_order_id=client_id,
            idempotency_key=f"{self._strategy_name}:{client_id}",
            timestamp=timestamp,
        )

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
        self._record_volume(bar)
        self._marks[bar.symbol] = bar.close
        account = self.broker.get_account()
        if self._starting_equity is None:
            self._starting_equity = account.equity
        self._update_day_metrics(bar.dt.date(), account.equity)

        positions = self.broker.get_positions()
        broker_positions = {pos.symbol: pos.quantity for pos in positions}
        position_qty = broker_positions.get(bar.symbol, 0.0)
        intents = list(self.order_generator([bar], position_qty))
        order_map = {}
        router_reports: List[FillReport] = []

        nav = account.equity
        asset_class_map = self.risk_limits.symbol_asset_class
        default_class = self.risk_limits.default_asset_class
        class_exposures = defaultdict(float)
        asset_exposures: Dict[str, float] = {}
        gross_exposure = 0.0
        for pos in positions:
            price = self._marks.get(pos.symbol)
            if not price or price <= 0.0:
                price = pos.avg_price if pos.avg_price > 0.0 else bar.close
            if nav <= 0.0 or price <= 0.0:
                exposure = 0.0
            else:
                exposure = abs(pos.quantity * price) / nav
            asset_exposures[pos.symbol] = exposure
            asset_class = asset_class_map.get(pos.symbol, default_class).lower()
            class_exposures[asset_class] += exposure
            gross_exposure += exposure

        symbol_class = asset_class_map.get(bar.symbol, default_class).lower()
        current_symbol_exposure = asset_exposures.get(bar.symbol, 0.0)
        current_class_exposure = class_exposures.get(symbol_class, 0.0)
        history = self._volume_history.get(bar.symbol, ())
        adv_notional = compute_adv_notional(history)

        peak_equity = self._state.peak_equity or account.equity
        if account.equity > peak_equity:
            peak_equity = account.equity
        portfolio_drawdown = (
            0.0 if peak_equity <= 0.0 else (peak_equity - account.equity) / peak_equity
        )
        if (
            self.risk_limits.portfolio_drawdown_cap > 0.0
            and portfolio_drawdown >= self.risk_limits.portfolio_drawdown_cap
            and self._cooldown_days_remaining == 0
        ):
            self._cooldown_days_remaining = self.risk_limits.cooldown_days

        daily_portfolio_loss = (
            0.0
            if self._day_open_equity <= 0.0
            else (account.equity - self._day_open_equity) / self._day_open_equity
        )
        gross_turnover = self._daily_turnover

        for intent in intents:
            cooldown_active = self._cooldown_days_remaining > 0
            signed_qty = intent.quantity if intent.side == "buy" else -intent.quantity
            current_qty = position_qty
            projected_qty = current_qty + signed_qty
            price = bar.close
            order_notional = abs(signed_qty * price)
            projected_symbol_exposure = (
                0.0 if nav <= 0.0 else abs(projected_qty * price) / nav
            )
            projected_class_exposure = (
                current_class_exposure
                - current_symbol_exposure
                + projected_symbol_exposure
            )
            projected_gross_exposure = (
                gross_exposure - current_symbol_exposure + projected_symbol_exposure
            )
            delta_symbol_exposure = projected_symbol_exposure - current_symbol_exposure
            delta_class_exposure = projected_class_exposure - current_class_exposure
            delta_gross_exposure = projected_gross_exposure - gross_exposure
            reducing = projected_symbol_exposure <= current_symbol_exposure + 1e-9
            order_turnover = order_notional / nav if nav > 0.0 else 0.0
            projected_turnover = gross_turnover + order_turnover
            participation = compute_participation(order_notional, adv_notional)

            strategy_losses = dict(self._strategy_daily_loss)
            ctx = RiskContext(
                equity=account.equity,
                position_quantity=current_qty,
                realized_drawdown_bps=compute_drawdown_bps(
                    self._state.equity or account.equity,
                    self._state.peak_equity or account.equity,
                ),
                consecutive_rejects=self._state.consecutive_rejects,
                last_bar_ts=bar.dt.timestamp(),
                now_ts=ts,
                order_notional=order_notional,
                gross_exposure=gross_exposure,
                projected_gross_exposure=projected_gross_exposure,
                delta_gross_exposure=delta_gross_exposure,
                symbol_exposure=current_symbol_exposure,
                projected_symbol_exposure=projected_symbol_exposure,
                delta_symbol_exposure=delta_symbol_exposure,
                asset_class=symbol_class,
                class_exposure=current_class_exposure,
                projected_class_exposure=projected_class_exposure,
                delta_class_exposure=delta_class_exposure,
                portfolio_drawdown=portfolio_drawdown,
                daily_portfolio_loss=daily_portfolio_loss,
                strategy_id=self.loop_config.strategy,
                strategy_daily_losses=strategy_losses,
                cooldown_active=cooldown_active,
                projected_turnover=projected_turnover,
                order_participation=participation,
                adv_notional=adv_notional,
                reducing_risk=reducing,
            )
            decision = check_order_limits(
                bar.symbol, signed_qty, price, self.risk_limits, ctx
            )
            if decision.warnings:
                for warning in decision.warnings:
                    logger.warning(
                        "risk_warning code=%s symbol=%s projected_turnover=%.4f participation=%.4f",
                        warning,
                        bar.symbol,
                        projected_turnover,
                        participation,
                    )
            if not decision.allowed:
                if (
                    decision.reason == "portfolio_drawdown_cap"
                    and self._cooldown_days_remaining == 0
                ):
                    self._cooldown_days_remaining = self.risk_limits.cooldown_days
                logger.warning("Order rejected by risk: %s", decision.reason)
                self._state.consecutive_rejects += 1
                append_event(
                    {"type": "order_reject", "reason": decision.reason, "ts": ts},
                    self.session.state_events_file,
                )
                self._metrics.record_error(decision.reason or "risk_reject")
                continue
            client_id = f"{self._strategy_name}-{self._client_seq:08d}"
            self._client_seq += 1
            request = self._build_router_request(intent, bar, client_id)
            router_decision = self._router.submit(
                request,
                now=self._iteration_start_logical or dt.datetime.now(dt.timezone.utc),
            )
            if not router_decision.accepted:
                reason = router_decision.reason or "router_rejected"
                logger.warning("Router rejected order: %s", reason)
                self._metrics.record_error(reason)
                append_event(
                    {
                        "type": "router_reject",
                        "reason": reason,
                        "strategy": self._strategy_name,
                        "client_order_id": request.client_order_id,
                        "ts": (
                            self._iteration_start_logical
                            or dt.datetime.now(dt.timezone.utc)
                        ).timestamp(),
                    },
                    self.session.state_events_file,
                )
                if reason == "router_halted":
                    self._halt_reason = "router_halted"
                    self._stopped = True
                self._state.consecutive_rejects += 1
                continue
            intent.client_order_id = router_decision.order_id
            try:
                order = self.broker.place_order(intent)
            except Exception as exc:  # pragma: no cover - guardrail
                logger.exception("Order placement failed: %s", exc)
                self._state.consecutive_rejects += 1
                self._metrics.record_error("broker_error")
                router_reports.append(
                    FillReport(
                        order_id=router_decision.order_id,
                        status="rejected",
                        filled_qty=0.0,
                        timestamp=dt.datetime.now(dt.timezone.utc),
                    )
                )
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
                self._metrics.record_error("broker_reject")
            else:
                self._state.consecutive_rejects = 0
                position_qty += signed_qty
                gross_turnover = projected_turnover
                self._daily_turnover = projected_turnover
                current_symbol_exposure = max(projected_symbol_exposure, 0.0)
                current_class_exposure = max(projected_class_exposure, 0.0)
                gross_exposure = max(projected_gross_exposure, 0.0)
                asset_exposures[bar.symbol] = current_symbol_exposure
                class_exposures[symbol_class] = current_class_exposure
            if order.state in {
                OrderState.CANCELED,
                OrderState.REJECTED,
            }:
                self._state.open_orders.pop(order.order_id, None)
                router_reports.append(
                    FillReport(
                        order_id=order.order_id,
                        status=order.state.value,
                        filled_qty=order.filled_qty,
                        timestamp=dt.datetime.now(dt.timezone.utc),
                    )
                )
            elif order.state == OrderState.FILLED:
                self._state.open_orders.pop(order.order_id, None)
        fill_reports: List[FillReport] = []
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
            daily_trade_path = (
                RUNS_LIVE_TRADES_DIR
                / f"{bar.symbol}_{dt.datetime.fromtimestamp(fill.ts, tz=dt.timezone.utc).strftime('%Y%m%d')}.csv"
            )
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
            fill_reports.append(
                FillReport(
                    order_id=fill.order_id,
                    status="filled",
                    filled_qty=fill.quantity,
                    timestamp=dt.datetime.fromtimestamp(fill.ts, tz=dt.timezone.utc),
                )
            )
        self._reconcile_router(router_reports + fill_reports)
        self._update_state_from_broker(bar)

    def _record_volume(self, bar: Bar) -> None:
        lookback = max(1, self.risk_limits.adv_lookback_days or 20)
        history = self._volume_history.get(bar.symbol)
        if history is None or history.maxlen != lookback:
            existing = list(history) if history is not None else []
            history = deque(existing, maxlen=lookback)
            self._volume_history[bar.symbol] = history
        history.append(float(bar.volume * bar.close))

    def _update_day_metrics(self, day: dt.date, equity: float) -> None:
        if self._current_day != day:
            if self._current_day is not None and self._cooldown_days_remaining > 0:
                self._cooldown_days_remaining = max(
                    0, self._cooldown_days_remaining - 1
                )
            self._current_day = day
            self._day_open_equity = equity
            self._daily_turnover = 0.0
            self._strategy_daily_loss = {}
        if self._day_open_equity <= 0.0:
            daily_loss = 0.0
        else:
            daily_loss = (equity - self._day_open_equity) / self._day_open_equity
        self._strategy_daily_loss[self.loop_config.strategy] = daily_loss

    def _update_state_from_broker(self, bar: Bar) -> None:
        account = self.broker.get_account()
        positions = self.broker.get_positions()
        pos_dict = {}
        for pos in positions:
            pos_dict[pos.symbol] = {
                "qty": pos.quantity,
                "avg_price": pos.avg_price,
                "unrealized": pos.unrealized_pnl,
            }
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
        append_event(
            {"type": "state", "equity": self._state.equity},
            self.session.state_events_file,
        )

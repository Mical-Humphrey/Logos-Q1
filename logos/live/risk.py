"""Risk checks enforced before and during live trading."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Mapping, Optional, Tuple

from logos.portfolio.risk import (
    PortfolioDecision,
    PortfolioLimitsConfig,
    PortfolioOrderState,
    evaluate_order_limits,
)

logger = logging.getLogger(__name__)


@dataclass
class RiskLimits:
    """Configuration for pre-trade and circuit-breaker checks."""

    max_notional: float = 0.0
    max_position: float = 0.0
    symbol_position_limits: Dict[str, float] = field(default_factory=dict)
    max_drawdown_bps: float = 0.0
    max_consecutive_rejects: int = 5
    stale_data_threshold_s: float = 300.0
    kill_switch_file: Optional[Path] = None
    portfolio_gross_cap: float = 0.0
    per_asset_cap: float = 0.0
    asset_class_caps: Dict[str, float] = field(default_factory=dict)
    per_trade_risk_cap: float = 0.0
    portfolio_drawdown_cap: float = 0.0
    cooldown_days: int = 0
    daily_portfolio_loss_cap: float = 0.0
    daily_strategy_loss_cap: float = 0.0
    capacity_warn_participation: float = 0.0
    capacity_max_participation: float = 0.0
    adv_lookback_days: int = 20
    turnover_warn: float = 0.0
    turnover_block: float = 0.0
    symbol_asset_class: Dict[str, str] = field(default_factory=dict)
    default_asset_class: str = "equity"
    asset_slippage_bps: Dict[str, float] = field(default_factory=dict)


@dataclass
class RiskContext:
    """Live state needed for the checks."""

    equity: float
    position_quantity: float
    realized_drawdown_bps: float
    consecutive_rejects: int
    last_bar_ts: float
    now_ts: float
    order_notional: float = 0.0
    gross_exposure: float = 0.0
    projected_gross_exposure: float | None = None
    delta_gross_exposure: float = 0.0
    symbol_exposure: float = 0.0
    projected_symbol_exposure: float | None = None
    delta_symbol_exposure: float = 0.0
    asset_class: str = "equity"
    class_exposure: float = 0.0
    projected_class_exposure: float | None = None
    delta_class_exposure: float = 0.0
    portfolio_drawdown: float = 0.0
    daily_portfolio_loss: float = 0.0
    strategy_id: str = ""
    strategy_daily_losses: Dict[str, float] = field(default_factory=dict)
    cooldown_active: bool = False
    projected_turnover: float = 0.0
    order_participation: float = 0.0
    adv_notional: float = 0.0
    reducing_risk: bool = False


@dataclass
class RiskDecision:
    """Structured response returned by the risk layer."""

    allowed: bool
    reason: str = ""
    warnings: Tuple[str, ...] = field(default_factory=tuple)

    def __bool__(self) -> bool:  # pragma: no cover - convenience
        return self.allowed


def _notional(quantity: float, price: float) -> float:
    return abs(quantity * price)


def check_order_limits(
    symbol: str, quantity: float, price: float, limits: RiskLimits, ctx: RiskContext
) -> RiskDecision:
    """Ensure the proposed order respects sizing limits."""

    order_notional = ctx.order_notional or _notional(quantity, price)

    if limits.max_notional > 0 and order_notional > limits.max_notional + 1e-6:
        return RiskDecision(False, "max_notional_exceeded")

    limit = limits.symbol_position_limits.get(symbol, limits.max_position)
    if limit and limit > 0:
        projected = abs(ctx.position_quantity + quantity)
        if projected > limit + 1e-6:
            return RiskDecision(False, "max_position_exceeded")

    warnings: Tuple[str, ...] = ()

    has_portfolio_limits = any(
        value > 0
        for value in (
            limits.portfolio_gross_cap,
            limits.per_asset_cap,
            limits.per_trade_risk_cap,
            limits.portfolio_drawdown_cap,
            limits.daily_portfolio_loss_cap,
            limits.daily_strategy_loss_cap,
            limits.capacity_warn_participation,
            limits.capacity_max_participation,
            limits.turnover_warn,
            limits.turnover_block,
        )
    ) or bool(limits.asset_class_caps)

    if has_portfolio_limits:
        projected_gross = (
            ctx.projected_gross_exposure
            if ctx.projected_gross_exposure is not None
            else ctx.gross_exposure
        )
        projected_symbol = (
            ctx.projected_symbol_exposure
            if ctx.projected_symbol_exposure is not None
            else ctx.symbol_exposure
        )
        projected_class = (
            ctx.projected_class_exposure
            if ctx.projected_class_exposure is not None
            else ctx.class_exposure
        )
        delta_gross = (
            ctx.delta_gross_exposure
            if ctx.delta_gross_exposure
            else projected_gross - ctx.gross_exposure
        )
        delta_symbol = (
            ctx.delta_symbol_exposure
            if ctx.delta_symbol_exposure
            else projected_symbol - ctx.symbol_exposure
        )
        delta_class = (
            ctx.delta_class_exposure
            if ctx.delta_class_exposure
            else projected_class - ctx.class_exposure
        )
        asset_class = ctx.asset_class or limits.default_asset_class
        strategy_loss = ctx.strategy_daily_losses.get(
            ctx.strategy_id, ctx.daily_portfolio_loss
        )
        config = PortfolioLimitsConfig(
            gross_cap=limits.portfolio_gross_cap,
            per_asset_cap=limits.per_asset_cap,
            class_caps=limits.asset_class_caps,
            per_trade_cap=limits.per_trade_risk_cap,
            drawdown_cap=limits.portfolio_drawdown_cap,
            cooldown_days=limits.cooldown_days,
            daily_portfolio_loss_cap=limits.daily_portfolio_loss_cap,
            daily_strategy_loss_cap=limits.daily_strategy_loss_cap,
            capacity_warn=limits.capacity_warn_participation,
            capacity_block=limits.capacity_max_participation,
            turnover_warn=limits.turnover_warn,
            turnover_block=limits.turnover_block,
        )
        order_state = PortfolioOrderState(
            symbol=symbol,
            asset_class=asset_class,
            strategy=ctx.strategy_id or symbol,
            nav=ctx.equity,
            order_notional=order_notional,
            gross_exposure=ctx.gross_exposure,
            projected_gross_exposure=projected_gross,
            delta_gross_exposure=delta_gross,
            asset_exposure=ctx.symbol_exposure,
            projected_asset_exposure=projected_symbol,
            delta_asset_exposure=delta_symbol,
            class_exposure=ctx.class_exposure,
            projected_class_exposure=projected_class,
            delta_class_exposure=delta_class,
            drawdown=ctx.portfolio_drawdown,
            daily_portfolio_loss=ctx.daily_portfolio_loss,
            daily_strategy_loss=strategy_loss,
            cooldown_active=ctx.cooldown_active,
            projected_turnover=ctx.projected_turnover,
            order_participation=ctx.order_participation,
            reducing=ctx.reducing_risk,
        )
        decision = evaluate_order_limits(order_state, config)
        if not decision.allowed:
            return RiskDecision(False, decision.reason)
        warnings = decision.warnings

    return RiskDecision(True, warnings=warnings)


def check_session_drawdown(limits: RiskLimits, ctx: RiskContext) -> RiskDecision:
    """Guard that halts the session when drawdown breaches limits."""

    if limits.max_drawdown_bps > 0 and ctx.realized_drawdown_bps <= -abs(
        limits.max_drawdown_bps
    ):
        return RiskDecision(False, "session_drawdown_limit")
    return RiskDecision(True)


def check_circuit_breakers(limits: RiskLimits, ctx: RiskContext) -> RiskDecision:
    """Apply global stop conditions (kill switch, drawdown, stale data)."""

    if limits.kill_switch_file and limits.kill_switch_file.exists():
        return RiskDecision(False, "kill_switch_triggered")
    drawdown_decision = check_session_drawdown(limits, ctx)
    if not drawdown_decision.allowed:
        return drawdown_decision
    if (
        limits.max_consecutive_rejects > 0
        and ctx.consecutive_rejects >= limits.max_consecutive_rejects
    ):
        return RiskDecision(False, "reject_limit_reached")
    if limits.stale_data_threshold_s > 0:
        age = ctx.now_ts - ctx.last_bar_ts
        if age >= limits.stale_data_threshold_s:
            return RiskDecision(False, "data_stale")
    return RiskDecision(True)


def compute_drawdown_bps(equity: float, peak_equity: float) -> float:
    """Return drawdown in basis points relative to the peak equity."""

    if peak_equity <= 0:
        return 0.0
    drop = equity - peak_equity
    return (drop / peak_equity) * 10_000


ViolationPayload = Mapping[str, float | str]
ViolationLogger = Callable[[str, ViolationPayload], None]
SnapshotPersister = Callable[[RiskDecision], None]


def _log_violation(reason: str, payload: ViolationPayload) -> None:
    logger.error(
        "risk_guard_halt reason=%s details=%s",
        reason,
        {
            k: (round(v, 6) if isinstance(v, (int, float)) else v)
            for k, v in payload.items()
        },
    )


def enforce_guards(
    symbol: str,
    quantity: float,
    price: float,
    limits: RiskLimits,
    ctx: RiskContext,
    persist_snapshot: SnapshotPersister | None = None,
    violation_logger: ViolationLogger | None = None,
) -> RiskDecision:
    """Run guards in deterministic priority order.

    The evaluation order is max order notional, max position (per-symbol first),
    then session drawdown. The first guard to fail halts the session, logs a
    structured message, and triggers the provided snapshot persister.
    """

    violation_logger = violation_logger or _log_violation

    decision = check_order_limits(symbol, quantity, price, limits, ctx)
    if not decision.allowed:
        _handle_violation(
            decision,
            symbol,
            quantity,
            price,
            persist_snapshot,
            violation_logger,
        )
        return decision

    drawdown_decision = check_session_drawdown(limits, ctx)
    if not drawdown_decision.allowed:
        _handle_violation(
            drawdown_decision,
            symbol,
            quantity,
            price,
            persist_snapshot,
            violation_logger,
        )
        return drawdown_decision

    return RiskDecision(True, warnings=decision.warnings)


def _handle_violation(
    decision: RiskDecision,
    symbol: str,
    quantity: float,
    price: float,
    persist_snapshot: SnapshotPersister | None,
    violation_logger: ViolationLogger,
) -> None:
    payload: Dict[str, float | str] = {
        "symbol": symbol,
        "quantity": quantity,
        "price": price,
        "notional": _notional(quantity, price),
    }
    violation_logger(decision.reason, payload)
    if persist_snapshot is not None:
        persist_snapshot(decision)

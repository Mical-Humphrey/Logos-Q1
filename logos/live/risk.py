"""Risk checks enforced before and during live trading."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Optional

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


@dataclass
class RiskContext:
    """Live state needed for the checks."""

    equity: float
    position_quantity: float
    realized_drawdown_bps: float
    consecutive_rejects: int
    last_bar_ts: float
    now_ts: float


@dataclass
class RiskDecision:
    """Structured response returned by the risk layer."""

    allowed: bool
    reason: str = ""

    def __bool__(self) -> bool:  # pragma: no cover - convenience
        return self.allowed


def _notional(quantity: float, price: float) -> float:
    return abs(quantity * price)


def check_order_limits(symbol: str, quantity: float, price: float, limits: RiskLimits, ctx: RiskContext) -> RiskDecision:
    """Ensure the proposed order respects sizing limits."""

    if limits.max_notional > 0 and _notional(quantity, price) > limits.max_notional + 1e-6:
        return RiskDecision(False, "max_notional_exceeded")

    limit = limits.symbol_position_limits.get(symbol, limits.max_position)
    if limit and limit > 0:
        projected = abs(ctx.position_quantity + quantity)
        if projected > limit + 1e-6:
            return RiskDecision(False, "max_position_exceeded")
    return RiskDecision(True)


def check_session_drawdown(limits: RiskLimits, ctx: RiskContext) -> RiskDecision:
    """Guard that halts the session when drawdown breaches limits."""

    if limits.max_drawdown_bps > 0 and ctx.realized_drawdown_bps <= -abs(limits.max_drawdown_bps):
        return RiskDecision(False, "session_drawdown_limit")
    return RiskDecision(True)


def check_circuit_breakers(limits: RiskLimits, ctx: RiskContext) -> RiskDecision:
    """Apply global stop conditions (kill switch, drawdown, stale data)."""

    if limits.kill_switch_file and limits.kill_switch_file.exists():
        return RiskDecision(False, "kill_switch_triggered")
    drawdown_decision = check_session_drawdown(limits, ctx)
    if not drawdown_decision.allowed:
        return drawdown_decision
    if limits.max_consecutive_rejects > 0 and ctx.consecutive_rejects >= limits.max_consecutive_rejects:
        return RiskDecision(False, "reject_limit_reached")
    if limits.stale_data_threshold_s > 0:
        age = ctx.now_ts - ctx.last_bar_ts
        if age > limits.stale_data_threshold_s:
            return RiskDecision(False, "data_stale")
    return RiskDecision(True)


def compute_drawdown_bps(equity: float, peak_equity: float) -> float:
    """Return drawdown in basis points relative to the peak equity."""

    if peak_equity <= 0:
        return 0.0
    drop = equity - peak_equity
    return (drop / peak_equity) * 10_000


ViolationLogger = Callable[[str, Dict[str, float]], None]
SnapshotPersister = Callable[[RiskDecision], None]


def _log_violation(reason: str, payload: Dict[str, float]) -> None:
    logger.error(
        "risk_guard_halt reason=%s details=%s",
        reason,
        {k: (round(v, 6) if isinstance(v, (int, float)) else v) for k, v in payload.items()},
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

    return RiskDecision(True)


def _handle_violation(
    decision: RiskDecision,
    symbol: str,
    quantity: float,
    price: float,
    persist_snapshot: SnapshotPersister | None,
    violation_logger: ViolationLogger,
) -> None:
    payload = {
        "symbol": symbol,
        "quantity": quantity,
        "price": price,
        "notional": _notional(quantity, price),
    }
    violation_logger(decision.reason, payload)
    if persist_snapshot is not None:
        persist_snapshot(decision)

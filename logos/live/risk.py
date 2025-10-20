"""Risk checks enforced before and during live trading."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class RiskLimits:
    """Configuration for pre-trade and circuit-breaker checks."""

    max_notional: float = 0.0
    max_position: float = 0.0
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


def check_order_limits(quantity: float, price: float, limits: RiskLimits, ctx: RiskContext) -> RiskDecision:
    """Ensure the proposed order respects sizing limits."""

    if limits.max_notional > 0 and _notional(quantity, price) > limits.max_notional + 1e-6:
        return RiskDecision(False, "max_notional_exceeded")
    if limits.max_position > 0:
        projected = abs(ctx.position_quantity + quantity)
        if projected > limits.max_position + 1e-6:
            return RiskDecision(False, "max_position_exceeded")
    return RiskDecision(True)


def check_circuit_breakers(limits: RiskLimits, ctx: RiskContext) -> RiskDecision:
    """Apply global stop conditions (kill switch, drawdown, stale data)."""

    if limits.kill_switch_file and limits.kill_switch_file.exists():
        return RiskDecision(False, "kill_switch_triggered")
    if limits.max_drawdown_bps > 0 and ctx.realized_drawdown_bps <= -abs(limits.max_drawdown_bps):
        return RiskDecision(False, "drawdown_limit_reached")
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

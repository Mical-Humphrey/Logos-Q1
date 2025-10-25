from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Mapping, Tuple

__all__ = [
    "PortfolioLimitsConfig",
    "PortfolioOrderState",
    "PortfolioDecision",
    "evaluate_order_limits",
]

_EPS = 1e-9


@dataclass(slots=True)
class PortfolioLimitsConfig:
    """Normalized configuration for portfolio overlays."""

    gross_cap: float = 0.0
    per_asset_cap: float = 0.0
    class_caps: Mapping[str, float] = field(default_factory=dict)
    per_trade_cap: float = 0.0
    drawdown_cap: float = 0.0
    cooldown_days: int = 0
    daily_portfolio_loss_cap: float = 0.0
    daily_strategy_loss_cap: float = 0.0
    capacity_warn: float = 0.0
    capacity_block: float = 0.0
    turnover_warn: float = 0.0
    turnover_block: float = 0.0


@dataclass(slots=True)
class PortfolioOrderState:
    """Snapshot of the portfolio before/after a proposed order."""

    symbol: str
    asset_class: str
    strategy: str
    nav: float
    order_notional: float
    gross_exposure: float
    projected_gross_exposure: float
    delta_gross_exposure: float
    asset_exposure: float
    projected_asset_exposure: float
    delta_asset_exposure: float
    class_exposure: float
    projected_class_exposure: float
    delta_class_exposure: float
    drawdown: float
    daily_portfolio_loss: float
    daily_strategy_loss: float
    cooldown_active: bool
    projected_turnover: float
    order_participation: float
    reducing: bool = False


@dataclass(slots=True)
class PortfolioDecision:
    """Decision returned by :func:`evaluate_order_limits`."""

    allowed: bool
    reason: str = ""
    warnings: Tuple[str, ...] = field(default_factory=tuple)


def _cap_for_class(config: PortfolioLimitsConfig, asset_class: str) -> float:
    cap = config.class_caps.get(asset_class.lower())
    if cap is None:
        cap = config.class_caps.get(asset_class.upper())
    return float(cap or 0.0)


def _cap_violation(value: float, cap: float) -> bool:
    return cap > 0.0 and value > cap + _EPS


def evaluate_order_limits(
    order: PortfolioOrderState,
    config: PortfolioLimitsConfig,
) -> PortfolioDecision:
    """Return guard decision for the proposed order."""

    warnings = []

    if order.cooldown_active:
        return PortfolioDecision(False, "cooldown_active")

    if config.drawdown_cap > 0.0 and order.drawdown >= config.drawdown_cap - _EPS:
        return PortfolioDecision(False, "portfolio_drawdown_cap")

    if (
        config.daily_portfolio_loss_cap > 0.0
        and order.daily_portfolio_loss <= -config.daily_portfolio_loss_cap - _EPS
    ):
        return PortfolioDecision(False, "daily_portfolio_loss_cap")

    if (
        config.daily_strategy_loss_cap > 0.0
        and order.daily_strategy_loss <= -config.daily_strategy_loss_cap - _EPS
    ):
        return PortfolioDecision(False, "strategy_daily_loss_cap")

    if (
        config.per_trade_cap > 0.0
        and order.nav > 0.0
        and not order.reducing
        and abs(order.order_notional) / order.nav > config.per_trade_cap + _EPS
    ):
        return PortfolioDecision(False, "per_trade_risk_cap")

    if _cap_violation(order.projected_gross_exposure, config.gross_cap):
        # Increasing risk past the cap is blocked; reductions remain allowed.
        if order.delta_gross_exposure > _EPS:
            return PortfolioDecision(False, "portfolio_gross_cap")

    if _cap_violation(order.projected_asset_exposure, config.per_asset_cap):
        if order.delta_asset_exposure > _EPS:
            return PortfolioDecision(False, "per_asset_cap")

    class_cap = _cap_for_class(config, order.asset_class)
    if _cap_violation(order.projected_class_exposure, class_cap):
        if order.delta_class_exposure > _EPS:
            return PortfolioDecision(False, "asset_class_cap")

    if (
        config.turnover_block > 0.0
        and order.projected_turnover > config.turnover_block + _EPS
    ):
        return PortfolioDecision(False, "turnover_block")

    if (
        config.capacity_block > 0.0
        and order.order_participation > config.capacity_block + _EPS
    ):
        return PortfolioDecision(False, "capacity_limit")

    if (
        config.turnover_warn > 0.0
        and order.projected_turnover > config.turnover_warn + _EPS
    ):
        warnings.append("turnover_warn")

    if (
        config.capacity_warn > 0.0
        and order.order_participation > config.capacity_warn + _EPS
    ):
        warnings.append("capacity_warn")

    return PortfolioDecision(True, warnings=tuple(warnings))

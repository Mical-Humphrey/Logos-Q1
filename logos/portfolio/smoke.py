from __future__ import annotations

import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .allocators import (
    AllocatorConfig,
    risk_budget_allocation,
    volatility_parity_allocation,
)
from .risk import (
    PortfolioDecision,
    PortfolioLimitsConfig,
    PortfolioOrderState,
    evaluate_order_limits,
)


@dataclass(slots=True)
class SmokeResult:
    weights_vol: pd.Series
    weights_risk: pd.Series
    decision: PortfolioDecision


def _synthetic_returns(seed: int = 7, periods: int = 40) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    data = rng.normal(0.0, 0.01, size=(periods, 2))
    frame = pd.DataFrame(data, columns=["EQT", "CRYPTO"])
    frame.index = pd.date_range("2024-01-01", periods=periods, freq="B")
    return frame


def run_smoke() -> SmokeResult:
    returns = _synthetic_returns()
    cfg = AllocatorConfig()
    weights_vol = volatility_parity_allocation(returns, cfg)
    budgets = {"EQT": 0.6, "CRYPTO": 0.4}
    weights_risk = risk_budget_allocation(returns, budgets, cfg)

    nav = 1_000_000.0
    current_exposure = 0.45  # 45% NAV gross
    order_notional = 75_000.0
    projected_asset_exposure = (current_exposure * nav + order_notional) / nav
    order_state = PortfolioOrderState(
        symbol="BTC-USD",
        asset_class="crypto",
        strategy="smoke",
        nav=nav,
        order_notional=order_notional,
        gross_exposure=current_exposure,
        projected_gross_exposure=current_exposure + order_notional / nav,
        delta_gross_exposure=order_notional / nav,
        asset_exposure=current_exposure,
        projected_asset_exposure=projected_asset_exposure,
        delta_asset_exposure=order_notional / nav,
        class_exposure=current_exposure,
        projected_class_exposure=projected_asset_exposure,
        delta_class_exposure=order_notional / nav,
        drawdown=0.05,
        daily_portfolio_loss=-0.005,
        daily_strategy_loss=-0.005,
        cooldown_active=False,
        projected_turnover=0.07,
        order_participation=0.02,
        reducing=False,
    )

    limits = PortfolioLimitsConfig(
        gross_cap=1.0,
        per_asset_cap=0.6,
        class_caps={"crypto": 0.6, "equity": 0.5, "forex": 0.5},
        per_trade_cap=0.10,
        drawdown_cap=0.12,
        cooldown_days=5,
        daily_portfolio_loss_cap=0.02,
        daily_strategy_loss_cap=0.0075,
        capacity_warn=0.03,
        capacity_block=0.05,
        turnover_warn=0.15,
        turnover_block=0.30,
    )

    decision = evaluate_order_limits(order_state, limits)
    if not decision.allowed:
        raise RuntimeError(
            f"portfolio smoke unexpectedly rejected order: {decision.reason}"
        )

    return SmokeResult(
        weights_vol=weights_vol, weights_risk=weights_risk, decision=decision
    )


def main() -> None:
    result = run_smoke()
    print("vol parity weights", result.weights_vol.to_dict())
    print("risk budget weights", result.weights_risk.to_dict())
    if result.decision.warnings:
        print("warnings", ",".join(result.decision.warnings))


if __name__ == "__main__":  # pragma: no cover
    try:
        main()
    except Exception as exc:  # pragma: no cover - debug aid
        print(f"Phase 6 smoke failed: {exc}", file=sys.stderr)
        sys.exit(1)

from __future__ import annotations

import dataclasses

import pytest

from logos.portfolio.risk import (
    PortfolioDecision,
    PortfolioLimitsConfig,
    PortfolioOrderState,
    evaluate_order_limits,
)


def _base_state(**overrides) -> PortfolioOrderState:
    state = PortfolioOrderState(
        symbol="MSFT",
        asset_class="equity",
        strategy="demo",
        nav=1_000_000.0,
        order_notional=0.0,
        gross_exposure=0.10,
        projected_gross_exposure=0.10,
        delta_gross_exposure=0.0,
        asset_exposure=0.05,
        projected_asset_exposure=0.05,
        delta_asset_exposure=0.0,
        class_exposure=0.05,
        projected_class_exposure=0.05,
        delta_class_exposure=0.0,
        drawdown=0.0,
        daily_portfolio_loss=0.0,
        daily_strategy_loss=0.0,
        cooldown_active=False,
        projected_turnover=0.0,
        order_participation=0.0,
        reducing=False,
    )
    return dataclasses.replace(state, **overrides)


def test_cooldown_blocks_orders():
    config = PortfolioLimitsConfig()
    decision = evaluate_order_limits(_base_state(cooldown_active=True), config)
    assert decision == PortfolioDecision(False, "cooldown_active")


def test_drawdown_and_daily_loss_caps_enforced():
    config = PortfolioLimitsConfig(drawdown_cap=0.05, daily_portfolio_loss_cap=0.02)
    decision = evaluate_order_limits(
        _base_state(drawdown=0.051),
        config,
    )
    assert not decision.allowed
    assert decision.reason == "portfolio_drawdown_cap"

    decision = evaluate_order_limits(
        _base_state(drawdown=0.03, daily_portfolio_loss=-0.03),
        config,
    )
    assert not decision.allowed
    assert decision.reason == "daily_portfolio_loss_cap"


def test_per_trade_cap_blocks_excessive_risk():
    config = PortfolioLimitsConfig(per_trade_cap=0.10)
    state = _base_state(order_notional=150_000.0, nav=1_000_000.0)
    decision = evaluate_order_limits(state, config)
    assert not decision.allowed
    assert decision.reason == "per_trade_risk_cap"


def test_exposure_reduction_allowed_when_over_cap():
    config = PortfolioLimitsConfig(per_asset_cap=0.2, gross_cap=0.4, class_caps={"equity": 0.3})
    state = _base_state(
        projected_asset_exposure=0.25,
        delta_asset_exposure=-0.05,
        projected_gross_exposure=0.45,
        delta_gross_exposure=-0.05,
        projected_class_exposure=0.35,
        delta_class_exposure=-0.05,
        reducing=True,
    )
    decision = evaluate_order_limits(state, config)
    assert decision.allowed


def test_turnover_and_capacity_warnings():
    config = PortfolioLimitsConfig(
        turnover_warn=0.15,
        turnover_block=0.30,
        capacity_warn=0.05,
        capacity_block=0.10,
    )
    state = _base_state(projected_turnover=0.2, order_participation=0.075)
    decision = evaluate_order_limits(state, config)
    assert decision.allowed
    assert set(decision.warnings) == {"turnover_warn", "capacity_warn"}


def test_capacity_block_triggers_limit():
    config = PortfolioLimitsConfig(capacity_block=0.05)
    decision = evaluate_order_limits(
        _base_state(order_participation=0.06),
        config,
    )
    assert not decision.allowed
    assert decision.reason == "capacity_limit"


def test_strategy_daily_loss_cap_applies():
    config = PortfolioLimitsConfig(daily_strategy_loss_cap=0.03)
    state = _base_state(daily_strategy_loss=-0.05)
    decision = evaluate_order_limits(state, config)
    assert not decision.allowed
    assert decision.reason == "strategy_daily_loss_cap"


def test_asset_class_cap_blocks_increasing_exposure():
    config = PortfolioLimitsConfig(class_caps={"equity": 0.25})
    state = _base_state(
        projected_class_exposure=0.3,
        delta_class_exposure=0.05,
    )
    decision = evaluate_order_limits(state, config)
    assert not decision.allowed
    assert decision.reason == "asset_class_cap"

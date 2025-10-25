# src/backtest/engine.py
# =============================================================================
# Purpose:
#   Convert signals into trades, simulate fills and costs, and produce equity,
#   positions, returns, trades, and metrics — now asset-class and interval aware.
#
# New:
#   - 'asset_class' switch for cost handling (equity, crypto, fx)
#   - 'periods_per_year' passed in to metrics for correct annualization
#   - Optional FX spread and crypto fee handling
#
# Simplifications:
#   - Fixed-dollar sizing per trade (no compounding)
#   - Enter/exit on signal changes only
#   - Slippage remains naive bps on price
# =============================================================================
from __future__ import annotations

import logging
from collections import deque
from typing import Dict, List, TypedDict

import numpy as np
import pandas as pd

from logos.utils.data_hygiene import ensure_no_object_dtype, require_datetime_index
from logos.utils.indexing import adjust_at, adjust_from, label_value

from .metrics import cagr, sharpe, max_drawdown, win_rate, exposure
from .slippage import apply as slip_price
from .costs import commission_per_share, crypto_fee_usd, fx_spread_price_bump
from logos.portfolio.capacity import compute_adv_notional, compute_participation
from logos.live.risk import (
    RiskLimits,
    RiskContext,
    check_circuit_breakers,
    check_order_limits,
    compute_drawdown_bps,
)

logger = logging.getLogger(__name__)


class BacktestResult(TypedDict):
    equity_curve: pd.Series
    positions: pd.Series
    returns: pd.Series
    trades: pd.DataFrame
    metrics: Dict[str, float]


def run_backtest(
    prices: pd.DataFrame,
    signals: pd.Series,
    dollar_per_trade: float = 10_000,
    slip_bps: float = 1.0,
    commission_per_share_rate: float = 0.0035,
    fee_bps: float = 5.0,  # crypto maker/taker fee
    fx_pip_size: float = 0.0001,  # 0.0001 for EURUSD; 0.01 for USDJPY
    asset_class: str = "equity",
    periods_per_year: int = 252,
    risk_limits: RiskLimits | None = None,
    portfolio_nav: float | None = None,
    strategy_id: str = "backtest",
    symbol: str | None = None,
) -> BacktestResult:
    """Simulate trading given price data and target signals with asset-aware costs."""
    require_datetime_index(prices, context="run_backtest(prices)")
    ensure_no_object_dtype(prices, context="run_backtest(prices)")
    require_datetime_index(signals, context="run_backtest(signals)")
    ensure_no_object_dtype(signals, context="run_backtest(signals)")

    df = prices.copy().sort_index()
    if df.index.has_duplicates:
        df = df[~df.index.duplicated(keep="last")]
    sig = signals.reindex(df.index).fillna(0).astype(int)
    close = df["Close"].astype(float)

    # Detect changes in desired position direction (delta signals)
    changes = sig - sig.shift(1).fillna(0).astype(int)
    orders_idx = changes.index[changes != 0]
    sides = np.sign(changes.loc[orders_idx]).astype(int)
    ref_prices = close.loc[orders_idx]
    base_sizes = np.floor(dollar_per_trade / ref_prices).astype(int)
    shares = (base_sizes * sides).astype(int)

    asset = asset_class.lower()
    candidate_orders: List[Dict[str, object]] = []
    for t, side, sh in zip(orders_idx, sides, shares):
        if sh == 0:
            continue
        px = float(label_value(close, t))
        fill_p = float(px)
        if asset in {"fx", "forex"}:
            fill_p = fx_spread_price_bump(
                fill_p, int(side), spread_pips=1.0, pip_size=fx_pip_size
            )
        fill_p = slip_price(fill_p, int(side), slip_bps=slip_bps)
        if asset == "equity":
            fee = commission_per_share(int(sh), rate=commission_per_share_rate)
        elif asset == "crypto":
            fee = crypto_fee_usd(fill_p, int(sh), fee_bps=fee_bps)
        else:
            fee = 0.0
        candidate_orders.append(
            {
                "time": t,
                "side": int(side),
                "shares": int(sh),
                "ref_close": float(px),
                "fill_price": float(fill_p),
                "fee": float(fee),
            }
        )

    allowed_orders: List[Dict[str, object]] = []
    current_position = 0.0
    cash_balance = 0.0
    nav_base = float(portfolio_nav or 0.0)
    equity_offset = nav_base if nav_base > 0 else 0.0
    peak_equity = equity_offset
    current_day = None
    day_open_equity = equity_offset
    daily_turnover = 0.0
    strategy_daily_loss = 0.0
    cooldown_days_remaining = 0
    consecutive_rejects = 0
    symbol_label = symbol or "portfolio"
    adv_window = (
        risk_limits.adv_lookback_days
        if risk_limits and risk_limits.adv_lookback_days
        else 20
    )
    if adv_window <= 0:
        adv_window = 20
    volume_history = deque(maxlen=adv_window)
    last_bar_ts: float | None = None

    for order in candidate_orders:
        bar_dt = order["time"]
        mark_price = float(label_value(close, bar_dt))
        raw_volume = 0.0
        if "Volume" in df.columns:
            try:
                raw_volume = float(df.loc[bar_dt]["Volume"])
            except (KeyError, TypeError, ValueError):
                raw_volume = 0.0
        notional_obs = raw_volume * mark_price
        volume_history.append(notional_obs)
        adv_notional = compute_adv_notional(volume_history)

        equity = equity_offset + cash_balance + current_position * mark_price
        if equity > peak_equity:
            peak_equity = equity

        order_day = bar_dt.date()
        if current_day != order_day:
            if current_day is not None and cooldown_days_remaining > 0:
                cooldown_days_remaining = max(0, cooldown_days_remaining - 1)
            current_day = order_day
            day_open_equity = equity
            daily_turnover = 0.0
            strategy_daily_loss = 0.0

        portfolio_drawdown = (
            0.0 if peak_equity <= 0 else (peak_equity - equity) / peak_equity
        )
        if (
            risk_limits
            and risk_limits.portfolio_drawdown_cap > 0.0
            and portfolio_drawdown >= risk_limits.portfolio_drawdown_cap
            and cooldown_days_remaining == 0
        ):
            cooldown_days_remaining = risk_limits.cooldown_days
        cooldown_active = cooldown_days_remaining > 0
        daily_portfolio_loss = (
            0.0
            if day_open_equity <= 0
            else (equity - day_open_equity) / day_open_equity
        )

        nav_denom = nav_base if nav_base > 0 else max(abs(equity), 1.0)
        order_qty = float(order["shares"])
        projected_qty = current_position + order_qty
        order_notional = abs(order_qty * mark_price)
        order_turnover = order_notional / nav_denom if nav_denom > 0 else 0.0
        projected_turnover = daily_turnover + order_turnover
        current_symbol_exposure = (
            abs(current_position * mark_price) / nav_denom if nav_denom > 0 else 0.0
        )
        projected_symbol_exposure = (
            abs(projected_qty * mark_price) / nav_denom if nav_denom > 0 else 0.0
        )
        delta_symbol_exposure = projected_symbol_exposure - current_symbol_exposure
        current_class_exposure = current_symbol_exposure
        projected_class_exposure = projected_symbol_exposure
        delta_class_exposure = delta_symbol_exposure
        gross_exposure = current_symbol_exposure
        projected_gross_exposure = projected_symbol_exposure
        delta_gross_exposure = delta_symbol_exposure
        participation = compute_participation(order_notional, adv_notional)
        reducing = projected_symbol_exposure <= current_symbol_exposure + 1e-9

        if risk_limits:
            circuit_ctx = RiskContext(
                equity=equity,
                position_quantity=current_position,
                realized_drawdown_bps=compute_drawdown_bps(equity, peak_equity),
                consecutive_rejects=consecutive_rejects,
                last_bar_ts=last_bar_ts or bar_dt.timestamp(),
                now_ts=bar_dt.timestamp(),
            )
            circuit_decision = check_circuit_breakers(risk_limits, circuit_ctx)
            if not circuit_decision.allowed:
                logger.warning(
                    "backtest_halt reason=%s time=%s",
                    circuit_decision.reason,
                    bar_dt,
                )
                break

        if risk_limits and nav_denom > 0:
            ctx = RiskContext(
                equity=equity,
                position_quantity=current_position,
                realized_drawdown_bps=compute_drawdown_bps(equity, peak_equity),
                consecutive_rejects=consecutive_rejects,
                last_bar_ts=bar_dt.timestamp(),
                now_ts=bar_dt.timestamp(),
                order_notional=order_notional,
                gross_exposure=gross_exposure,
                projected_gross_exposure=projected_gross_exposure,
                delta_gross_exposure=delta_gross_exposure,
                symbol_exposure=current_symbol_exposure,
                projected_symbol_exposure=projected_symbol_exposure,
                delta_symbol_exposure=delta_symbol_exposure,
                asset_class=asset_class,
                class_exposure=current_class_exposure,
                projected_class_exposure=projected_class_exposure,
                delta_class_exposure=delta_class_exposure,
                portfolio_drawdown=portfolio_drawdown,
                daily_portfolio_loss=daily_portfolio_loss,
                strategy_id=strategy_id,
                strategy_daily_losses={strategy_id: strategy_daily_loss},
                cooldown_active=cooldown_active,
                projected_turnover=projected_turnover,
                order_participation=participation,
                adv_notional=adv_notional,
                reducing_risk=reducing,
            )
            decision = check_order_limits(
                symbol_label, order_qty, mark_price, risk_limits, ctx
            )
            if decision.warnings:
                for warning in decision.warnings:
                    logger.warning(
                        "risk_warning code=%s symbol=%s projected_turnover=%.4f participation=%.4f",
                        warning,
                        symbol_label,
                        projected_turnover,
                        participation,
                    )
            if not decision.allowed:
                consecutive_rejects += 1
                logger.warning(
                    "risk_reject reason=%s symbol=%s time=%s",
                    decision.reason,
                    symbol_label,
                    bar_dt,
                )
                if (
                    decision.reason == "portfolio_drawdown_cap"
                    and risk_limits.cooldown_days > 0
                    and cooldown_days_remaining == 0
                ):
                    cooldown_days_remaining = risk_limits.cooldown_days
                last_bar_ts = bar_dt.timestamp()
                continue
            consecutive_rejects = 0
        else:
            consecutive_rejects = 0

        cash_balance -= order_qty * float(order["fill_price"]) + float(order["fee"])
        current_position = projected_qty
        daily_turnover = projected_turnover
        last_bar_ts = bar_dt.timestamp()

        equity_after = equity_offset + cash_balance + current_position * mark_price
        if equity_after > peak_equity:
            peak_equity = equity_after
        if day_open_equity > 0:
            strategy_daily_loss = (equity_after - day_open_equity) / day_open_equity

        allowed_orders.append(order)

    position = pd.Series(0.0, index=df.index)
    cash = pd.Series(0.0, index=df.index)
    for order in allowed_orders:
        sh = float(order["shares"])
        adjust_from(position, order["time"], sh)
        adjust_at(
            cash,
            order["time"],
            -(sh * float(order["fill_price"]) + float(order["fee"])),
        )

    mkt_value = position * close
    equity = (cash.cumsum() + mkt_value).ffill()
    if portfolio_nav and portfolio_nav > 0:
        equity = equity + float(portfolio_nav)

    returns = equity.pct_change(fill_method=None)
    returns = returns.replace([np.inf, -np.inf], 0.0).fillna(0.0)

    trade_marks = position.abs().diff() < 0
    realized = returns.where(trade_marks, 0.0)
    trade_pnl_series = realized * equity.shift(1).bfill()

    metrics = {
        "CAGR": cagr(equity, periods_per_year=periods_per_year),
        "Sharpe": sharpe(returns, periods_per_year=periods_per_year),
        "MaxDD": max_drawdown(equity),
        "WinRate": win_rate(trade_pnl_series[trade_pnl_series != 0.0]),
        "Exposure": exposure(position),
    }

    trades = pd.DataFrame(
        {
            "time": [order["time"] for order in allowed_orders],
            "side": [order["side"] for order in allowed_orders],
            "shares": [order["shares"] for order in allowed_orders],
            "ref_close": [order["ref_close"] for order in allowed_orders],
        }
    )

    return {
        "equity_curve": equity,
        "positions": position,
        "returns": returns,
        "trades": trades,
        "metrics": metrics,
    }

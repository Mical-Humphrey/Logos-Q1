# logos/tutor/engine.py
# =============================================================================
# Purpose:
#   Power the educational "Tutor Mode" walkthroughs for Logos-Q1.
#   Each lesson fetches real market data, applies existing strategies,
#   and narrates every mathematical step so new traders understand the "why".
#
# Summary:
#   - Provides a reusable LessonContext for logging + transcript capture
#   - Registers tutorial handlers (mean reversion, momentum, pairs trading)
#   - Reuses project modules: config, data loader, strategies, backtest engine
#   - Narrates formulas (SMA, z-score, correlation, Sharpe, drawdown)
#   - Persists transcripts under runs/lessons/ and optionally plots the series
#
# Design Philosophy:
#   - Education-first: every calculation is explained in plain language
#   - Zero duplication: rely on the same engines as production backtests
#   - Extensible: add new lessons by decorating functions with @lesson
# =============================================================================
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List

import numpy as np
import pandas as pd

from ..config import load_settings
from ..data_loader import get_prices
from ..backtest.engine import run_backtest
from ..strategies.mean_reversion import generate_signals as mean_reversion_signals
from ..strategies.momentum import generate_signals as momentum_signals
from ..strategies.pairs_trading import generate_signals as pairs_trading_signals
from ..utils import ensure_dirs, setup_logging

# Module-wide logger so CLI shims get consistent messages and transcript copies.
logger = logging.getLogger(__name__)


@dataclass
class LessonContext:
    """Mutable state shared across lesson scripts."""
    lesson: str
    settings: object
    plot: bool
    transcript: List[str]

    def narrate(self, message: str) -> None:
        """Print, log, and collect each narration line."""
        print(message)
        logger.info(message)
        self.transcript.append(message)


# Registry mapping lesson names to their execution callbacks.
LESSON_HANDLERS: Dict[str, Callable[[LessonContext], None]] = {}


def lesson(name: str) -> Callable[[Callable[[LessonContext], None]], Callable[[LessonContext], None]]:
    """Decorator to register lesson handlers by name."""
    def decorator(func: Callable[[LessonContext], None]) -> Callable[[LessonContext], None]:
        LESSON_HANDLERS[name] = func
        return func
    return decorator


def available_lessons() -> List[str]:
    """Return lesson names in sorted order for CLI display."""
    return sorted(LESSON_HANDLERS)


def _default_window(end: str, days: int = 120) -> tuple[str, str]:
    """Return (start, end) ISO strings covering a compact tutorial window."""
    if not end:
        raise ValueError("Settings.END_DATE must be defined for tutor lessons")
    end_dt = pd.to_datetime(end)
    start_dt = end_dt - pd.Timedelta(days=days)
    return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")


def _build_transcript_path(lesson_name: str) -> str:
    """Return the output path for the upcoming transcript write."""
    ensure_dirs()
    out_dir = os.path.join("runs", "lessons")
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return os.path.join(out_dir, f"{lesson_name}_{stamp}.txt")


def _write_transcript(ctx: LessonContext, path: str) -> None:
    """Persist the tutor narration so learners can revisit the storyline."""
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(ctx.transcript))
    logger.info("Saved tutor transcript -> %s", path)


def _maybe_plot(prices: pd.Series, signals: pd.Series, title: str) -> None:
    """Render a quick annotated plot when the --plot flag is used."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:  # pragma: no cover - optional dependency
        logger.warning("Matplotlib missing; skipping plot rendering")
        return

    fig, ax = plt.subplots(figsize=(10, 4))
    prices.plot(ax=ax, label="Close", color="#60a5fa")
    entries = signals.diff().fillna(signals) > 0
    exits = signals.diff().fillna(0) < 0
    ax.scatter(prices.index[entries], prices[entries], marker="^", color="#10b981", label="Entry")
    ax.scatter(prices.index[exits], prices[exits], marker="v", color="#f87171", label="Exit")
    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.set_ylabel("Price")
    ax.legend(loc="best")
    fig.tight_layout()
    plt.show()


@lesson("mean_reversion")
def _lesson_mean_reversion(ctx: LessonContext) -> None:
    symbol = "MSFT"
    # Kick things off with a friendly preamble so learners know the context.
    ctx.narrate(f"[Lesson: Mean Reversion] Using {symbol} daily bars to illustrate z-score fades.")

    start, end = _default_window(ctx.settings.end)
    # Pull a manageable slice of price history; tail() keeps the lesson concise.
    prices = get_prices(symbol, start, end, interval="1d", asset_class="equity").tail(40)
    close = prices["Close"].astype(float)

    lookback = 10
    window = close.tail(lookback)
    sma = window.mean()
    sigma = window.std(ddof=0)
    last_price = close.iloc[-1]
    z_value = (last_price - sma) / sigma

    # Narrate each formula in the order a human might compute it by hand.
    ctx.narrate(f"Step 1: {lookback}-day SMA = mean({window.min():.2f}…{window.max():.2f}) = {sma:.2f}")
    ctx.narrate(f"Step 2: σ (population std) = {sigma:.2f}; latest Close = {last_price:.2f}")
    ctx.narrate(f"Step 3: z = (Price - SMA) / σ = ({last_price:.2f} - {sma:.2f}) / {sigma:.2f} = {z_value:.2f}")

    signals = mean_reversion_signals(prices, lookback=lookback, z_entry=1.0)
    zscores = (close - close.rolling(lookback).mean()) / close.rolling(lookback).std(ddof=0)
    # Track signal changes so we can explain each entry/exit transition.
    changes = signals.diff().fillna(signals)
    step = 4
    meaningful = changes[changes != 0]
    if meaningful.empty:
        ctx.narrate(f"Step {step}: No trades fired in this window; prices stayed within ±{1.0:.1f}σ of the mean.")
        step += 1
    else:
        for when, delta in meaningful.items():
            sig = signals.loc[when]
            tag = "BUY" if sig == 1 else "SELL" if sig == -1 else "EXIT"
            reason = "reversion opportunity" if sig else "mean hit"
            z_at = zscores.loc[when]
            ctx.narrate(
                f"Step {step}: {tag} {'entry' if sig else 'flat'} at {close.loc[when]:.2f} on {when.date()} "
                f"because z = {z_at:.2f} → {reason}."
            )
            step += 1

    # Feed the same signals into the existing backtest engine to keep logic shared.
    results = run_backtest(prices=prices, signals=signals, asset_class="equity", periods_per_year=252)
    sharpe = results["metrics"].get("Sharpe", float("nan"))
    drawdown = results["metrics"].get("MaxDD", float("nan"))
    if np.isfinite(sharpe):
        ctx.narrate(
            f"Step {step}: Sharpe = mean(excess returns)/σ * √252 = {sharpe:.2f}. Higher ≈ smoother equity curve."
        )
    else:
        ctx.narrate(
            f"Step {step}: Sharpe undefined for this mini-sample — returns lacked enough variation."
        )
    step += 1
    if np.isfinite(drawdown):
        ctx.narrate(
            f"Step {step}: Max Drawdown captures worst peak→trough = {drawdown:.2%}. Lower drawdown means sturdier risk."
        )
    else:
        ctx.narrate(
            f"Step {step}: Max Drawdown undefined here — equity never recovered above its starting high."
        )
    step += 1

    if ctx.plot:
        _maybe_plot(close, signals, "Mean Reversion Lesson")


@lesson("momentum")
def _lesson_momentum(ctx: LessonContext) -> None:
    symbol = "BTC-USD"
    ctx.narrate(f"[Lesson: Momentum] Tracking trend-following crossovers on {symbol}.")

    start, end = _default_window(ctx.settings.end)
    # Crypto trades 24/7, so learners see continuous data with quick trends.
    prices = get_prices(symbol, start, end, interval="1d", asset_class="crypto").tail(60)
    close = prices["Close"].astype(float)

    fast, slow = 5, 15
    sma_fast = close.rolling(fast).mean().iloc[-1]
    sma_slow = close.rolling(slow).mean().iloc[-1]
    ctx.narrate(
        f"Step 1: Fast SMA({fast}) = {close.tail(fast).mean():.2f}; Slow SMA({slow}) = {close.tail(slow).mean():.2f}" 
        f" → crossover check."
    )
    ctx.narrate(f"Step 2: Last Close {close.iloc[-1]:.2f} sits {'above' if sma_fast > sma_slow else 'below'} slow SMA → trend signal.")

    signals = momentum_signals(prices, fast=fast, slow=slow)
    # Similar to mean reversion, diff() highlights moments when the strategy flips bias.
    changes = signals.diff().fillna(signals)
    step = 3
    meaningful = changes[changes != 0]
    if meaningful.empty:
        ctx.narrate(f"Step {step}: No crossover yet — trend filter still neutral in this sample.")
        step += 1
    else:
        for when, delta in meaningful.items():
            sig = signals.loc[when]
            direction = "LONG" if sig == 1 else "SHORT" if sig == -1 else "FLAT"
            ctx.narrate(
                f"Step {step}: {direction} on {when.date()} because SMA({fast}) {'>' if sig == 1 else '<' if sig == -1 else '≈'} "
                f"SMA({slow}). Price={close.loc[when]:.2f}."
            )
            step += 1

    # Reuse the main simulation engine to obtain production-grade metrics.
    results = run_backtest(prices=prices, signals=signals, asset_class="crypto", periods_per_year=365)
    sharpe = results["metrics"].get("Sharpe", float("nan"))
    drawdown = results["metrics"].get("MaxDD", float("nan"))
    if np.isfinite(sharpe):
        ctx.narrate(
            f"Step {step}: Sharpe = {sharpe:.2f}. Trend systems aim for Sharpe > 1 after costs."
        )
    else:
        ctx.narrate(
            f"Step {step}: Sharpe undefined here — this slice is too flat to reveal momentum edge."
        )
    step += 1
    if np.isfinite(drawdown):
        ctx.narrate(
            f"Step {step}: Max Drawdown = {drawdown:.2%}. Momentum needs risk controls to prevent deep cuts."
        )
    else:
        ctx.narrate(
            f"Step {step}: Max Drawdown undefined because equity never set a new high in this window."
        )
    step += 1

    if ctx.plot:
        _maybe_plot(close, signals, "Momentum Lesson")


@lesson("pairs_trading")
def _lesson_pairs(ctx: LessonContext) -> None:
    sym_a, sym_b = "MSFT", "AAPL"
    ctx.narrate(f"[Lesson: Pairs Trading] Comparing {sym_a} vs {sym_b} to trade their spread.")

    start, end = _default_window(ctx.settings.end)
    prices_a = get_prices(sym_a, start, end, interval="1d", asset_class="equity").tail(60)
    prices_b = get_prices(sym_b, start, end, interval="1d", asset_class="equity").tail(60)

    closes = pd.DataFrame({sym_a: prices_a["Close"], sym_b: prices_b["Close"]}).dropna()
    corr = closes.pct_change().corr().iloc[0, 1]
    ctx.narrate(f"Step 1: 30-day return correlation = {corr:.2f}. High correlation suggests spread mean reversion.")

    lookback = 20
    signals_df = pairs_trading_signals(
        closes,
        symA=sym_a,
        symB=sym_b,
        lookback=lookback,
        z_entry=1.0,
        z_exit=0.2,
    )
    spread_tail = signals_df["spread"].tail(lookback)
    beta = np.polyfit(closes[sym_b], closes[sym_a], 1)[0]
    ctx.narrate(f"Step 2: Hedge ratio β ≈ {beta:.2f}; spread = {sym_a} - β·{sym_b}.")
    ctx.narrate(
        f"Step 3: 20-day spread mean = {spread_tail.mean():.2f}; σ = {spread_tail.std(ddof=0):.2f}."
    )

    sig_a = signals_df[f"signal_{sym_a}"]
    zscores = signals_df["zscore"]
    changes = sig_a.diff().fillna(sig_a)
    step = 4
    meaningful = changes[changes != 0]
    if meaningful.empty:
        ctx.narrate(f"Step {step}: Spread never hit ±1.0σ during this slice — patience is part of pairs trading.")
        step += 1
    else:
        for when, delta in meaningful.items():
            sig = sig_a.loc[when]
            if sig == 1:
                action = f"LONG {sym_a} / SHORT {sym_b}"
            elif sig == -1:
                action = f"SHORT {sym_a} / LONG {sym_b}"
            else:
                action = "EXIT spread"
            ctx.narrate(
                f"Step {step}: {action} on {when.date()} because spread z = {zscores.loc[when]:.2f}."
            )
            step += 1

    # Run backtest on leg A to show mechanics of execution costs
    aligned_prices = prices_a.loc[sig_a.index]
    # Evaluate the leg-A equity curve so learners see real execution metrics.
    results = run_backtest(prices=aligned_prices, signals=sig_a.astype(int), asset_class="equity", periods_per_year=252)
    sharpe = results["metrics"].get("Sharpe", float("nan"))
    drawdown = results["metrics"].get("MaxDD", float("nan"))
    if np.isfinite(sharpe):
        ctx.narrate(f"Step {step}: Sharpe (leg A perspective) = {sharpe:.2f}.")
    else:
        ctx.narrate(f"Step {step}: Sharpe undefined — leg A saw little realized PnL in this snippet.")
    step += 1
    if np.isfinite(drawdown):
        ctx.narrate(f"Step {step}: Max Drawdown = {drawdown:.2%}. Pair edges rely on tight risk exits.")
    else:
        ctx.narrate(f"Step {step}: Max Drawdown undefined because equity stayed near zero PnL in this lesson slice.")
    step += 1

    if ctx.plot:
        _maybe_plot(closes[sym_a], sig_a, "Pairs Trading Lesson (leg A)")


def run_lesson(lesson_name: str, plot: bool = False) -> None:
    """Public entry point for CLI and shims."""
    lesson_name = lesson_name.lower().strip()
    if lesson_name not in LESSON_HANDLERS:
        raise ValueError(f"Unknown lesson '{lesson_name}'. Available: {', '.join(available_lessons())}")

    # Pull configuration defaults (dates, logging level, etc.) from .env.
    settings = load_settings()
    setup_logging(settings.log_level)

    # Prepare the per-lesson context so narration, logging, and transcripts stay in sync.
    ctx = LessonContext(lesson=lesson_name, settings=settings, plot=plot, transcript=[])
    LESSON_HANDLERS[lesson_name](ctx)
    transcript_path = _build_transcript_path(ctx.lesson)
    ctx.narrate(f"Transcript archived at {transcript_path}")
    _write_transcript(ctx, transcript_path)


__all__ = ["available_lessons", "run_lesson"]

# logos/tutor/engine.py
# =============================================================================
# Purpose:
#   Power the educational "Tutor Mode" walkthroughs for Logos-Q1.
#   Each lesson fetches real market data, applies existing strategies,
#   and narrates every mathematical step so new traders understand the "why".
#
# Summary:
#   - Provides a reusable LessonContext for logging, transcripts, glossary, and plots
#   - Registers tutorial handlers (mean reversion, momentum, pairs trading)
#   - Reuses project modules: config, data loader, strategies, backtest engine
#   - Narrates formulas (SMA, z-score, correlation, Sharpe, drawdown)
#   - Persists transcripts, glossaries, explain.md, and annotated charts under runs/
#
# Design Philosophy:
#   - Education-first: explain each calculation in approachable language
#   - Zero duplication: rely on shared production code paths for realism
#   - Extensible: add new lessons by decorating functions with @lesson
# =============================================================================
from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple, cast

import numpy as np
import pandas as pd

from ..config import Settings, load_settings
from ..data_loader import get_prices
from ..backtest.engine import run_backtest
from ..strategies.mean_reversion import generate_signals as mean_reversion_signals
from ..strategies.momentum import generate_signals as momentum_signals
from ..strategies.pairs_trading import generate_signals as pairs_trading_signals
from ..utils import ensure_dirs, setup_logging

logger = logging.getLogger(__name__)


@dataclass
class LessonContext:
    """Shared state for a tutor run, tracking narration, files, and flags."""

    lesson: str
    settings: Settings
    plot: bool
    explain_math: bool
    lesson_dir: Path
    run_dir: Path
    plots_dir: Path
    timestamp: str
    transcript: List[str] = field(default_factory=list)
    glossary: List[Dict[str, str]] = field(default_factory=list)
    math_notes: List[str] = field(default_factory=list)
    saved_plots: List[str] = field(default_factory=list)

    def narrate(self, message: str) -> None:
        """Print, log, and record a narration line."""
        print(message)
        logger.info(message)
        self.transcript.append(message)

    def explain(self, title: str, detail: str) -> None:
        """Optionally expand on a formula when --explain-math is enabled."""
        if not self.explain_math:
            return
        block = f"[Math] {title}: {detail}"
        print(block)
        logger.info(block)
        self.transcript.append(block)
        self.math_notes.append(f"### {title}\n{detail}")

    def add_glossary(self, entries: List[Dict[str, str]]) -> None:
        """Store glossary entries and echo them for the learner."""
        if not entries:
            return
        self.glossary.extend(entries)
        self.narrate("Glossary (name | symbol | definition | units):")
        for entry in entries:
            line = f"  {entry['name']:<22} | {entry['symbol']:<8} | {entry['definition']} | {entry['units']}"
            self.narrate(line)

    def add_plot(self, path: Path | str) -> None:
        """Track saved plots and keep the learner informed."""
        location = str(path)
        self.saved_plots.append(location)
        self.narrate(f"Plot saved -> {location}")


# Registry mapping lesson names to callables and descriptions for CLI listings.
LESSON_HANDLERS: Dict[str, Callable[[LessonContext], None]] = {}
LESSON_DESCRIPTIONS: Dict[str, str] = {}


def lesson(
    name: str, description: str
) -> Callable[[Callable[[LessonContext], None]], Callable[[LessonContext], None]]:
    """Decorator to register lesson handlers and their CLI description."""

    def decorator(
        func: Callable[[LessonContext], None]
    ) -> Callable[[LessonContext], None]:
        LESSON_HANDLERS[name] = func
        LESSON_DESCRIPTIONS[name] = description
        return func

    return decorator


def available_lessons() -> List[str]:
    """Return lesson names in sorted order for CLI display."""
    return sorted(LESSON_HANDLERS)


def lesson_catalog() -> List[Tuple[str, str]]:
    """Return (lesson, description) pairs for CLI tables."""
    return [(name, LESSON_DESCRIPTIONS.get(name, "")) for name in available_lessons()]


def _prepare_run_dirs(lesson_name: str) -> tuple[Path, Path, Path, str]:
    """Create lesson/run directories and return (lesson_dir, run_dir, plots_dir, timestamp)."""
    ensure_dirs()
    lessons_root = Path("runs") / "lessons"
    lessons_root.mkdir(parents=True, exist_ok=True)
    lesson_dir = lessons_root / lesson_name
    lesson_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    run_dir = lesson_dir / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    plots_dir = run_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    return lesson_dir, run_dir, plots_dir, stamp


def _format_index_label(label: object) -> str:
    if isinstance(label, pd.Timestamp):
        return label.date().isoformat()
    if isinstance(label, datetime):
        return label.date().isoformat()
    return str(label)


def _summarize_data(ctx: LessonContext, df: pd.DataFrame) -> None:
    """Narrate dataset hygiene stats (rows, range, NaNs, zero-volume bars)."""
    rows = len(df)
    if df.empty:
        start_date = "n/a"
        end_date = "n/a"
    else:
        start_date = _format_index_label(df.index.min())
        end_date = _format_index_label(df.index.max())
    missing_values = int(df.isna().sum().sum())
    zero_volume = int(df["Volume"].eq(0).sum()) if "Volume" in df.columns else "n/a"
    ctx.narrate(
        f"Data summary: {rows} rows from {start_date} to {end_date}; "
        f"missing values={missing_values}; zero-volume bars={zero_volume}."
    )


def _summarize_signals(ctx: LessonContext, signals: pd.Series) -> float:
    """Narrate signal distribution and return exposure ratio."""
    total = len(signals)
    if total == 0:
        ctx.narrate("Signal summary: no observations in this window.")
        return 0.0
    long_count = int((signals > 0).sum())
    short_count = int((signals < 0).sum())
    flat_count = total - long_count - short_count
    exposure_pct = (long_count + short_count) / total * 100.0
    ctx.narrate(
        "Signal summary: "
        f"long {long_count} ({long_count / total:.1%}), "
        f"short {short_count} ({short_count / total:.1%}), "
        f"flat {flat_count} ({flat_count / total:.1%}); exposure ≈ {exposure_pct:.1f}%."
    )
    return exposure_pct / 100.0


def _print_takeaways(
    ctx: LessonContext, metrics: Dict[str, float], equity: pd.Series
) -> None:
    """Summarize three insights after metrics are computed."""
    if equity.empty:
        start_date = "n/a"
        end_date = "n/a"
        worst_point = "n/a"
    else:
        start_date = _format_index_label(equity.index.min())
        end_date = _format_index_label(equity.index.max())
        worst_point = _format_index_label(equity.idxmin())
    cagr = metrics.get("CAGR")
    sharpe = metrics.get("Sharpe")
    max_dd = metrics.get("MaxDD")
    exposure_ratio = metrics.get("Exposure", 0.0)

    if cagr is not None and np.isfinite(cagr):
        ctx.narrate(
            f"Takeaway 1: CAGR {cagr:.2%} across {start_date}–{end_date}; compounding drove overall growth."
        )
    else:
        ctx.narrate(
            "Takeaway 1: CAGR unavailable — insufficient variation in equity curve."
        )

    if sharpe is not None and np.isfinite(sharpe):
        qualitative = (
            "high" if sharpe >= 1.0 else "balanced" if sharpe >= 0.5 else "fragile"
        )
        ctx.narrate(
            f"Takeaway 2: Sharpe {sharpe:.2f} indicates {qualitative} risk-adjusted performance."
        )
    else:
        ctx.narrate(
            "Takeaway 2: Sharpe reset to 0.0 due to degenerate variance — consider richer data."
        )

    if max_dd is not None and np.isfinite(max_dd):
        ctx.narrate(
            f"Takeaway 3: Max drawdown {max_dd:.2%}; pain peaked around {worst_point}."
        )
    else:
        ctx.narrate(
            "Takeaway 3: Max drawdown undefined — equity never dipped below its starting level."
        )

    if exposure_ratio < 0.05:
        ctx.narrate(
            "⚠️ Low exposure (<5%). Consider tuning parameters for more active participation."
        )


def _write_glossary(ctx: LessonContext) -> Optional[str]:
    """Persist glossary JSON for the latest run and copy to lesson root."""
    if not ctx.glossary:
        return None
    run_path = ctx.run_dir / "glossary.json"
    with run_path.open("w", encoding="utf-8") as handle:
        json.dump(ctx.glossary, handle, indent=2)
    lesson_path = ctx.lesson_dir / "glossary.json"
    shutil.copyfile(run_path, lesson_path)
    logger.info("Saved tutor glossary -> %s", run_path)
    return str(run_path)


def _write_explain_md(ctx: LessonContext) -> Optional[str]:
    """Persist markdown of math derivations when requested."""
    if not ctx.explain_math or not ctx.math_notes:
        return None
    path = ctx.run_dir / "explain.md"
    with path.open("w", encoding="utf-8") as handle:
        handle.write("# Math Derivations\n\n")
        for block in ctx.math_notes:
            handle.write(block + "\n\n")
    logger.info("Saved tutor explain.md -> %s", path)
    return str(path)


def _write_transcript(ctx: LessonContext, path: Path) -> None:
    """Persist the lesson transcript to disk."""
    with path.open("w", encoding="utf-8") as handle:
        handle.write("\n".join(ctx.transcript))
    logger.info("Saved tutor transcript -> %s", path)


def _plot_mean_reversion(
    ctx: LessonContext,
    close: pd.Series,
    signals: pd.Series,
    lookback: int,
    zscores: pd.Series,
) -> None:
    """Render price/SMA bands and z-score panel for mean reversion lessons."""
    try:
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("Matplotlib missing; skipping mean reversion plot rendering")
        return

    sma = close.rolling(lookback).mean()
    sigma = close.rolling(lookback).std(ddof=0)
    upper = sma + sigma
    lower = sma - sigma
    changes = signals.diff().fillna(signals)

    fig, (ax_price, ax_z) = plt.subplots(
        2,
        1,
        sharex=True,
        figsize=(12, 6),
        gridspec_kw={"height_ratios": [3, 1]},
    )

    ax_price.plot(
        close.index,
        close.to_numpy(dtype=float, copy=False),
        label="Close",
        color="#60a5fa",
        linewidth=1.4,
    )
    ax_price.plot(
        sma.index,
        sma.to_numpy(dtype=float, copy=False),
        label=f"SMA({lookback})",
        color="#1d4ed8",
        linewidth=1.2,
    )
    ax_price.fill_between(
        close.index,
        upper.to_numpy(dtype=float, copy=False),
        lower.to_numpy(dtype=float, copy=False),
        color="#93c5fd",
        alpha=0.15,
        label="±1σ band",
    )
    event_times: list[pd.Timestamp] = [
        cast(pd.Timestamp, when)
        for when in changes[changes != 0].index
        if isinstance(when, pd.Timestamp)
    ]
    for when in event_times:
        color = "#10b981" if float(signals.loc[when]) > 0 else "#ef4444"
        ax_price.axvline(when, color=color, linestyle="--", alpha=0.35, linewidth=1.0)
    ax_price.set_ylabel("Price")
    ax_price.legend(loc="upper left")
    ax_price.set_title("Mean Reversion Lesson: price vs. SMA ± σ")

    ax_z.plot(
        zscores.index,
        zscores.to_numpy(dtype=float, copy=False),
        color="#6366f1",
        linewidth=1.5,
    )
    ax_z.axhline(1.0, color="#f97316", linestyle="--", alpha=0.7)
    ax_z.axhline(-1.0, color="#f97316", linestyle="--", alpha=0.7)
    ax_z.set_ylabel("z-score")
    ax_z.set_xlabel("Date")
    ax_z.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    ax_z.grid(alpha=0.2)

    fig.tight_layout()
    plot_path = ctx.plots_dir / f"mean_reversion_{ctx.timestamp}.png"
    fig.savefig(plot_path, dpi=150)
    if ctx.plot:
        plt.show()
    plt.close(fig)
    ctx.add_plot(plot_path)


def _plot_momentum(
    ctx: LessonContext,
    close: pd.Series,
    signals: pd.Series,
    sma_fast: pd.Series,
    sma_slow: pd.Series,
) -> None:
    """Render price with moving averages and shaded regime states."""
    try:
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("Matplotlib missing; skipping momentum plot rendering")
        return

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(
        close.index,
        close.to_numpy(dtype=float, copy=False),
        label="Close",
        color="#60a5fa",
        linewidth=1.2,
    )
    ax.plot(
        sma_fast.index,
        sma_fast.to_numpy(dtype=float, copy=False),
        label=f"Fast SMA({sma_fast.name})",
        color="#16a34a",
    )
    ax.plot(
        sma_slow.index,
        sma_slow.to_numpy(dtype=float, copy=False),
        label=f"Slow SMA({sma_slow.name})",
        color="#f97316",
    )

    state = signals.astype(int)
    regime_id = (state != state.shift()).cumsum()
    for _, segment in state.groupby(regime_id):
        val = segment.iloc[0]
        if val == 0:
            continue
        color = "#dcfce7" if val > 0 else "#fee2e2"
        if len(segment.index) == 0:
            continue
    start_time = cast(pd.Timestamp, segment.index[0])
    end_time = cast(pd.Timestamp, segment.index[-1])
    start_val = float(mdates.date2num(start_time.to_pydatetime()))
    end_val = float(mdates.date2num(end_time.to_pydatetime()))
    ax.axvspan(start_val, end_val, color=color, alpha=0.25)

    ax.set_title("Momentum Lesson: crossover regimes")
    ax.set_ylabel("Price")
    ax.set_xlabel("Date")
    ax.legend(loc="upper left")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    ax.grid(alpha=0.2)

    fig.tight_layout()
    plot_path = ctx.plots_dir / f"momentum_{ctx.timestamp}.png"
    fig.savefig(plot_path, dpi=150)
    if ctx.plot:
        plt.show()
    plt.close(fig)
    ctx.add_plot(plot_path)


def _plot_pairs(
    ctx: LessonContext,
    closes: pd.DataFrame,
    signals_df: pd.DataFrame,
    sig_a: pd.Series,
) -> None:
    """Render normalized price legs, spread, and z-score panels for pairs trading."""
    try:
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("Matplotlib missing; skipping pairs plot rendering")
        return

    sym_a, sym_b = closes.columns[:2]
    norm_a = closes[sym_a] / closes[sym_a].iloc[0]
    norm_b = closes[sym_b] / closes[sym_b].iloc[0]
    spread = signals_df["spread"]
    zscores = signals_df["zscore"]
    changes = sig_a.diff().fillna(sig_a)

    fig, (ax_top, ax_mid, ax_bot) = plt.subplots(
        3,
        1,
        sharex=True,
        figsize=(12, 7),
        gridspec_kw={"height_ratios": [3, 2, 1]},
    )

    ax_top.plot(
        norm_a.index,
        norm_a.to_numpy(dtype=float, copy=False),
        label=f"{sym_a} (normalized)",
        color="#0ea5e9",
    )
    ax_top.plot(
        norm_b.index,
        norm_b.to_numpy(dtype=float, copy=False),
        label=f"{sym_b} (normalized)",
        color="#f97316",
    )
    long_shown = False
    short_shown = False
    event_times: list[pd.Timestamp] = [
        cast(pd.Timestamp, when)
        for when in changes[changes != 0].index
        if isinstance(when, pd.Timestamp)
    ]
    for when in event_times:
        val = int(sig_a.loc[when])
        if val == 1:
            label = "Long A / Short B" if not long_shown else None
            ax_top.scatter(
                when,
                float(norm_a.loc[when]),
                marker="^",
                color="#10b981",
                s=60,
                label=label,
            )
            long_shown = True
        elif val == -1:
            label = "Short A / Long B" if not short_shown else None
            ax_top.scatter(
                when,
                float(norm_a.loc[when]),
                marker="v",
                color="#ef4444",
                s=60,
                label=label,
            )
            short_shown = True
    ax_top.set_title("Pairs Trading Lesson: normalized legs")
    ax_top.legend(loc="upper left")

    ax_mid.plot(
        spread.index,
        spread.to_numpy(dtype=float, copy=False),
        color="#4b5563",
        linewidth=1.3,
    )
    ax_mid.axhline(spread.mean(), color="#1d4ed8", linestyle="--", alpha=0.5)
    ax_mid.set_ylabel("Spread")

    ax_bot.plot(
        zscores.index,
        zscores.to_numpy(dtype=float, copy=False),
        color="#6366f1",
        linewidth=1.5,
    )
    ax_bot.axhline(1.0, color="#f97316", linestyle="--", alpha=0.7)
    ax_bot.axhline(-1.0, color="#f97316", linestyle="--", alpha=0.7)
    ax_bot.set_ylabel("z-score")
    ax_bot.set_xlabel("Date")
    ax_bot.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    ax_bot.grid(alpha=0.2)

    fig.tight_layout()
    plot_path = ctx.plots_dir / f"pairs_trading_{ctx.timestamp}.png"
    fig.savefig(plot_path, dpi=150)
    if ctx.plot:
        plt.show()
    plt.close(fig)
    ctx.add_plot(plot_path)


@lesson("mean_reversion", "Fade z-score extremes on a single asset.")
def _lesson_mean_reversion(ctx: LessonContext) -> None:
    symbol = "MSFT"
    ctx.narrate(
        f"[Lesson: Mean Reversion] Using {symbol} daily bars to illustrate z-score fades."
    )

    start, end = ctx.settings.start, ctx.settings.end
    prices = get_prices(symbol, start, end, interval="1d", asset_class="equity").tail(
        60
    )
    _summarize_data(ctx, prices)
    close = prices["Close"].astype(float)

    lookback = 10
    window = close.tail(lookback)
    sma = window.mean()
    sigma = window.std(ddof=0)
    last_price = close.iloc[-1]
    z_value = (last_price - sma) / sigma

    ctx.add_glossary(
        [
            {
                "name": "Lookback window",
                "symbol": "n",
                "definition": "Bars used for rolling stats",
                "units": "bars",
            },
            {
                "name": "Rolling mean",
                "symbol": "μ_t",
                "definition": "Average price across the last n bars",
                "units": "price",
            },
            {
                "name": "Rolling std dev",
                "symbol": "σ_t",
                "definition": "Volatility of price over the last n bars",
                "units": "price",
            },
            {
                "name": "Z-score",
                "symbol": "z_t",
                "definition": "Standardized distance from the rolling mean",
                "units": "σ",
            },
            {
                "name": "Price",
                "symbol": "p_t",
                "definition": "Closing price at time t",
                "units": "price",
            },
        ]
    )

    ctx.narrate(
        f"Step 1: {lookback}-day SMA = mean({window.min():.2f}…{window.max():.2f}) = {sma:.2f}"
    )
    ctx.narrate(
        f"Step 2: σ (population std) = {sigma:.2f}; latest Close = {last_price:.2f}"
    )
    ctx.narrate(
        f"Step 3: z = (Price - SMA) / σ = ({last_price:.2f} - {sma:.2f}) / {sigma:.2f} = {z_value:.2f}"
    )

    ctx.explain(
        "Simple Moving Average", f"SMA_t = (1/n) Σ p_i over the last {lookback} bars."
    )
    ctx.explain(
        "Rolling Standard Deviation",
        "σ_t = sqrt((1/n) Σ (p_i - μ_t)^2), capturing dispersion around the mean.",
    )
    ctx.explain(
        "Z-score", "z_t measures how many standard deviations p_t sits away from μ_t."
    )

    signals = mean_reversion_signals(prices, lookback=lookback, z_entry=1.0)
    zscores = (close - close.rolling(lookback).mean()) / close.rolling(lookback).std(
        ddof=0
    )
    _summarize_signals(ctx, signals)

    changes = signals.diff().fillna(signals)
    step = 4
    meaningful = changes[changes != 0]
    if meaningful.empty:
        ctx.narrate(
            f"Step {step}: No trades fired in this window; prices stayed within ±1.0σ of the mean."
        )
        step += 1
    else:
        event_times: list[pd.Timestamp] = [
            cast(pd.Timestamp, when)
            for when in meaningful.index
            if isinstance(when, pd.Timestamp)
        ]
        for when in event_times:
            sig = int(signals.loc[when])
            tag = "BUY" if sig == 1 else "SELL" if sig == -1 else "EXIT"
            reason = "reversion opportunity" if sig else "mean hit"
            z_at = float(zscores.loc[when])
            ctx.narrate(
                f"Step {step}: {tag} {'entry' if sig else 'flat'} at {float(close.loc[when]):.2f} on {when.date()} "
                f"because z = {z_at:.2f} → {reason}."
            )
            step += 1

    results = run_backtest(
        prices=prices, signals=signals, asset_class="equity", periods_per_year=252
    )
    returns_std = results["returns"].std()
    if np.isclose(returns_std, 0.0):
        ctx.narrate(
            "Sharpe variance guard: returns variance was zero, so Sharpe was reset to 0.0."
        )
    warnings = cast(Iterable[str], results.get("warnings", []))
    for note in warnings:
        ctx.narrate(f"Warning: {note}")
    _print_takeaways(ctx, results["metrics"], results["equity_curve"])

    if ctx.plot:
        _plot_mean_reversion(ctx, close, signals, lookback, zscores)


@lesson("momentum", "Ride fast/slow SMA crossovers for trend following.")
def _lesson_momentum(ctx: LessonContext) -> None:
    symbol = "BTC-USD"
    ctx.narrate(f"[Lesson: Momentum] Tracking trend-following crossovers on {symbol}.")

    start, end = ctx.settings.start, ctx.settings.end
    prices = get_prices(symbol, start, end, interval="1d", asset_class="crypto").tail(
        90
    )
    _summarize_data(ctx, prices)
    close = prices["Close"].astype(float)

    fast, slow = 5, 15
    sma_fast = close.rolling(fast).mean().rename(fast)
    sma_slow = close.rolling(slow).mean().rename(slow)
    ctx.explain(
        "Momentum Signal",
        "Signal = sign(SMA_fast - SMA_slow); crossovers flag regime shifts.",
    )

    ctx.add_glossary(
        [
            {
                "name": "Fast moving average",
                "symbol": "SMA_f",
                "definition": f"Mean of last {fast} closes",
                "units": "price",
            },
            {
                "name": "Slow moving average",
                "symbol": "SMA_s",
                "definition": f"Mean of last {slow} closes",
                "units": "price",
            },
            {
                "name": "Signal",
                "symbol": "s_t",
                "definition": "Direction derived from SMA_f - SMA_s",
                "units": "{-1,0,+1}",
            },
        ]
    )

    ctx.narrate(
        f"Step 1: Fast SMA({fast}) = {close.tail(fast).mean():.2f}; Slow SMA({slow}) = {close.tail(slow).mean():.2f} → crossover check."
    )
    ctx.narrate(
        f"Step 2: Last Close {close.iloc[-1]:.2f} sits {'above' if sma_fast.iloc[-1] > sma_slow.iloc[-1] else 'below'} slow SMA → trend signal."
    )

    signals = momentum_signals(prices, fast=fast, slow=slow)
    _summarize_signals(ctx, signals)

    changes = signals.diff().fillna(signals)
    step = 3
    meaningful = changes[changes != 0]
    if meaningful.empty:
        ctx.narrate(
            f"Step {step}: No crossover yet — trend filter still neutral in this sample."
        )
        step += 1
    else:
        event_times: list[pd.Timestamp] = [
            cast(pd.Timestamp, when)
            for when in meaningful.index
            if isinstance(when, pd.Timestamp)
        ]
        for when in event_times:
            sig = int(signals.loc[when])
            direction = "LONG" if sig == 1 else "SHORT" if sig == -1 else "FLAT"
            ctx.narrate(
                f"Step {step}: {direction} on {when.date()} because SMA({fast}) {'>' if sig == 1 else '<' if sig == -1 else '≈'} "
                f"SMA({slow}). Price={float(close.loc[when]):.2f}."
            )
            step += 1

    results = run_backtest(
        prices=prices, signals=signals, asset_class="crypto", periods_per_year=365
    )
    returns_std = results["returns"].std()
    if np.isclose(returns_std, 0.0):
        ctx.narrate(
            "Sharpe variance guard: returns variance was zero, so Sharpe was reset to 0.0."
        )
    warnings = cast(Iterable[str], results.get("warnings", []))
    for note in warnings:
        ctx.narrate(f"Warning: {note}")
    _print_takeaways(ctx, results["metrics"], results["equity_curve"])

    if ctx.plot:
        _plot_momentum(ctx, close, signals, sma_fast, sma_slow)


@lesson("pairs_trading", "Trade the spread between two correlated assets.")
def _lesson_pairs(ctx: LessonContext) -> None:
    sym_a, sym_b = "MSFT", "AAPL"
    ctx.narrate(
        f"[Lesson: Pairs Trading] Comparing {sym_a} vs {sym_b} to trade their spread."
    )

    start, end = ctx.settings.start, ctx.settings.end
    prices_a = get_prices(sym_a, start, end, interval="1d", asset_class="equity").tail(
        90
    )
    prices_b = get_prices(sym_b, start, end, interval="1d", asset_class="equity").tail(
        90
    )
    closes = pd.DataFrame({sym_a: prices_a["Close"], sym_b: prices_b["Close"]}).dropna()
    _summarize_data(ctx, closes)

    corr = closes.pct_change().corr().iloc[0, 1]
    ctx.narrate(
        f"Step 1: 30-day return correlation = {corr:.2f}. High correlation suggests spread mean reversion."
    )

    lookback = 20
    ctx.add_glossary(
        [
            {
                "name": "Hedge ratio",
                "symbol": "β",
                "definition": "OLS slope linking A to B",
                "units": "ratio",
            },
            {
                "name": "Spread",
                "symbol": "spread_t",
                "definition": "A - β·B residual",
                "units": "price",
            },
            {
                "name": "Z-score",
                "symbol": "z_t",
                "definition": "Spread normalized by its σ",
                "units": "σ",
            },
            {
                "name": "Price",
                "symbol": "p_t",
                "definition": "Closing leg price",
                "units": "price",
            },
        ]
    )
    ctx.explain(
        "Hedge Ratio",
        "β estimated via ordinary least squares between the two price series.",
    )
    ctx.explain(
        "Pair Spread",
        "spread_t = p^A_t - β p^B_t captures divergence from the equilibrium line.",
    )

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
        f"Step 3: {lookback}-day spread mean = {spread_tail.mean():.2f}; σ = {spread_tail.std(ddof=0):.2f}."
    )

    sig_a = signals_df[f"signal_{sym_a}"]
    _summarize_signals(ctx, sig_a)

    changes = sig_a.diff().fillna(sig_a)
    step = 4
    meaningful = changes[changes != 0]
    if meaningful.empty:
        ctx.narrate(
            "Step 4: Spread never hit ±1.0σ during this slice — patience is part of pairs trading."
        )
        step += 1
    else:
        event_times: list[pd.Timestamp] = [
            cast(pd.Timestamp, when)
            for when in meaningful.index
            if isinstance(when, pd.Timestamp)
        ]
        for when in event_times:
            sig = int(sig_a.loc[when])
            if sig == 1:
                action = f"LONG {sym_a} / SHORT {sym_b}"
            elif sig == -1:
                action = f"SHORT {sym_a} / LONG {sym_b}"
            else:
                action = "EXIT spread"
            ctx.narrate(
                f"Step {step}: {action} on {when.date()} because spread z = {float(signals_df['zscore'].loc[when]):.2f}."
            )
            step += 1

    aligned_prices = prices_a.loc[sig_a.index]
    results = run_backtest(
        prices=aligned_prices,
        signals=sig_a.astype(int),
        asset_class="equity",
        periods_per_year=252,
    )
    returns_std = results["returns"].std()
    if np.isclose(returns_std, 0.0):
        ctx.narrate(
            "Sharpe variance guard: returns variance was zero, so Sharpe was reset to 0.0."
        )
    warnings = cast(Iterable[str], results.get("warnings", []))
    for note in warnings:
        ctx.narrate(f"Warning: {note}")
    _print_takeaways(ctx, results["metrics"], results["equity_curve"])

    if ctx.plot:
        _plot_pairs(ctx, closes.loc[sig_a.index], signals_df.loc[sig_a.index], sig_a)


def run_lesson(
    lesson_name: str, plot: bool = False, explain_math: bool = False
) -> None:
    """Public entry point for CLI and shims."""
    lesson_key = lesson_name.lower().strip()
    if lesson_key not in LESSON_HANDLERS:
        raise ValueError(
            f"Unknown lesson '{lesson_name}'. Available: {', '.join(available_lessons())}"
        )

    lesson_dir_raw, run_dir_raw, plots_dir_raw, stamp = _prepare_run_dirs(lesson_key)
    lesson_dir = Path(lesson_dir_raw)
    run_dir = Path(run_dir_raw)
    plots_dir = Path(plots_dir_raw)
    settings = load_settings()
    setup_logging(settings.log_level)

    ctx = LessonContext(
    lesson=lesson_key,
    settings=settings,
    plot=plot,
    explain_math=explain_math,
    lesson_dir=lesson_dir,
    run_dir=run_dir,
    plots_dir=plots_dir,
    timestamp=stamp,
    )

    LESSON_HANDLERS[lesson_key](ctx)

    glossary_path = _write_glossary(ctx)
    explain_path = _write_explain_md(ctx)
    transcript_path = ctx.run_dir / "transcript.txt"

    if glossary_path:
        ctx.narrate(f"Glossary saved -> {glossary_path}")
    if explain_path:
        ctx.narrate(f"Explain sheet saved -> {explain_path}")
    ctx.narrate(f"Transcript location: {transcript_path}")
    _write_transcript(ctx, transcript_path)


__all__ = ["available_lessons", "lesson_catalog", "run_lesson"]

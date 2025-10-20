from __future__ import annotations

from typing import Any, Dict

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from logos.paths import DATA_RAW_DIR
from . import LessonContext

FIXTURE = DATA_RAW_DIR / "fixtures" / "momentum_ohlcv.csv"


def _load_fixture() -> pd.DataFrame:
    """Return a deterministic price series for the lesson."""
    if FIXTURE.exists():
        df = pd.read_csv(FIXTURE, parse_dates=["dt"])
        return df.sort_values("dt").reset_index(drop=True)

    rng = np.random.default_rng(21)
    periods = 250
    dt = pd.date_range("2023-01-01", periods=periods, freq="D", tz="UTC")
    trend = np.linspace(0, 15, periods)
    noise = rng.normal(scale=2.0, size=periods).cumsum()
    prices = 100 + trend + noise
    df = pd.DataFrame(
        {
            "dt": dt,
            "close": prices,
            "high": prices + rng.uniform(0.2, 1.5, size=periods),
            "low": prices - rng.uniform(0.2, 1.5, size=periods),
            "open": prices + rng.normal(scale=0.7, size=periods),
            "volume": rng.integers(50_000, 150_000, size=periods),
        }
    )
    return df


def build_glossary(explain_math: bool) -> Dict[str, Any]:
    glossary: Dict[str, Any] = {
        "momentum": "The rate of change of price over a lookback window.",
        "lookback_fast": "Short moving average window capturing recent trend.",
        "lookback_slow": "Long moving average window capturing prevailing trend.",
        "crossover": "When the fast average crosses the slow average, signalling shifts in momentum.",
    }
    if explain_math:
        glossary["formulas"] = {
            "ema": "EMA_t = EMA_{t-1} + k * (price_t - EMA_{t-1})",
            "roc": "ROC_t = price_t / price_{t-L} - 1",
        }
    return glossary


def generate_transcript(glossary: Dict[str, Any], explain_math: bool) -> str:
    lines = [
        "Lesson: Momentum",
        "- Compare short- and long-term moving averages to detect regime shifts.",
        "- Stay long when the fast average is above the slow average; short when below.",
    ]
    if explain_math and "formulas" in glossary:
        ema_formula = glossary["formulas"].get("ema")
        if ema_formula:
            lines.append(f"- Exponential moving average update: {ema_formula}")
    return "\n".join(lines) + "\n"


def generate_plots(ctx: LessonContext) -> None:
    df = _load_fixture()
    df = df.sort_values("dt").reset_index(drop=True)
    close = df["close"].astype(float)

    fast = close.ewm(span=20, adjust=False).mean()
    slow = close.ewm(span=60, adjust=False).mean()

    crosses_up = (fast > slow) & (fast.shift(1) <= slow.shift(1))
    crosses_down = (fast < slow) & (fast.shift(1) >= slow.shift(1))

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df["dt"], close, label="Close", color="steelblue")
    ax.plot(df["dt"], fast, label="EMA 20", color="green", alpha=0.8)
    ax.plot(df["dt"], slow, label="EMA 60", color="orange", alpha=0.8)
    ax.scatter(
        df.loc[crosses_up, "dt"],
        close[crosses_up],
        marker="^",
        color="green",
        label="Bullish crossover",
    )
    ax.scatter(
        df.loc[crosses_down, "dt"],
        close[crosses_down],
        marker="v",
        color="red",
        label="Bearish crossover",
    )
    ax.set_title("Momentum Lesson: EMA Crossovers")
    ax.set_xlabel("Date")
    ax.set_ylabel("Price")
    ax.legend(loc="best")
    fig.tight_layout()

    out = ctx.plots_dir / "momentum_crossovers.png"
    fig.savefig(out, dpi=144, bbox_inches="tight")
    plt.close(fig)
    ctx.logger.info("Saved momentum plot to %s", out)

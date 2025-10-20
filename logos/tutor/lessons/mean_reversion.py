from __future__ import annotations

from typing import Dict, Any

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from logos.paths import DATA_RAW_DIR
from . import LessonContext

FIXTURE = DATA_RAW_DIR / "fixtures" / "mean_reversion_ohlcv.csv"


def _load_fixture() -> pd.DataFrame:
    # Tiny committed CSV expected at data/raw/fixtures/mean_reversion_ohlcv.csv
    # If missing, synthesize a deterministic series.
    if FIXTURE.exists():
        df = pd.read_csv(FIXTURE, parse_dates=["dt"])
        return df.sort_values("dt").reset_index(drop=True)
    # Synthetic fallback (deterministic)
    rng = np.random.default_rng(42)
    n = 400
    dt = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    prices = 100 + np.cumsum(rng.normal(0, 1, size=n))
    df = pd.DataFrame(
        {
            "dt": dt,
            "open": prices,
            "high": prices + 0.5,
            "low": prices - 0.5,
            "close": prices,
            "volume": 1000,
        }
    )
    return df


def build_glossary(explain_math: bool) -> Dict[str, Any]:
    g = {
        "zscore": "Standardized price deviation from moving average.",
        "lookback": "Window length for moving average and std.",
        "entry_threshold": "Absolute z-score threshold for entry.",
        "exit_threshold": "Z-score threshold to close positions.",
    }
    if explain_math:
        g["formulas"] = {
            "zscore": "z_t = (p_t - MA_t) / std_t",
            "MA_t": "MA_t = mean(p_{t-L+1}..p_t)",
            "std_t": "Standard deviation over the same window",
        }
    return g


def generate_transcript(glossary: Dict[str, Any], explain_math: bool) -> str:
    parts = [
        "Lesson: Mean Reversion",
        "- Compute rolling mean/std and convert price to a z-score.",
        "- Enter when |z| >= entry_threshold; exit when |z| <= exit_threshold.",
    ]
    if explain_math and "formulas" in glossary:
        parts.append(f"- Formula: {glossary['formulas']['zscore']}")
    return "\n".join(parts) + "\n"


def generate_plots(ctx: LessonContext) -> None:
    df = _load_fixture()
    L = 50
    thr_in = 2.0
    thr_out = 0.5

    df = df.sort_values("dt").reset_index(drop=True)
    df["ma"] = df["close"].rolling(L).mean()
    df["std"] = df["close"].rolling(L).std()
    df["z"] = (df["close"] - df["ma"]) / df["std"]

    entries = df.index[(df["z"].abs() >= thr_in)]
    exits = df.index[(df["z"].abs() <= thr_out)]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df["dt"], df["close"], label="Close")
    ax.plot(df["dt"], df["ma"], label=f"MA({L})", alpha=0.8)
    ax.scatter(
        df.loc[entries, "dt"],
        df.loc[entries, "close"],
        marker="^",
        color="green",
        label="Entries",
    )
    ax.scatter(
        df.loc[exits, "dt"],
        df.loc[exits, "close"],
        marker="v",
        color="red",
        label="Exits",
    )
    ax.legend()
    ax.set_title("Mean Reversion Lesson: Annotated Entries/Exits")

    out = ctx.plots_dir / "annotated_mean_reversion.png"
    fig.savefig(out, dpi=144, bbox_inches="tight")
    plt.close(fig)

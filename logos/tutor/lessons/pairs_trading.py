from __future__ import annotations

from typing import Any, Dict

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from logos.paths import DATA_RAW_DIR
from . import LessonContext

FIXTURE_A = DATA_RAW_DIR / "fixtures" / "pairs_A.csv"
FIXTURE_B = DATA_RAW_DIR / "fixtures" / "pairs_B.csv"


def _load_pair() -> pd.DataFrame:
    if FIXTURE_A.exists() and FIXTURE_B.exists():
        a = pd.read_csv(FIXTURE_A, parse_dates=["dt"]).rename(columns={"close": "A"})
        b = pd.read_csv(FIXTURE_B, parse_dates=["dt"]).rename(columns={"close": "B"})
        df = a.merge(b, on="dt", how="inner")
        return df.sort_values("dt").reset_index(drop=True)

    rng = np.random.default_rng(314)
    periods = 300
    dt = pd.date_range("2022-01-01", periods=periods, freq="D", tz="UTC")
    base = np.cumsum(rng.normal(scale=1.0, size=periods))
    series_a = 100 + base + rng.normal(scale=0.5, size=periods)
    series_b = 95 + 0.98 * base + rng.normal(scale=0.5, size=periods)
    df = pd.DataFrame({"dt": dt, "A": series_a, "B": series_b})
    return df


def build_glossary(explain_math: bool) -> Dict[str, Any]:
    glossary: Dict[str, Any] = {
        "spread": "Difference between two correlated assets (A - beta * B).",
        "hedge_ratio": "Scaling applied to the second asset to neutralize trend.",
        "zscore": "Standardized spread used for entries and exits.",
    }
    if explain_math:
        glossary["formulas"] = {
            "spread": "spread_t = price_A_t - beta * price_B_t",
            "zscore": "z_t = (spread_t - mean(spread)) / std(spread)",
        }
    return glossary


def generate_transcript(glossary: Dict[str, Any], explain_math: bool) -> str:
    lines = [
        "Lesson: Pairs Trading",
        "- Identify two assets that move together historically.",
        "- Trade deviations in the spread expecting mean reversion.",
    ]
    if explain_math and "formulas" in glossary:
        spread_formula = glossary["formulas"].get("spread")
        if spread_formula:
            lines.append(f"- Spread definition: {spread_formula}")
    return "\n".join(lines) + "\n"


def generate_plots(ctx: LessonContext) -> None:
    df = _load_pair()
    df = df.sort_values("dt").reset_index(drop=True)
    hedge_ratio = np.polyfit(df["B"], df["A"], 1)[0]
    spread = df["A"] - hedge_ratio * df["B"]
    z = (spread - spread.rolling(40).mean()) / spread.rolling(40).std(ddof=0)

    fig, (ax_price, ax_spread) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    ax_price.plot(df["dt"], df["A"], label="Asset A", color="tab:blue")
    ax_price.plot(df["dt"], df["B"], label="Asset B", color="tab:orange")
    ax_price.set_title("Pairs Trading Lesson: Price Relationship")
    ax_price.legend(loc="best")

    ax_spread.plot(df["dt"], spread, label="Spread", color="tab:purple")
    ax_spread.plot(
        df["dt"],
        spread.rolling(40).mean(),
        label="Rolling Mean",
        color="black",
        linestyle="--",
    )
    ax_spread.fill_between(
        df["dt"], z * 0 + 2, 2, color="red", alpha=0.1, label="+2σ threshold"
    )
    ax_spread.fill_between(
        df["dt"], z * 0 - 2, -2, color="green", alpha=0.1, label="-2σ threshold"
    )
    ax_spread.set_title("Spread and Entry Thresholds")
    ax_spread.legend(loc="best")
    fig.tight_layout()

    out = ctx.plots_dir / "pairs_spread.png"
    fig.savefig(out, dpi=144, bbox_inches="tight")
    plt.close(fig)
    ctx.logger.info("Saved pairs trading plot to %s", out)

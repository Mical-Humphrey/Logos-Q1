from __future__ import annotations

import json
from collections import deque

import numpy as np
import pandas as pd

from logos.research.tune import TuningConfig, tune_parameters


def _synthetic_prices(rows: int = 160) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=rows, freq="D")
    base = 100.0 + np.linspace(0.0, 3.0, rows)
    noise = 0.5 * np.sin(np.linspace(0.0, 8.0, rows))
    close = base + noise
    frame = pd.DataFrame(
        {
            "Open": close + 0.1,
            "High": close + 0.4,
            "Low": close - 0.4,
            "Close": close,
            "Adj Close": close,
            "Volume": np.full(rows, 1_000.0),
        },
        index=index,
    )
    frame.index.name = "Date"
    return frame


def test_tuning_outputs_and_gates(tmp_path, monkeypatch) -> None:
    prices = _synthetic_prices()

    # Pre-programmed backtest responses: for each trial we expect
    # train -> oos -> stress. Guard metrics rely on the OOS returns series.
    def _result(
        *,
        index: pd.DatetimeIndex,
        sharpe: float,
        maxdd: float,
        cagr: float,
        returns_level: float = 0.01,
    ):
        returns = pd.Series(np.full(index.size, returns_level), index=index)
        equity = pd.Series(np.linspace(1.0, 2.0, index.size), index=index)
        positions = pd.Series(0.0, index=index)
        return {
            "metrics": {"Sharpe": sharpe, "MaxDD": maxdd, "CAGR": cagr},
            "returns": returns,
            "equity_curve": equity,
            "positions": positions,
            "trades": pd.DataFrame(columns=["time", "side", "shares", "ref_close"]),
        }

    plan = deque(
        [
            # Trial 1 (accepted)
            (0.8, -0.2, 0.12),  # train metrics
            (0.65, -0.15, 0.08),  # oos metrics
            (0.40, -0.25, 0.02),  # stress metrics
            # Trial 2 (rejected due to oos Sharpe)
            (0.9, -0.2, 0.10),
            (0.20, -0.10, 0.05),
            (0.10, -0.20, 0.03),
        ]
    )

    def fake_backtest(*, prices: pd.DataFrame, **_) -> dict:
        sharpe, maxdd, cagr = plan.popleft()
        return _result(index=prices.index, sharpe=sharpe, maxdd=maxdd, cagr=cagr)

    monkeypatch.setattr("logos.research.tune.run_backtest", fake_backtest)

    config = TuningConfig(
        strategy="momentum",
        symbol="DEMO",
        interval="1d",
        asset_class="equity",
        param_grid={"fast": [8, 12], "slow": [20]},
        oos_fraction=0.2,
        min_oos_sharpe=0.5,
        max_oos_drawdown=-0.3,
        top_n=3,
    )

    result = tune_parameters(prices, config, output_dir=tmp_path)

    summary_path = tmp_path / "summary.json"
    overview_html = tmp_path / "overview.html"
    overview_md = tmp_path / "overview.md"
    trials_csv = tmp_path / "trials.csv"
    trials_top_csv = tmp_path / "trials_top.csv"

    assert summary_path.exists()
    assert overview_html.exists()
    assert overview_md.exists()
    assert trials_csv.exists()
    assert trials_top_csv.exists()

    accepted = result.accepted()
    assert len(accepted) == 1
    assert accepted[0].params["fast"] == 8

    payload = json.loads(summary_path.read_text())
    assert payload["best_params"] == accepted[0].params

    html = overview_html.read_text()
    assert "Tuning Report" in html
    assert "Trial Summary" in html

    markdown = overview_md.read_text()
    assert "## Accepted Trials" in markdown

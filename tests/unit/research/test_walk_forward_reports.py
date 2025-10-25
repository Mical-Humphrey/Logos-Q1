from __future__ import annotations

import json

import numpy as np
import pandas as pd

from logos.research.walk_forward import WalkForwardConfig, run_walk_forward


def _synthetic_prices(rows: int = 180) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=rows, freq="D")
    base = 100.0 + np.linspace(0.0, 5.0, rows)
    noise = np.sin(np.linspace(0.0, 12.0, rows))
    close = base + noise
    frame = pd.DataFrame(
        {
            "Open": close + 0.1,
            "High": close + 0.3,
            "Low": close - 0.3,
            "Close": close,
            "Adj Close": close,
            "Volume": np.full(rows, 1_000.0),
        },
        index=index,
    )
    frame.index.name = "Date"
    return frame


def test_walk_forward_outputs(tmp_path) -> None:
    prices = _synthetic_prices()
    config = WalkForwardConfig(
        strategy="momentum",
        symbol="DEMO",
        window_size=90,
        train_fraction=0.6,
        params={"fast": 10, "slow": 30},
    )

    report = run_walk_forward(prices, config, output_dir=tmp_path)

    summary_path = tmp_path / "summary.json"
    overview_html = tmp_path / "overview.html"
    overview_md = tmp_path / "overview.md"
    windows_csv = tmp_path / "windows.csv"

    assert summary_path.exists()
    assert overview_html.exists()
    assert overview_md.exists()
    assert windows_csv.exists()
    assert report.windows, "expected at least one evaluated window"

    payload = json.loads(summary_path.read_text())
    assert payload["aggregate"], "aggregate metrics missing from summary"

    html = overview_html.read_text()
    assert "Walk-Forward Report" in html
    assert "Window Details" in html

    markdown = overview_md.read_text()
    assert "## Guard Failures" in markdown

import json
from pathlib import Path

import pandas as pd
import pytest

from logos.tutor import engine as tutor_engine


class DummySettings:
    start = "2024-01-01"
    end = "2024-01-31"
    log_level = "INFO"


@pytest.fixture
def tutor_run_tmp(tmp_path, monkeypatch):
    def fake_prepare(lesson_name: str):
        lesson_dir = tmp_path / "lessons" / lesson_name
        run_dir = lesson_dir / "20240101-000000"
        plots_dir = run_dir / "plots"
        plots_dir.mkdir(parents=True, exist_ok=True)
        return str(lesson_dir), str(run_dir), str(plots_dir), "20240101-000000"

    monkeypatch.setattr(tutor_engine, "_prepare_run_dirs", fake_prepare)
    monkeypatch.setattr(tutor_engine, "load_settings", lambda: DummySettings())
    monkeypatch.setattr(tutor_engine, "setup_logging", lambda level: None)

    def fake_prices(symbol, start, end, interval="1d", asset_class="equity"):
        dates = pd.date_range(start, periods=30, freq="D")
        base = {
            "Open": pd.Series(range(100, 130), index=dates).astype(float),
            "High": pd.Series(range(101, 131), index=dates).astype(float),
            "Low": pd.Series(range(99, 129), index=dates).astype(float),
            "Close": pd.Series(range(100, 130), index=dates).astype(float),
            "Adj Close": pd.Series(range(100, 130), index=dates).astype(float),
            "Volume": pd.Series([1_000] * 30, index=dates).astype(float),
        }
        df = pd.DataFrame(base)
        if asset_class == "equity" and symbol in {"MSFT", "AAPL"}:
            return df
        if asset_class == "crypto":
            return df
        return df

    monkeypatch.setattr(tutor_engine, "get_prices", fake_prices)

    def fake_run_backtest(**kwargs):
        idx = kwargs["prices"].index
        return {
            "returns": pd.Series([0.0] * len(idx), index=idx),
            "equity_curve": pd.Series(range(len(idx)), index=idx, dtype=float),
            "trades": pd.DataFrame(
                {"time": [], "side": [], "shares": [], "ref_close": []}
            ),
            "metrics": {"CAGR": 0.1, "Sharpe": 1.0, "MaxDD": -0.05, "Exposure": 0.2},
            "warnings": [],
        }

    monkeypatch.setattr(tutor_engine, "run_backtest", fake_run_backtest)

    return tmp_path


def test_run_lesson_writes_artifacts(tutor_run_tmp):
    tutor_engine.run_lesson("mean_reversion", plot=False, explain_math=True)

    run_dir = Path(tutor_run_tmp) / "lessons" / "mean_reversion" / "20240101-000000"

    transcript = run_dir / "transcript.txt"
    glossary = run_dir / "glossary.json"
    explain = run_dir / "explain.md"

    assert transcript.exists()
    assert glossary.exists()
    assert explain.exists()

    glossary_payload = json.loads(glossary.read_text(encoding="utf-8"))
    assert len(glossary_payload) > 0
    assert all("name" in entry for entry in glossary_payload)

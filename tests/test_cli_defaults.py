from argparse import Namespace
import json
from pathlib import Path

import pandas as pd
import pytest

from logos.cli import Settings, cmd_backtest


@pytest.fixture
def dummy_settings() -> Settings:
    return Settings(
        start="2024-01-01",
        end="2024-01-10",
        symbol="MSFT",
        log_level="INFO",
        asset_class="equity",
        commission_per_share=0.0035,
        slippage_bps=1.0,
    )


def test_cmd_backtest_writes_run_artifacts(tmp_path, monkeypatch, dummy_settings):
    run_dir = tmp_path / "runs" / "test_run"
    (run_dir / "logs").mkdir(parents=True)

    monkeypatch.setattr("logos.cli._create_run_dir", lambda symbol, strategy: str(run_dir))
    monkeypatch.setattr("logos.cli.setup_logging", lambda level: None)
    monkeypatch.setattr("logos.cli.ensure_dirs", lambda: None)

    dates = pd.date_range("2024-01-01", periods=4, freq="D")
    price_df = pd.DataFrame({"Close": [100.0, 101.0, 102.0, 103.0]}, index=dates)
    price_df.index.name = "Date"
    monkeypatch.setattr("logos.cli.get_prices", lambda *args, **kwargs: price_df)

    signals = pd.Series([0, 1, 0, -1], index=dates)

    def fake_strategy(data, **params):
        return signals

    monkeypatch.setattr("logos.cli.STRATEGIES", {"mean_reversion": fake_strategy})

    returns = pd.Series([0.0, 0.01, -0.005, 0.002], index=dates)
    equity = pd.Series([1_0000.0, 1_0100.0, 1_0050.0, 1_0070.0], index=dates)
    trades = pd.DataFrame(
        {
            "time": [dates[1], dates[3]],
            "side": [1, -1],
            "shares": [10, -10],
            "ref_close": [101.0, 103.0],
        }
    )
    metrics = {"CAGR": 0.15, "Sharpe": 1.25, "MaxDD": -0.04, "WinRate": 0.6, "Exposure": 0.5}

    def fake_run_backtest(**kwargs):
        return {
            "returns": returns,
            "equity_curve": equity,
            "trades": trades,
            "metrics": metrics,
            "warnings": [],
        }

    monkeypatch.setattr("logos.cli.run_backtest", fake_run_backtest)

    args = Namespace(
        symbol="MSFT",
        strategy="mean_reversion",
        start=None,
        end=None,
        asset_class="equity",
        interval="1d",
        dollar_per_trade=10_000.0,
        slip_bps=1.0,
        commission=0.0035,
        fee_bps=5.0,
        fx_pip_size=0.0001,
        params=None,
        paper=False,
    )

    cmd_backtest(args, settings=dummy_settings)

    config_path = run_dir / "config.yaml"
    metrics_path = run_dir / "metrics.json"
    trades_path = run_dir / "trades.csv"
    equity_path = run_dir / "equity.png"
    log_path = run_dir / "logs" / "run.log"

    assert config_path.exists()
    assert metrics_path.exists()
    assert trades_path.exists()
    assert equity_path.exists()
    assert log_path.exists()

    config_text = config_path.read_text(encoding="utf-8")
    assert "symbol: MSFT" in config_text
    assert "strategy: mean_reversion" in config_text

    metrics_payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert metrics_payload["Sharpe"] == pytest.approx(1.25)

    trades_file = trades_path.read_text(encoding="utf-8")
    assert "ref_close" in trades_file

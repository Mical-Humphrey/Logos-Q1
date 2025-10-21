import json
import logging
from argparse import Namespace
from typing import Dict

import pandas as pd
import pytest

from logos.cli import Settings, cmd_backtest
from logos.run_manager import RunContext
from logos.window import Window


@pytest.fixture
def base_settings() -> Settings:
    return Settings(
        start="2024-01-01",
        end="2024-01-10",
        symbol="MSFT",
        log_level="INFO",
        asset_class="equity",
        commission_per_share=0.0035,
        slippage_bps=1.0,
    )


def _prep_run_context(tmp_path, name: str) -> RunContext:
    run_dir = tmp_path / name
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return RunContext(
        run_id=name,
        run_dir=run_dir,
        logs_dir=logs_dir,
        config_file=run_dir / "config.yaml",
        metrics_file=run_dir / "metrics.json",
        trades_file=run_dir / "trades.csv",
        equity_png=run_dir / "equity.png",
        run_log_file=logs_dir / "run.log",
        log_handler=logging.NullHandler(),
    )


def _install_common_patches(
    monkeypatch, cli_mod, run_ctx: RunContext, price_meta: Dict[str, object]
) -> None:
    monkeypatch.setattr(cli_mod, "setup_app_logging", lambda level: None)
    monkeypatch.setattr(cli_mod, "ensure_dirs", lambda extra=None: None)
    monkeypatch.setattr(cli_mod, "close_run_context", lambda ctx: None)
    monkeypatch.setattr(cli_mod, "capture_env", lambda keys: {"LOGOS_SEED": "123"})

    def _fake_save_plot(ctx, fig):
        run_ctx.equity_png.write_text("", encoding="utf-8")
        return run_ctx.equity_png

    monkeypatch.setattr(cli_mod, "save_equity_plot", _fake_save_plot)
    monkeypatch.setattr(cli_mod.plt, "close", lambda fig=None: None)
    monkeypatch.setattr(cli_mod, "last_price_metadata", lambda: dict(price_meta))

    data_index = pd.date_range("2024-01-01", periods=5, freq="D")
    price_df = pd.DataFrame(
        {"Close": [100.0, 101.0, 102.0, 103.0, 104.0]}, index=data_index
    )
    price_df.index.name = "Date"

    def _fake_prices(symbol, window: Window, **kwargs):
        return price_df

    monkeypatch.setattr(cli_mod, "get_prices", _fake_prices)

    def _fake_strategy(data, **params):
        return pd.Series(0, index=data.index)

    monkeypatch.setitem(cli_mod.STRATEGIES, "mean_reversion", _fake_strategy)

    equity = pd.Series([1.0, 1.01, 1.02, 1.03, 1.04], index=data_index)
    trades = pd.DataFrame(
        {"time": [data_index[1]], "side": [1], "shares": [10], "ref_close": [101.0]}
    )
    metrics = {
        "CAGR": 0.05,
        "Sharpe": 1.1,
        "MaxDD": -0.02,
        "WinRate": 0.6,
        "Exposure": 0.4,
    }

    def _fake_backtest(**kwargs):
        return {
            "returns": pd.Series([0.0, 0.01, -0.005, 0.002, 0.0], index=data_index),
            "equity_curve": equity,
            "trades": trades,
            "metrics": metrics,
            "warnings": [],
        }

    monkeypatch.setattr(cli_mod, "run_backtest", _fake_backtest)

    monkeypatch.setattr(cli_mod, "new_run", lambda symbol, strategy: run_ctx)


def test_provenance_marks_real_runs(monkeypatch, tmp_path, base_settings):
    from logos import cli as cli_mod

    run_ctx = _prep_run_context(tmp_path, "real_run")
    price_meta = {
        "data_source": "fixture",
        "synthetic": False,
        "fixture_paths": ["/tmp/fixture.csv"],
        "row_count": 5,
        "first_timestamp": "2024-01-01T00:00:00",
        "last_timestamp": "2024-01-05T00:00:00",
    }
    _install_common_patches(monkeypatch, cli_mod, run_ctx, price_meta)

    args = Namespace(
        symbol="MSFT",
        strategy="mean_reversion",
        start="2024-01-01",
        end="2024-01-10",
        window=None,
        allow_env_dates=False,
        tz="UTC",
        asset_class="equity",
        interval="1d",
        dollar_per_trade=10_000.0,
        slip_bps=1.0,
        commission=0.0035,
        fee_bps=5.0,
        fx_pip_size=0.0001,
        params=None,
        paper=True,
        allow_synthetic=False,
    )

    cmd_backtest(args, settings=base_settings)

    provenance = json.loads(run_ctx.run_dir.joinpath("provenance.json").read_text())
    assert provenance["data_source"] == "real"
    assert provenance["data_details"]["synthetic"] is False
    assert provenance["window"]["tz"] == "UTC"
    assert provenance["window"]["start_iso"].startswith("2024-01-01")
    assert provenance["window"]["end_iso"].startswith("2024-01-10")

    metrics_payload = json.loads(run_ctx.metrics_file.read_text())
    assert metrics_payload["provenance"]["synthetic"] is False
    assert metrics_payload["provenance"]["window"]["tz"] == "UTC"

    session_text = run_ctx.run_dir.joinpath("session.md").read_text()
    assert session_text.startswith("# Session Summary")


def test_provenance_marks_synthetic_runs(monkeypatch, tmp_path, base_settings):
    from logos import cli as cli_mod

    run_ctx = _prep_run_context(tmp_path, "synthetic_run")
    price_meta = {
        "data_source": "synthetic",
        "synthetic": True,
        "synthetic_reason": "download_empty",
        "generator": "synthetic-ohlcv-v1",
        "fixture_paths": ["/tmp/fixture.csv"],
        "cache_paths": ["/tmp/cache.csv"],
        "row_count": 3,
        "first_timestamp": "2024-01-01T00:00:00",
        "last_timestamp": "2024-01-03T00:00:00",
    }
    _install_common_patches(monkeypatch, cli_mod, run_ctx, price_meta)

    args = Namespace(
        symbol="BTC-USD",
        strategy="mean_reversion",
        start="2024-01-01",
        end="2024-01-10",
        window=None,
        allow_env_dates=False,
        tz="UTC",
        asset_class="crypto",
        interval="5m",
        dollar_per_trade=10_000.0,
        slip_bps=1.0,
        commission=0.0035,
        fee_bps=5.0,
        fx_pip_size=0.0001,
        params=None,
        paper=True,
        allow_synthetic=True,
    )

    cmd_backtest(args, settings=base_settings)

    provenance = json.loads(run_ctx.run_dir.joinpath("provenance.json").read_text())
    assert provenance["data_source"] == "synthetic"
    assert provenance["data_details"]["synthetic"] is True
    assert provenance["data_details"]["generator"] == "synthetic-ohlcv-v1"
    assert provenance["window"]["tz"] == "UTC"

    metrics_payload = json.loads(run_ctx.metrics_file.read_text())
    assert metrics_payload["provenance"]["synthetic"] is True
    assert metrics_payload["provenance"]["window"]["tz"] == "UTC"

    session_text = run_ctx.run_dir.joinpath("session.md").read_text()
    assert session_text.startswith("# SYNTHETIC RUN")

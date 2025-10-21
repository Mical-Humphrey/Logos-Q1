import shlex

import matplotlib
import pytest

from logos import cli
from logos.tutor.__main__ import main as tutor_main
from logos import logging_setup, paths, run_manager
from logos.config import load_settings

matplotlib.use("Agg", force=True)

BACKTEST_COMMANDS = [
    "--symbol MSFT --strategy mean_reversion --asset-class equity --start 2022-01-01 --end 2024-01-01 --paper",
    "--symbol BTC-USD --strategy momentum --asset-class crypto --interval 1h --start 2024-01-01 --end 2024-03-31 --dollar-per-trade 5000 --fee-bps 15 --paper --allow-synthetic",
    "--symbol EURUSD=X --strategy mean_reversion --asset-class forex --interval 30m --slip-bps 8 --commission 0.0 --fx-pip-size 0.0001 --start 2023-06-01 --end 2023-08-31",
    "--symbol AAPL --strategy pairs_trading --params window=20,threshold=1.5 --start 2024-01-01 --end 2024-04-01 --paper",
    "--symbol TSLA --strategy momentum --start 2024-01-01 --end 2024-03-31",
    "--symbol BTC-USD --strategy mean_reversion --asset-class crypto --interval 5m --start 2024-01-01 --end 2024-01-07 --paper --allow-synthetic",
    "--symbol MSFT --strategy momentum --params fast=20,slow=50 --start 2024-01-01 --end 2024-03-01 --paper --dollar-per-trade 2000",
    "--symbol EURUSD --strategy pairs_trading --asset-class forex --params hedge_ratio=0.95 --start 2023-06-01 --end 2023-09-01 --paper",
    "--symbol DEMO --strategy mean_reversion --paper --start 2023-01-01 --end 2023-01-15 --allow-synthetic",
]

TUTOR_COMMANDS = [
    ["--list"],
    ["--lesson", "mean_reversion"],
    ["--lesson", "mean_reversion", "--plot", "--explain-math"],
    ["--lesson", "momentum", "--plot"],
    ["--lesson", "pairs_trading", "--plot", "--explain-math"],
]


@pytest.fixture(autouse=True)
def isolate_filesystem(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_raw = data_dir / "raw"
    data_cache = data_dir / "cache"
    runs_dir = tmp_path / "runs"
    runs_lessons = runs_dir / "lessons"
    latest_link = runs_dir / "latest"
    app_logs_dir = tmp_path / "logs"
    app_log_file = app_logs_dir / "app.log"

    monkeypatch.setattr(paths, "DATA_DIR", data_dir, raising=False)
    monkeypatch.setattr(paths, "DATA_RAW_DIR", data_raw, raising=False)
    monkeypatch.setattr(paths, "DATA_CACHE_DIR", data_cache, raising=False)
    monkeypatch.setattr(paths, "RUNS_DIR", runs_dir, raising=False)
    monkeypatch.setattr(paths, "RUNS_LESSONS_DIR", runs_lessons, raising=False)
    monkeypatch.setattr(paths, "RUNS_LATEST_LINK", latest_link, raising=False)
    monkeypatch.setattr(paths, "APP_LOGS_DIR", app_logs_dir, raising=False)
    monkeypatch.setattr(paths, "APP_LOG_FILE", app_log_file, raising=False)

    monkeypatch.setattr(run_manager, "RUNS_DIR", runs_dir, raising=False)
    monkeypatch.setattr(run_manager, "RUNS_LESSONS_DIR", runs_lessons, raising=False)
    monkeypatch.setattr(run_manager, "RUNS_LATEST_LINK", latest_link, raising=False)

    monkeypatch.setattr(logging_setup, "APP_LOG_FILE", app_log_file, raising=False)
    monkeypatch.setattr(logging_setup, "_configured", False, raising=False)

    paths.ensure_dirs()


def test_backtest_commands():
    for cmd in BACKTEST_COMMANDS:
        argv = ["backtest", *shlex.split(cmd)]
        cli.main(argv)


def test_tutor_commands():
    for args in TUTOR_COMMANDS:
        tutor_main(args)


def test_cli_help_formatting():
    parser = cli.build_parser(load_settings())
    parser.format_help()

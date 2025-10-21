from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime

import pandas as pd
import pytest

from logos.cli import (
    BacktestValidationResult,
    validate_backtest_args,
)
from logos.config import Settings
from logos.window import Window


def _args(**overrides):
    base = {
        "start": None,
        "end": None,
        "window": None,
        "allow_env_dates": False,
        "tz": "UTC",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def sample_settings() -> Settings:
    return Settings(start="2024-01-01", end="2024-03-01", symbol="MSFT")


def test_validate_requires_explicit_dates_without_env(
    sample_settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        validate_backtest_args(
            _args(), sample_settings, now=lambda tz: datetime(2024, 3, 1, tzinfo=tz)
        )
    captured = capsys.readouterr()
    assert "requires either --window" in captured.err


def test_validate_allows_env_dates_when_flag(sample_settings: Settings) -> None:
    result = validate_backtest_args(
        _args(allow_env_dates=True),
        sample_settings,
        now=lambda tz: datetime(2024, 2, 1, tzinfo=tz),
    )
    assert result.start == "2024-01-01"
    assert result.end == "2024-03-01"
    assert result.env_sources == {"END_DATE": "2024-03-01", "START_DATE": "2024-01-01"}


def test_validate_errors_when_env_missing(
    sample_settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = Settings(start="", end="2024-02-01", symbol="MSFT")
    with pytest.raises(SystemExit):
        validate_backtest_args(
            _args(allow_env_dates=True),
            missing,
            now=lambda tz: datetime(2024, 2, 1, tzinfo=tz),
        )
    captured = capsys.readouterr()
    assert "START_DATE not found" in captured.err


def test_validate_rejects_reversed_dates(
    sample_settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        validate_backtest_args(
            _args(start="2024-03-01", end="2024-01-01"),
            sample_settings,
            now=lambda tz: datetime(2024, 3, 1, tzinfo=tz),
        )
    captured = capsys.readouterr()
    assert "Start date 2024-03-01 is not before end date 2024-01-01" in captured.err


def test_validate_rejects_invalid_window(
    sample_settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        validate_backtest_args(
            _args(window="PX"),
            sample_settings,
            now=lambda tz: datetime(2024, 3, 1, tzinfo=tz),
        )
    captured = capsys.readouterr()
    assert "not a supported ISO-8601 duration" in captured.err


def test_validate_accepts_explicit_dates(sample_settings: Settings) -> None:
    result = validate_backtest_args(
        _args(start="2024-01-15", end="2024-02-15"),
        sample_settings,
        now=lambda tz: datetime(2024, 2, 15, tzinfo=tz),
    )
    assert isinstance(result, BacktestValidationResult)
    assert result.start == "2024-01-15"
    assert result.end == "2024-02-15"
    assert result.window_spec is None


def test_validate_accepts_window(sample_settings: Settings) -> None:
    result = validate_backtest_args(
        _args(window="P10D"),
        sample_settings,
        now=lambda tz: datetime(2024, 1, 20, tzinfo=tz),
    )
    assert result.start == "2024-01-10"
    assert result.end == "2024-01-20"
    assert result.window_spec == "P10D"


def test_validate_handles_timezone_offset(sample_settings: Settings) -> None:
    result = validate_backtest_args(
        _args(
            start="2024-01-01T12:00:00-05:00",
            end="2024-02-01T00:00:00-05:00",
            tz="America/Chicago",
        ),
        sample_settings,
        now=lambda tz: datetime(2024, 2, 1, tzinfo=tz),
    )
    assert result.start == "2024-01-01"
    assert result.end == "2024-01-31"


def test_validate_rejects_unknown_timezone(
    sample_settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        validate_backtest_args(
            _args(start="2024-01-01", end="2024-01-05", tz="Mars/Phobos"),
            sample_settings,
            now=lambda tz: datetime(2024, 1, 5, tzinfo=tz),
        )
    captured = capsys.readouterr()
    assert "Unknown timezone 'Mars/Phobos'" in captured.err


def test_cli_fail_fast_prevents_run_creation(
    monkeypatch, sample_settings: Settings, capsys
) -> None:
    from logos import cli as cli_mod

    monkeypatch.setattr(cli_mod, "load_settings", lambda: sample_settings)
    monkeypatch.setattr(cli_mod, "setup_app_logging", lambda level: None)
    monkeypatch.setattr(cli_mod, "ensure_dirs", lambda extra=None: None)

    called = False

    def _should_not_run(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("new_run should not be invoked on validation failure")

    monkeypatch.setattr(cli_mod, "new_run", _should_not_run)

    with pytest.raises(SystemExit):
        cli_mod.main(["backtest", "--symbol", "DEMO", "--strategy", "mean_reversion"])

    captured = capsys.readouterr()
    assert "requires either --window" in captured.err
    assert called is False


def test_cli_accepts_window_and_proceeds(
    monkeypatch, tmp_path, sample_settings: Settings
) -> None:
    from logos import cli as cli_mod

    monkeypatch.setattr(cli_mod, "load_settings", lambda: sample_settings)
    monkeypatch.setattr(cli_mod, "setup_app_logging", lambda level: None)
    monkeypatch.setattr(cli_mod, "ensure_dirs", lambda extra=None: None)
    monkeypatch.setattr(cli_mod, "capture_env", lambda keys: {k: "" for k in keys})
    monkeypatch.setattr(cli_mod, "write_config", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli_mod, "write_metrics", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli_mod, "write_trades", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        cli_mod, "save_equity_plot", lambda ctx, fig: tmp_path / "equity.png"
    )
    monkeypatch.setattr(cli_mod, "close_run_context", lambda ctx: None)
    monkeypatch.setattr(cli_mod.plt, "close", lambda fig=None: None)

    fake_fig = SimpleNamespace(savefig=lambda *args, **kwargs: None)
    monkeypatch.setattr(cli_mod, "_plot_equity", lambda equity: fake_fig)

    def _fake_prices(
        symbol,
        window: Window,
        interval="1d",
        asset_class="equity",
        **_kwargs,
    ):
        idx = pd.date_range(start=window.start, periods=5, freq="D")
        data = pd.DataFrame(
            {
                "Open": 1.0,
                "High": 1.0,
                "Low": 1.0,
                "Close": 1.0,
                "Adj Close": 1.0,
                "Volume": 1.0,
            },
            index=idx,
        )
        return data

    monkeypatch.setattr(cli_mod, "get_prices", _fake_prices)

    def _fake_strategy(df, **_params):
        return pd.Series(0, index=df.index)

    monkeypatch.setitem(cli_mod.STRATEGIES, "mean_reversion", _fake_strategy)

    def _fake_backtest(**_kwargs):
        base_window = Window.from_bounds(start="2024-01-01", end="2024-01-05")
        return {
            "metrics": {
                "CAGR": 0.1,
                "Sharpe": 1.0,
                "MaxDD": -0.01,
                "WinRate": 0.5,
                "Exposure": 0.3,
            },
            "equity_curve": pd.Series(
                [1, 1.1, 1.2, 1.3, 1.4],
                index=_fake_prices("", base_window).index,
            ),
            "returns": pd.Series(
                [0, 0, 0, 0, 0],
                index=_fake_prices("", base_window).index,
            ),
            "trades": pd.DataFrame([]),
        }

    monkeypatch.setattr(cli_mod, "run_backtest", _fake_backtest)

    class _Ctx(SimpleNamespace):
        pass

    def _fake_new_run(symbol, strategy):
        run_dir = tmp_path / f"run_{symbol}_{strategy}"
        run_dir.mkdir(parents=True, exist_ok=True)
        logs_dir = run_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        return _Ctx(
            run_id="test",
            run_dir=run_dir,
            logs_dir=logs_dir,
            config_file=run_dir / "config.yaml",
            metrics_file=run_dir / "metrics.json",
            trades_file=run_dir / "trades.csv",
            equity_png=run_dir / "equity.png",
            run_log_file=logs_dir / "run.log",
            log_handler=SimpleNamespace(),
        )

    monkeypatch.setattr(cli_mod, "new_run", _fake_new_run)

    cli_mod.main(
        [
            "backtest",
            "--symbol",
            "DEMO",
            "--strategy",
            "mean_reversion",
            "--window",
            "P5D",
        ]
    )

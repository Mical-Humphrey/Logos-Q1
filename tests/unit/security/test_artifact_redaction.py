from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from logos.run_manager import (
    RunContext,
    write_config,
    write_metrics,
    write_provenance,
    write_trades,
)


def _ctx(tmp_path: Path) -> RunContext:
    return RunContext(
        run_id="unit",
        run_dir=tmp_path,
        logs_dir=tmp_path,
        config_file=tmp_path / "config.yaml",
        metrics_file=tmp_path / "metrics.json",
        trades_file=tmp_path / "trades.csv",
        equity_png=tmp_path / "equity.png",
        run_log_file=tmp_path / "run.log",
        log_handler=logging.NullHandler(),
    )


def test_write_config_redacts_secrets(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    write_config(
        ctx,
        {"alpaca_secret_key": "super"},
        env={"API_TOKEN": "abc"},
    )
    text = ctx.config_file.read_text(encoding="utf-8")
    assert "<redacted>" in text
    assert "super" not in text
    assert "abc" not in text


def test_write_metrics_masks_payload(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    write_metrics(
        ctx,
        {"Sharpe": 1.2, "secret_key": "value"},
        provenance={"api_secret": "hidden"},
    )
    contents = ctx.metrics_file.read_text(encoding="utf-8")
    assert "<redacted>" in contents
    assert "value" not in contents


def test_write_trades_sanitizes_rows(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    write_trades(ctx, pd.DataFrame([["=SUM(A1:A2)"]], columns=["note"]))
    csv_text = ctx.trades_file.read_text(encoding="utf-8")
    assert "'=SUM" in csv_text
    sanitized_row = csv_text.splitlines()[1]
    assert sanitized_row.startswith("'")


def test_write_provenance_masks_sensitive_fields(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    path = write_provenance(
        ctx,
        {"token": "abc", "window": {"start": "2024-01-01", "api_secret": "def"}},
    )
    data = path.read_text(encoding="utf-8")
    assert "<redacted>" in data
    assert "abc" not in data
    assert "def" not in data

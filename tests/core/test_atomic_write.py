from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path

import pytest

from core.io.atomic_write import atomic_write_text
from logos.run_manager import RunContext, write_metrics

atomic_mod = importlib.import_module("core.io.atomic_write")


def _make_run_context(tmp_path: Path) -> RunContext:
    logs_dir = tmp_path / "logs"
    return RunContext(
        run_id="run",
        run_dir=tmp_path,
        logs_dir=logs_dir,
        config_file=tmp_path / "config.yaml",
        metrics_file=tmp_path / "metrics.json",
        trades_file=tmp_path / "trades.csv",
        equity_png=tmp_path / "equity.png",
        run_log_file=logs_dir / "run.log",
        log_handler=logging.NullHandler(),
    )


def test_atomic_write_text_writes_content(tmp_path):
    target = tmp_path / "sample.txt"
    atomic_write_text(target, "hello")
    assert target.read_text("utf-8") == "hello"


def test_write_metrics_uses_atomic_write(tmp_path):
    ctx = _make_run_context(tmp_path)
    write_metrics(ctx, {"sharpe": 1.23})

    payload = json.loads(ctx.metrics_file.read_text("utf-8"))
    assert payload["sharpe"] == 1.23


def test_write_metrics_failure_preserves_existing(tmp_path, monkeypatch):
    ctx = _make_run_context(tmp_path)
    ctx.metrics_file.parent.mkdir(parents=True, exist_ok=True)
    ctx.metrics_file.write_text(json.dumps({"baseline": True}), encoding="utf-8")

    def boom(src: str | bytes, dst: str | bytes) -> None:
        raise RuntimeError("rename_failed")

    monkeypatch.setattr(atomic_mod.os, "replace", boom)

    with pytest.raises(RuntimeError):
        write_metrics(ctx, {"sharpe": 2.0})

    payload = json.loads(ctx.metrics_file.read_text("utf-8"))
    assert payload == {"baseline": True}

    temp_files = [
        child
        for child in ctx.metrics_file.parent.iterdir()
        if child.is_file() and child.name != "metrics.json"
    ]
    assert not temp_files


def test_write_metrics_failure_without_existing_leaves_absent(tmp_path, monkeypatch):
    ctx = _make_run_context(tmp_path)

    def boom(src: str | bytes, dst: str | bytes) -> None:
        raise RuntimeError("rename_failed")

    monkeypatch.setattr(atomic_mod.os, "replace", boom)

    with pytest.raises(RuntimeError):
        write_metrics(ctx, {"sharpe": 2.0})

    assert not ctx.metrics_file.exists()

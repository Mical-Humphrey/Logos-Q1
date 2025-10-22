from __future__ import annotations

import csv
import importlib
from pathlib import Path

import pandas as pd
import pytest

atomic_utils = importlib.import_module("core.io.atomic_write")

from logos.run_manager import close_run_context, new_run, write_trades


def _snapshot(directory: Path) -> list[str]:
    return sorted(
        str(path.relative_to(directory))
        for path in directory.rglob("*")
        if path.is_file()
    )


def test_atomic_write_cleans_up_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "metrics.json"

    calls = {"count": 0}
    real_replace = atomic_utils.os.replace

    def flaky_replace(src: str, dst: str) -> None:
        calls["count"] += 1
        raise OSError("simulated crash during replace")

    monkeypatch.setattr(atomic_utils.os, "replace", flaky_replace)

    with pytest.raises(OSError):
        atomic_utils.atomic_write_text(target, "{}")

    assert not target.exists()
    assert list(tmp_path.iterdir()) == []
    assert calls["count"] == 1

    monkeypatch.setattr(atomic_utils.os, "replace", real_replace)


def test_restart_idempotent_trade_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = new_run("MSFT", "mean_reversion", base_dir=tmp_path, set_latest=False)

    before = _snapshot(ctx.run_dir)

    calls = {"count": 0}
    real_replace = atomic_utils.os.replace

    def flaky_replace(src: str, dst: str) -> None:
        if calls["count"] == 0:
            calls["count"] += 1
            raise OSError("disk error mid-write")
        real_replace(src, dst)

    monkeypatch.setattr(atomic_utils.os, "replace", flaky_replace)

    trades = pd.DataFrame(
        [
            {
                "timestamp": "2024-01-01T09:30:00+00:00",
                "symbol": "MSFT",
                "qty": 10,
                "price": 100.0,
                "side": "BUY",
            },
            {
                "timestamp": "2024-01-01T09:31:00+00:00",
                "symbol": "MSFT",
                "qty": -10,
                "price": 101.5,
                "side": "SELL",
            },
        ]
    )

    with pytest.raises(OSError):
        write_trades(ctx, trades)

    after_failure = _snapshot(ctx.run_dir)
    assert after_failure == before
    assert not ctx.trades_file.exists()

    monkeypatch.setattr(atomic_utils.os, "replace", real_replace)

    write_trades(ctx, trades)

    after_restart = _snapshot(ctx.run_dir)
    assert ctx.trades_file.exists()
    assert calls["count"] == 1

    with ctx.trades_file.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    assert len(rows) == len(trades)
    assert rows[0]["timestamp"] == "2024-01-01T09:30:00+00:00"
    assert rows[1]["timestamp"] == "2024-01-01T09:31:00+00:00"

    close_run_context(ctx)

    # Ensure restart did not leave duplicate artifacts beyond the expected trades file
    expected_new_files = set(after_restart) - set(before)
    assert expected_new_files == {str(ctx.trades_file.relative_to(ctx.run_dir))}

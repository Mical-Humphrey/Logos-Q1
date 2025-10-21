from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from logos.cli import (
    ERROR_INVALID_ISO_DURATION,
    ERROR_MUTUALLY_EXCLUSIVE,
    ERROR_REQUIRES_WINDOW,
    ERROR_START_BEFORE_END,
)
from logos.paths import PROJECT_ROOT, RUNS_DIR, RUNS_LATEST_LINK
from logos.strategies import STRATEGIES


def _sorted_strategy_names() -> list[str]:
    return sorted(STRATEGIES.keys(), key=str.lower)


def _format_strategy_list() -> str:
    return ",".join(_sorted_strategy_names())


def _snapshot_runs() -> list[str]:
    if not RUNS_DIR.exists():
        return []
    entries: list[str] = []
    for path in sorted(RUNS_DIR.rglob("*")):
        rel = path.relative_to(RUNS_DIR).as_posix()
        if path.is_dir():
            entries.append(f"DIR {rel}")
        elif path.is_file():
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            entries.append(f"FILE {rel} {sha}")
    return entries


def _capture_latest_state() -> tuple[str, str | None]:
    link = RUNS_LATEST_LINK
    if link.is_symlink():
        return ("symlink", os.readlink(link))
    if link.exists():
        return ("file", link.read_text(encoding="utf-8"))
    return ("missing", None)


def _restore_latest(state: tuple[str, str | None]) -> None:
    kind, payload = state
    link = RUNS_LATEST_LINK
    if link.exists() or link.is_symlink():
        if link.is_dir():
            shutil.rmtree(link)
        else:
            link.unlink()
    if kind == "symlink" and payload is not None:
        target = Path(payload)
        try:
            link.symlink_to(target)
        except OSError:
            link.write_text(payload, encoding="utf-8")
    elif kind == "file" and payload is not None:
        link.write_text(payload, encoding="utf-8")


def _cleanup_runs(
    before: list[str], after: list[str], latest_state: tuple[str, str | None]
) -> None:
    before_set = set(before)
    after_set = set(after)
    new_entries = after_set - before_set
    top_dirs: set[str] = set()
    for entry in new_entries:
        if entry.startswith("DIR "):
            rel = entry.split(" ", 1)[1]
            top = rel.split("/", 1)[0]
            if top and top != "latest":
                top_dirs.add(top)
    for dirname in top_dirs:
        candidate = RUNS_DIR / dirname
        if candidate.exists() and candidate.is_dir():
            shutil.rmtree(candidate)
    _restore_latest(latest_state)


def _run_cli(
    args: list[str], *, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-m", "logos.cli", "backtest", *args]
    env_vars = os.environ.copy()
    env_vars.update(
        {
            "MPLBACKEND": "Agg",
            "LIVE_DISABLE_NETWORK": "1",
            "TZ": "UTC",
        }
    )
    if env:
        env_vars.update(env)
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=env_vars,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "extra_args, expected_substring",
    [
        ([], ERROR_REQUIRES_WINDOW),
        (["--start", "2024-03-10", "--end", "2024-03-01"], ERROR_START_BEFORE_END),
        (
            ["--window", "P30D", "--start", "2024-03-01", "--end", "2024-03-10"],
            ERROR_MUTUALLY_EXCLUSIVE,
        ),
        (["--window", "P3X"], ERROR_INVALID_ISO_DURATION),
    ],
)
def test_cli_subprocess_validation_failures(
    extra_args: list[str], expected_substring: str
) -> None:
    before = _snapshot_runs()
    result = _run_cli(["--symbol", "MSFT", "--strategy", "mean_reversion", *extra_args])
    after = _snapshot_runs()
    assert result.returncode != 0
    assert expected_substring in result.stderr
    assert before == after


def test_cli_subprocess_ambiguous_timezone() -> None:
    before = _snapshot_runs()
    result = _run_cli(
        [
            "--symbol",
            "MSFT",
            "--strategy",
            "mean_reversion",
            "--tz",
            "America/New_York",
            "--start",
            "2024-11-03T01:30",
            "--end",
            "2024-11-03T03:00",
        ]
    )
    after = _snapshot_runs()
    assert result.returncode != 0
    assert "ambiguous timezone input" in result.stderr
    assert before == after


def test_cli_subprocess_unknown_strategy_lists_valid() -> None:
    before = _snapshot_runs()
    expected = _format_strategy_list()
    result = _run_cli(["--symbol", "MSFT", "--strategy", "DOES_NOT_EXIST"])
    after = _snapshot_runs()
    assert result.returncode != 0
    assert f"valid strategies: {expected}" in result.stderr
    assert before == after


def test_cli_subprocess_env_dates_success_and_logs() -> None:
    env_dates = {"START_DATE": "2024-01-01", "END_DATE": "2024-02-01"}
    before = _snapshot_runs()
    latest_state = _capture_latest_state()
    result = _run_cli(
        [
            "--symbol",
            "DEMO",
            "--strategy",
            "mean_reversion",
            "--allow-env-dates",
            "--allow-synthetic",
            "--paper",
        ],
        env=env_dates,
    )
    after = _snapshot_runs()
    try:
        assert result.returncode == 0
        combined_output = f"{result.stdout}\n{result.stderr}"
        assert "Using dates from environment: START=" in combined_output
        assert "END=" in combined_output
    finally:
        _cleanup_runs(before, after, latest_state)

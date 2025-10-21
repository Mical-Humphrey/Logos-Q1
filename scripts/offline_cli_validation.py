"""Offline CLI validation scenarios for Logos backtest command."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "runs"
RUNS_LATEST = RUNS_DIR / "latest"


class ScenarioError(RuntimeError):
    pass


def _current_run_dirs() -> set[Path]:
    if not RUNS_DIR.exists():
        return set()
    return {path for path in RUNS_DIR.iterdir() if path.is_dir()}


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _validate(
    name: str,
    cmd: list[str],
    *,
    expect_success: bool,
    expect_artifact: bool,
) -> None:
    before = _current_run_dirs()
    result = _run(cmd)
    after = _current_run_dirs()
    created = sorted(after - before)

    if expect_success and result.returncode != 0:
        raise ScenarioError(
            f"{name} expected success but exited {result.returncode}: {result.stderr.strip()}"
        )
    if not expect_success and result.returncode == 0:
        raise ScenarioError(
            f"{name} expected non-zero exit but succeeded: {result.stdout.strip()}"
        )

    if expect_artifact and not created:
        raise ScenarioError(f"{name} expected new artifacts but none were created")
    if not expect_artifact and created:
        raise ScenarioError(f"{name} should not create artifacts (created: {created})")

    for path in created:
        shutil.rmtree(path, ignore_errors=True)
    _cleanup_latest_pointer(created)


def _cleanup_latest_pointer(removed: Iterable[Path]) -> None:
    if not RUNS_LATEST.exists() and not RUNS_LATEST.is_symlink():
        return
    target_str: str | None = None
    if RUNS_LATEST.is_symlink():
        try:
            target_str = os.readlink(RUNS_LATEST)
        except OSError:
            target_str = None
    else:
        try:
            target_str = RUNS_LATEST.read_text(encoding="utf-8").strip()
        except Exception:
            target_str = None
    if not target_str:
        RUNS_LATEST.unlink(missing_ok=True)
        return
    candidate = Path(target_str)
    if not candidate.is_absolute():
        candidate = RUNS_LATEST.parent / candidate
    if not candidate.exists():
        RUNS_LATEST.unlink(missing_ok=True)
        return
    target_name = candidate.name
    for path in removed:
        if path.name == target_name:
            RUNS_LATEST.unlink(missing_ok=True)
            break


def main() -> int:
    scenarios: list[tuple[str, list[str], bool, bool]] = [
        (
            "missing_dates",
            [
                sys.executable,
                "-m",
                "logos.cli",
                "backtest",
                "--symbol",
                "MSFT",
                "--strategy",
                "momentum",
            ],
            False,
            False,
        ),
        (
            "reversed_window",
            [
                sys.executable,
                "-m",
                "logos.cli",
                "backtest",
                "--symbol",
                "MSFT",
                "--strategy",
                "momentum",
                "--start",
                "2024-01-10",
                "--end",
                "2024-01-01",
            ],
            False,
            False,
        ),
        (
            "malformed_iso_window",
            [
                sys.executable,
                "-m",
                "logos.cli",
                "backtest",
                "--symbol",
                "MSFT",
                "--strategy",
                "momentum",
                "--window",
                "P-30D",
            ],
            False,
            False,
        ),
        (
            "valid_window",
            [
                sys.executable,
                "-m",
                "logos.cli",
                "backtest",
                "--symbol",
                "DEMO",
                "--strategy",
                "mean_reversion",
                "--window",
                "P5D",
                "--allow-synthetic",
                "--paper",
            ],
            True,
            True,
        ),
        (
            "synthetic_without_flag",
            [
                sys.executable,
                "-m",
                "logos.cli",
                "backtest",
                "--symbol",
                "FAKE_SYNTH",
                "--strategy",
                "mean_reversion",
                "--window",
                "P5D",
                "--asset-class",
                "equity",
            ],
            False,
            False,
        ),
    ]

    for name, cmd, expect_success, expect_artifact in scenarios:
        _validate(
            name, cmd, expect_success=expect_success, expect_artifact=expect_artifact
        )

    return 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())

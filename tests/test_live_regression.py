from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from logos.live.regression import BASELINE_DIR, DEFAULT_FIXTURE_DIR, run_regression


def test_regression_matches_smoke_baseline(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baseline"
    output_dir = tmp_path / "run"

    run_regression(
        output_root=output_dir,
        baseline_dir=baseline_dir,
        update_baseline=True,
        allow_refresh=True,
        dataset_dir=DEFAULT_FIXTURE_DIR,
        label="test-paper",
        seed=101,
    )

    result = run_regression(
        output_root=output_dir,
        baseline_dir=baseline_dir,
        dataset_dir=DEFAULT_FIXTURE_DIR,
        label="test-paper",
        seed=101,
    )

    assert result.matches_baseline is True
    assert result.diffs == {}
    assert result.artifacts.snapshot.exists()
    assert result.artifacts.equity_curve.exists()
    assert result.artifacts.metrics.exists()


def test_refresh_requires_confirmation(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        run_regression(
            output_root=tmp_path,
            baseline_dir=BASELINE_DIR,
            update_baseline=True,
        )


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_adapter_mode_emits_logs(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baseline"
    output_dir = tmp_path / "run"

    result_one = run_regression(
        output_root=output_dir,
        baseline_dir=baseline_dir,
        update_baseline=True,
        allow_refresh=True,
        dataset_dir=DEFAULT_FIXTURE_DIR,
        label="adapter-test",
        seed=77,
        adapter_mode="adapter",
        adapter_name="ccxt",
    )

    result_two = run_regression(
        output_root=output_dir,
        baseline_dir=baseline_dir,
        dataset_dir=DEFAULT_FIXTURE_DIR,
        label="adapter-test",
        seed=77,
        adapter_mode="adapter",
        adapter_name="ccxt",
    )

    assert result_two.matches_baseline is True
    assert result_two.artifacts.adapter_logs is not None
    assert result_two.artifacts.adapter_logs.exists()
    assert _checksum(result_one.artifacts.adapter_logs) == _checksum(result_two.artifacts.adapter_logs)

from __future__ import annotations

from pathlib import Path

import pytest

from logos.live.regression import BASELINE_DIR, run_regression


def test_regression_matches_smoke_baseline(tmp_path: Path) -> None:
    result = run_regression(output_root=tmp_path, baseline_dir=BASELINE_DIR)
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

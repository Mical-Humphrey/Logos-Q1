from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from logos.live import regression
from logos.live.regression import (
    BASELINE_DIR,
    DEFAULT_FIXTURE_DIR,
    DEFAULT_SYMBOL,
    METRIC_ABS_TOLERANCE,
    run_regression,
)
from logos.window import Window


FIXTURE_WINDOW = Window.from_bounds(start="2024-01-01", end="2024-01-02")


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
        window=FIXTURE_WINDOW,
    )

    result = run_regression(
        output_root=output_dir,
        baseline_dir=baseline_dir,
        dataset_dir=DEFAULT_FIXTURE_DIR,
        label="test-paper",
        seed=101,
        window=FIXTURE_WINDOW,
    )

    assert result.matches_baseline is True
    assert result.diffs == {}
    assert result.artifacts.snapshot.exists()
    assert result.artifacts.equity_curve.exists()
    assert result.artifacts.metrics.exists()
    assert result.artifacts.provenance.exists()
    assert result.artifacts.session.exists()
    assert result.artifacts.orchestrator_metrics is not None
    assert result.artifacts.orchestrator_metrics.exists()
    assert result.artifacts.router_state is not None
    assert result.artifacts.router_state.exists()

    metrics_payload = json.loads(result.artifacts.metrics.read_text(encoding="utf-8"))
    assert metrics_payload["provenance"]["dataset"].endswith("regression_default")
    assert (
        metrics_payload["provenance"]["window"]["start_iso"]
        == FIXTURE_WINDOW.start.isoformat()
    )
    assert (
        metrics_payload["provenance"]["window"]["end_iso"]
        == FIXTURE_WINDOW.end.isoformat()
    )
    provenance_payload = json.loads(
        result.artifacts.provenance.read_text(encoding="utf-8")
    )
    assert provenance_payload["data_source"] == "fixture"
    assert provenance_payload["data_details"]["bars"] == 3
    window_payload = provenance_payload["window"]
    assert window_payload["start_iso"] == FIXTURE_WINDOW.start.isoformat()
    assert window_payload["end_iso"] == FIXTURE_WINDOW.end.isoformat()
    assert provenance_payload["data_details"]["window"] == window_payload


def test_refresh_requires_confirmation(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        run_regression(
            output_root=tmp_path,
            baseline_dir=BASELINE_DIR,
            update_baseline=True,
            window=FIXTURE_WINDOW,
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
        window=FIXTURE_WINDOW,
    )

    result_two = run_regression(
        output_root=output_dir,
        baseline_dir=baseline_dir,
        dataset_dir=DEFAULT_FIXTURE_DIR,
        label="adapter-test",
        seed=77,
        adapter_mode="adapter",
        adapter_name="ccxt",
        window=FIXTURE_WINDOW,
    )

    assert result_two.matches_baseline is True
    assert result_one.artifacts.adapter_logs is not None
    assert result_two.artifacts.adapter_logs is not None
    first_logs = result_one.artifacts.adapter_logs
    second_logs = result_two.artifacts.adapter_logs
    assert second_logs.exists()
    assert _checksum(first_logs) == _checksum(second_logs)


def test_compare_metrics_tolerance(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    output = tmp_path / "output.json"
    baseline.write_text(json.dumps({"pnl": 1.0, "count": 5}))
    output.write_text(json.dumps({"pnl": 1.0 + METRIC_ABS_TOLERANCE / 2, "count": 5}))

    assert regression._compare_metrics(baseline, output, METRIC_ABS_TOLERANCE) is None

    output.write_text(json.dumps({"pnl": 1.0 + METRIC_ABS_TOLERANCE * 5, "count": 6}))
    diff = regression._compare_metrics(baseline, output, METRIC_ABS_TOLERANCE)
    assert diff is not None and "pnl" in diff and "count" in diff


def test_run_regression_requires_window_overlap(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        run_regression(
            output_root=tmp_path / "out",
            baseline_dir=tmp_path / "base",
            dataset_dir=DEFAULT_FIXTURE_DIR,
            label="no-overlap",
            seed=42,
            window=Window.from_bounds(start="2030-01-01", end="2030-01-02"),
        )


def test_drain_adapter_logs_variants() -> None:
    class WithDrain:
        def __init__(self) -> None:
            self._payload = [{"a": 1}]

        def drain_logs(self) -> list[dict]:
            data = self._payload
            self._payload = []
            return data

    class WithLogs:
        def __init__(self) -> None:
            self.logs = [{"b": 2}]

        def reset_logs(self) -> None:
            self.logs = []

    assert regression._drain_adapter_logs(WithDrain()) == [{"a": 1}]
    assert regression._drain_adapter_logs(WithLogs()) == [{"b": 2}]


def test_write_adapter_logs_handles_empty(tmp_path: Path) -> None:
    paths = regression.prepare_seeded_run_paths(1, "log-test", base_dir=tmp_path)
    empty_path = regression._write_adapter_logs(paths, [])
    assert empty_path.read_text(encoding="utf-8").strip() == "[]"

    payload_path = regression._write_adapter_logs(paths, [{"foo": "bar"}])
    lines = payload_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and "foo" in lines[0]


def test_regression_cli_cycle(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    baseline_dir = tmp_path / "base"
    args_refresh = [
        "--output-dir",
        str(output_dir),
        "--baseline",
        str(baseline_dir),
        "--dataset",
        str(DEFAULT_FIXTURE_DIR),
        "--symbol",
        DEFAULT_SYMBOL,
        "--label",
        "cli-cycle",
        "--seed",
        "515",
        "--refresh-baseline",
        "--confirm-refresh",
    ]
    assert regression.main(args_refresh) == 0

    args_run = args_refresh[:-2]
    assert regression.main(args_run) == 0

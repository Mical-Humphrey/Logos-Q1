from __future__ import annotations

from datetime import datetime, timezone

import pytest

from logos.cli import status


def test_load_orchestrator_metrics_returns_last_entry(tmp_path) -> None:
    run_dir = tmp_path
    metrics_path = run_dir / "orchestrator_metrics.jsonl"
    metrics_path.write_text(
        """
{"p95_latency_s": 0.05, "skip_rate": 0.0}
{"p95_latency_s": 0.12, "skip_rate": 0.02}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    data = status._load_orchestrator_metrics(run_dir)

    assert data is not None
    assert pytest.approx(data["p95_latency_s"], rel=1e-6) == 0.12
    assert pytest.approx(data["skip_rate"], rel=1e-6) == 0.02


def test_print_status_includes_orchestrator_metrics(tmp_path, capsys) -> None:
    payload = status.StatusPayload(
        run_id="test",
        equity=1000.0,
        pnl=25.0,
        positions={},
        last_signal="flat",
        last_updated=datetime(2025, 1, 1, tzinfo=timezone.utc),
        health={"offline_only": False, "stale": False, "open_positions": False},
    )
    metrics: dict[str, object] = {"sharpe": 1.23}
    orchestrator_metrics: dict[str, object] = {
        "timestamp": "2025-01-01T00:00:00+00:00",
        "p95_latency_s": 0.04,
        "skip_rate": 0.001,
        "queue_depth_max": 3,
        "ticks": 17,
    }

    status._print_status(tmp_path, payload, metrics, orchestrator_metrics)
    captured = capsys.readouterr().out

    assert "Orchestrator Metrics" in captured
    assert "0.040" in captured
    assert "Skip rate" in captured
    assert "Queue depth max" in captured
    assert "Tick samples" in captured

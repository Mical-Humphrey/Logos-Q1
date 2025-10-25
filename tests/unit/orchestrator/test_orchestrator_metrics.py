from __future__ import annotations

import datetime as dt

from logos.orchestrator.metrics import MetricsRecorder


def test_metrics_recorder_snapshot() -> None:
    recorder = MetricsRecorder(window=10)
    recorder.record_tick("alpha", 0.1)
    recorder.record_tick("alpha", 0.2, skipped=True)
    recorder.record_tick("beta", 0.3)
    recorder.record_queue_depth(4)
    recorder.record_queue_depth(6)
    recorder.record_error("timeout")

    stamp = dt.datetime(2025, 1, 1, 12, 0, 0, tzinfo=dt.timezone.utc)
    snap = recorder.snapshot(timestamp=stamp)

    assert snap["timestamp"] == stamp.isoformat()
    assert snap["ticks"] == 3
    assert snap["queue_depth_max"] == 6
    assert snap["error_counts"] == {"timeout": 1}
    assert abs(snap["skip_rate"] - (1 / 3)) < 1e-6
    assert abs(snap["avg_latency_s"] - (0.1 + 0.2 + 0.3) / 3) < 1e-6
    assert abs(snap["p95_latency_s"] - 0.29) < 1e-2

    # Snapshot should not mutate recorded ticks
    assert len(list(recorder.iter_ticks())) == 3

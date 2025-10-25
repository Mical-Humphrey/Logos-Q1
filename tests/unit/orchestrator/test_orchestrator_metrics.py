from __future__ import annotations

import datetime as dt
from typing import cast

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
    ticks = cast(int, snap["ticks"])
    queue_depth_max = cast(int, snap["queue_depth_max"])
    error_counts = cast(dict[str, int], snap["error_counts"])
    skip_rate = cast(float, snap["skip_rate"])
    avg_latency = cast(float, snap["avg_latency_s"])
    p95_latency = cast(float, snap["p95_latency_s"])

    assert ticks == 3
    assert queue_depth_max == 6
    assert error_counts == {"timeout": 1}
    assert abs(skip_rate - (1 / 3)) < 1e-6
    assert abs(avg_latency - (0.1 + 0.2 + 0.3) / 3) < 1e-6
    assert abs(p95_latency - 0.29) < 1e-2

    # Snapshot should not mutate recorded ticks
    assert len(list(recorder.iter_ticks())) == 3

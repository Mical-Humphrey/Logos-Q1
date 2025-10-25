from __future__ import annotations

from datetime import timedelta

from logos.orchestrator.smoke import run_smoke


def test_orchestrator_smoke(tmp_path):
    result = run_smoke(
        num_strategies=20,
        duration=timedelta(minutes=2),
        cadence=timedelta(seconds=15),
        time_budget=timedelta(seconds=2.5),
        jitter=timedelta(seconds=1),
        seed=321,
        output_dir=tmp_path,
    )

    p95_limit = 0.25 * 15.0
    assert result.metrics["p95_latency_s"] <= p95_limit
    assert result.scheduler["skip_rate"] < 0.05
    assert not result.router["halted"]
    assert result.router["pending_orders"] == 0
    assert result.metrics_path is not None and result.metrics_path.exists()
    assert result.summary_path is not None and result.summary_path.exists()

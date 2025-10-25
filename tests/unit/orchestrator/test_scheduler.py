from __future__ import annotations

import datetime as dt

from logos.orchestrator.scheduler import Scheduler, StrategySpec


def _now() -> dt.datetime:
    return dt.datetime(2025, 1, 1, 12, 0, 0, tzinfo=dt.timezone.utc)


def test_scheduler_due_and_mark_finish_sets_next_run():
    now = _now()
    scheduler = Scheduler(now=now)
    spec = StrategySpec(
        name="alpha",
        cadence=dt.timedelta(seconds=30),
        time_budget=dt.timedelta(seconds=10),
    )
    scheduler.register(spec)

    due = scheduler.due(now)
    assert due == ["alpha"]

    scheduler.mark_start("alpha", now)
    finish = now + dt.timedelta(seconds=5)
    scheduler.mark_finish("alpha", finish)

    stats = scheduler.stats()["alpha"]
    next_run = dt.datetime.fromisoformat(stats["next_run"])
    expected_lower = finish + spec.cadence - dt.timedelta(milliseconds=1)
    expected_upper = finish + spec.cadence + dt.timedelta(milliseconds=1)
    assert expected_lower <= next_run <= expected_upper
    assert stats["executions"] == 1
    assert stats["overruns"] == 0


def test_scheduler_skip_on_overrun():
    now = _now()
    scheduler = Scheduler(now=now)
    spec = StrategySpec(
        name="bravo",
        cadence=dt.timedelta(seconds=20),
        time_budget=dt.timedelta(seconds=8),
    )
    scheduler.register(spec)

    scheduler.mark_start("bravo", now)
    scheduler.mark_finish("bravo", now + dt.timedelta(seconds=12))
    stats = scheduler.stats()["bravo"]
    assert stats["overruns"] == 1
    next_run = dt.datetime.fromisoformat(stats["next_run"])
    # Overrun should skip one cadence, effectively cadence * 2 from finish.
    expected = now + dt.timedelta(seconds=12) + spec.cadence * 2
    assert abs((next_run - expected).total_seconds()) < 0.5
    assert stats["skips"] == 1


def test_scheduler_heartbeat_and_watchdog():
    now = _now()
    scheduler = Scheduler(now=now)
    spec = StrategySpec(
        name="charlie",
        cadence=dt.timedelta(seconds=15),
        time_budget=dt.timedelta(seconds=5),
        heartbeat_timeout=dt.timedelta(seconds=20),
    )
    scheduler.register(spec)
    late = scheduler.late_heartbeats(now + dt.timedelta(seconds=30))
    assert late == ["charlie"]

    scheduler.record_heartbeat("charlie", now + dt.timedelta(seconds=5))
    late = scheduler.late_heartbeats(now + dt.timedelta(seconds=15))
    assert late == []

    scheduler.mark_start("charlie", now + dt.timedelta(seconds=20))
    overruns = scheduler.running_over_budget(now + dt.timedelta(seconds=30))
    assert overruns == ["charlie"]


def test_scheduler_jitter_seed_deterministic():
    now = _now()
    jitter = dt.timedelta(seconds=3)
    spec = StrategySpec(
        name="delta",
        cadence=dt.timedelta(seconds=10),
        time_budget=dt.timedelta(seconds=4),
        jitter=jitter,
    )
    scheduler = Scheduler(now=now, seed=123)
    scheduler.register(spec)
    next_run = dt.datetime.fromisoformat(scheduler.stats()["delta"]["next_run"])
    delta_seconds = (next_run - now).total_seconds()
    assert -jitter.total_seconds() <= delta_seconds <= jitter.total_seconds()

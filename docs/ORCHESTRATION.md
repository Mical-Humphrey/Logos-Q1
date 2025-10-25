# Orchestration Guardrails & Router

Phase 7 adds primitives that let Logos coordinate dozens of strategies without
sacrificing determinism or safety. Everything lives under `logos/orchestrator/`
and ships with unit coverage plus a synthetic smoke.

## Scheduler

- **Cadence & jitter** – `Scheduler` honours per-strategy cadences while applying
  optional jitter so that large cohorts never fire in lock-step.
- **Time budgets** – if a run exceeds the configured budget the scheduler skips
  the next slot (`skip-on-overrun`) and increments overrun counters for metrics.
- **Heartbeats & watchdogs** – `record_heartbeat` captures liveness updates and
  `late_heartbeats()` surfaces stragglers. `running_over_budget()` highlights
  strategies still in-flight beyond their budget so infrastructure can act.
- **Deterministic fixtures** – pass a seed to `Scheduler` to obtain reproducible
  jitter for CI or integration tests.

## Order Router

- **Idempotency** – requests carry a `client_order_id`; replays return the
  original decision so upstream retries are safe.
- **Rate limiting** – the router enforces a sliding one-second window per
  strategy. Breaches yield `rate_limited` rejections before orders hit the
  broker.
- **Fail closed** – reconciliation marks the router as halted whenever fills
  arrive for unknown orders, preventing new submissions until operators review
  the drift.
- **Transactional snapshots** – `OrderRouter.snapshot()` captures in-flight
  orders, idempotency cache, and rate windows so operators can persist state
  with `save(path)` and restore via `OrderRouter.load(path)`.

## Metrics

`MetricsRecorder` keeps a rolling window of tick latency, skip rate, queue depth,
and error counts. Snapshots are serialisable and can be logged or scraped by
other diagnostics tooling.

## Usage Sketch

```python
from datetime import datetime, timedelta
from logos.orchestrator import Scheduler, StrategySpec

scheduler = Scheduler(seed=7)
scheduler.register(
    StrategySpec(
        name="mean_reversion",
        cadence=timedelta(seconds=30),
        time_budget=timedelta(seconds=5),
        jitter=timedelta(seconds=3),
    )
)

for strategy in scheduler.due(datetime.utcnow()):
    scheduler.mark_start(strategy)
    # ... run strategy ...
    scheduler.mark_finish(strategy)
```

See `tests/unit/orchestrator/` for runnable examples covering guardrails,
router reconciliation, and metrics snapshots. A full synthetic run is available
via `make phase7-smoke`, which emits JSON metrics under `runs/orchestrator/_ci/smoke/`.

## Live Integration

The live runner threads these primitives together (see `logos/live/runner.py`):

- Scheduler gates strategy loops on logical cadence and records runtime budgets.
- Router mediates submissions before `BrokerAdapter.place_order`, persisting
  snapshots to `router_state.json` for restarts.
- Metrics recorder streams JSONL snapshots to each session directory so CI can
  assert SLOs alongside fills and equity curves.
- Router snapshots are flushed every 30 seconds by default and on shutdown.
  Adjust `orchestrator_snapshot_interval_s` in `logos/config.py` when running
  multi-hour sessions that demand tighter recovery points.

### Regression Harness

`logos/live/regression.py` now reuses the live scheduler, router, and metrics
recorder so deterministic CI runs mirror production guardrails. The harness
writes `orchestrator_metrics.jsonl` and `router_state.json` artifacts to the
fixture run directory, giving baselines a like-for-like copy of live outputs.

### Operational Visibility

- `logos cli status` reads the latest `orchestrator_metrics.jsonl` entry and
  surfaces p95 latency, skip rate, queue depth, and sample counts alongside PnL.
- Operators can `tail -f runs/live/sessions/<run_id>/orchestrator_metrics.jsonl`
  during live trading to watch latency/skip SLOs evolve in real time.
- For restart drills, copy the persisted `router_state.json` back into the
  session directory before re-launching a halted runner so the router resumes
  with identical sequencing and idempotency caches.

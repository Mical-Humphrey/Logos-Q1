from __future__ import annotations

import json
import random
import argparse
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Deque, Dict, List, Optional, Sequence, Tuple

from .metrics import MetricsRecorder
from .router import FillReport, OrderDecision, OrderRequest, OrderRouter
from .scheduler import Scheduler, StrategySpec


@dataclass
class SmokeResult:
    metrics: Dict[str, object]
    scheduler: Dict[str, object]
    router: Dict[str, object]
    metrics_path: Optional[Path]
    summary_path: Optional[Path]


def run_smoke(
    *,
    num_strategies: int = 50,
    duration: timedelta = timedelta(minutes=15),
    cadence: timedelta = timedelta(seconds=20),
    time_budget: timedelta = timedelta(seconds=3),
    jitter: timedelta = timedelta(seconds=2),
    seed: int = 9402,
    output_dir: Optional[Path | str] = None,
) -> SmokeResult:
    """Run the synthetic orchestrator smoke and return aggregated metrics."""

    if num_strategies <= 0:
        raise ValueError("num_strategies must be positive")
    if duration <= timedelta(0):
        raise ValueError("duration must be positive")

    rng = random.Random(seed)
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = start + duration

    scheduler = Scheduler(now=start, seed=seed)
    metrics = MetricsRecorder(window=1024)
    router = OrderRouter(rate_limit_per_sec=8, max_inflight=512)

    specs: Dict[str, StrategySpec] = {}
    client_sequences: Dict[str, int] = {}
    for idx in range(num_strategies):
        name = f"strategy_{idx:03d}"
        offset_seconds = rng.uniform(0, float(cadence.total_seconds()))
        spec = StrategySpec(
            name=name,
            cadence=cadence,
            time_budget=time_budget,
            jitter=jitter,
            heartbeat_timeout=cadence * 3,
        )
        scheduler.register(spec, start_at=start + timedelta(seconds=offset_seconds))
        specs[name] = spec
        client_sequences[name] = 0

    pending_fills: List[Tuple[datetime, OrderDecision, OrderRequest]] = []
    replay_queue: Deque[Tuple[datetime, OrderRequest]] = deque()
    router_rejections: Counter[str] = Counter()
    router_unknowns: List[str] = []

    now = start
    while now <= end:
        due = scheduler.due(now)
        metrics.record_queue_depth(len(due))
        for name in due:
            scheduler.mark_start(name, now)
            spec = specs[name]
            overrun = rng.random() < 0.015
            runtime_base = spec.time_budget.total_seconds() * rng.uniform(0.45, 0.65)
            if overrun:
                runtime_seconds = spec.time_budget.total_seconds() * rng.uniform(
                    1.05, 1.25
                )
            else:
                runtime_seconds = max(0.01, runtime_base)
            finish_time = now + timedelta(seconds=runtime_seconds)
            scheduler.mark_finish(name, finish_time)
            scheduler.record_heartbeat(name, finish_time)

            metrics.record_tick(
                name,
                latency_s=runtime_seconds,
                skipped=runtime_seconds > spec.time_budget.total_seconds(),
            )

            client_id = client_sequences[name]
            client_sequences[name] += 1
            request = OrderRequest(
                strategy_id=name,
                symbol="SYNTH",
                quantity=1.0,
                price=100.0,
                client_order_id=f"{name}-{client_id:05d}",
                timestamp=now,
            )
            decision = router.submit(request, now=now)
            if decision.accepted and decision.order_id is not None:
                fill_delay = rng.uniform(0.05, 0.35)
                pending_fills.append(
                    (finish_time + timedelta(seconds=fill_delay), decision, request)
                )
            else:
                router_rejections[decision.reason or "rejected"] += 1
                metrics.record_error(decision.reason or "rejected")
            replay_time = now + timedelta(seconds=0.5)
            replay_queue.append((replay_time, request))

        while replay_queue and replay_queue[0][0] <= now:
            _, replay_request = replay_queue.popleft()
            replay_decision = router.submit(replay_request, now=now)
            if (
                not replay_decision.accepted
                and replay_decision.reason != "rate_limited"
            ):
                router_rejections[replay_decision.reason or "rejected"] += 1
                metrics.record_error(replay_decision.reason or "rejected")

        fills_to_publish: List[FillReport] = []
        remaining_fills: List[Tuple[datetime, OrderDecision, OrderRequest]] = []
        for ready_at, decision, request in pending_fills:
            if ready_at <= now:
                fills_to_publish.append(
                    FillReport(
                        order_id=decision.order_id or "",
                        status="filled",
                        filled_qty=request.quantity,
                        timestamp=now,
                    )
                )
            else:
                remaining_fills.append((ready_at, decision, request))
        pending_fills = remaining_fills
        if fills_to_publish:
            result = router.reconcile(fills_to_publish)
            if result.unknown_fills:
                router_unknowns.extend(result.unknown_fills)
        now += timedelta(seconds=1)

    if pending_fills:
        remainder_reports = [
            FillReport(
                order_id=decision.order_id or "",
                status="filled",
                filled_qty=request.quantity,
                timestamp=end + timedelta(seconds=1),
            )
            for _, decision, request in pending_fills
        ]
        result = router.reconcile(remainder_reports)
        if result.unknown_fills:
            router_unknowns.extend(result.unknown_fills)

    snap = metrics.snapshot(timestamp=end)
    stats = scheduler.stats()
    executions = sum(int(row["executions"]) for row in stats.values())
    skips = sum(int(row["skips"]) for row in stats.values())
    overruns = sum(int(row["overruns"]) for row in stats.values())
    scheduler_payload = {
        "strategies": len(stats),
        "executions": executions,
        "skips": skips,
        "overruns": overruns,
        "skip_rate": (skips / executions) if executions else 0.0,
    }
    router_payload = {
        "halted": router.halted(),
        "pending_orders": len(router.pending_orders()),
        "rejection_counts": dict(router_rejections),
        "unknown_fills": tuple(router_unknowns),
    }

    metrics_path: Optional[Path] = None
    summary_path: Optional[Path] = None
    if output_dir is not None:
        base = Path(output_dir)
        logs_dir = base / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        metrics_path = logs_dir / "metrics.jsonl"
        summary_path = base / "summary.json"
        metrics_line = json.dumps(snap, separators=(",", ":"))
        metrics_path.write_text(metrics_line + "\n", encoding="utf-8")
        summary_payload = {
            "metrics": snap,
            "scheduler": scheduler_payload,
            "router": router_payload,
        }
        summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    return SmokeResult(
        metrics=snap,
        scheduler=scheduler_payload,
        router=router_payload,
        metrics_path=metrics_path,
        summary_path=summary_path,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic orchestrator smoke run")
    parser.add_argument(
        "--strategies", type=int, default=50, help="Number of strategies to simulate"
    )
    parser.add_argument(
        "--duration-min",
        type=float,
        default=15.0,
        help="Simulation duration in minutes",
    )
    parser.add_argument(
        "--cadence-sec", type=float, default=20.0, help="Strategy cadence in seconds"
    )
    parser.add_argument(
        "--time-budget-sec",
        type=float,
        default=3.0,
        help="Per-strategy time budget in seconds",
    )
    parser.add_argument(
        "--jitter-sec", type=float, default=2.0, help="Cadence jitter in seconds"
    )
    parser.add_argument(
        "--seed", type=int, default=9402, help="Seed for deterministic jitter/runtime"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("runs/orchestrator/_ci/smoke"),
        help="Directory for artifacts",
    )
    args = parser.parse_args(argv)

    result = run_smoke(
        num_strategies=args.strategies,
        duration=timedelta(minutes=args.duration_min),
        cadence=timedelta(seconds=args.cadence_sec),
        time_budget=timedelta(seconds=args.time_budget_sec),
        jitter=timedelta(seconds=args.jitter_sec),
        seed=args.seed,
        output_dir=args.output_dir,
    )

    print(f"strategies={result.scheduler['strategies']}")
    print(f"executions={result.scheduler['executions']}")
    print(f"skip_rate={result.scheduler['skip_rate']:.6f}")
    print(f"p95_latency_s={result.metrics['p95_latency_s']}")
    print(f"avg_latency_s={result.metrics['avg_latency_s']}")
    print(f"queue_depth_max={result.metrics['queue_depth_max']}")
    if result.metrics_path is not None:
        print(f"metrics_path={result.metrics_path}")
    if result.summary_path is not None:
        print(f"summary_path={result.summary_path}")
    if result.router["unknown_fills"]:
        print(f"unknown_fills={result.router['unknown_fills']}")
        return 2
    return 0


__all__ = ["run_smoke", "SmokeResult", "main"]


if __name__ == "__main__":  # pragma: no cover - CLI glue
    raise SystemExit(main())

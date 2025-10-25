from __future__ import annotations

import math
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime
from typing import Deque, Dict, Iterable, Optional


@dataclass
class TickRecord:
    strategy: str
    latency_s: float
    skipped: bool = False


class MetricsRecorder:
    """Rolling window metrics for orchestrator diagnostics."""

    def __init__(self, *, window: int = 200) -> None:
        if window <= 0:  # pragma: no cover - guard
            raise ValueError("window must be positive")
        self._window = window
        self._ticks: Deque[TickRecord] = deque(maxlen=window)
        self._queue_depths: Deque[int] = deque(maxlen=window)
        self._errors: Counter[str] = Counter()
        self._last_snapshot_at: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Recording hooks
    # ------------------------------------------------------------------
    def record_tick(
        self, strategy: str, latency_s: float, *, skipped: bool = False
    ) -> None:
        latency = max(0.0, float(latency_s))
        self._ticks.append(
            TickRecord(strategy=strategy, latency_s=latency, skipped=skipped)
        )

    def record_queue_depth(self, depth: int) -> None:
        self._queue_depths.append(max(0, int(depth)))

    def record_error(self, kind: str) -> None:
        self._errors[kind] += 1

    # ------------------------------------------------------------------
    # Reporting helpers
    # ------------------------------------------------------------------
    def snapshot(self, *, timestamp: Optional[datetime] = None) -> Dict[str, object]:
        ts = timestamp or datetime.utcnow()
        self._last_snapshot_at = ts
        latencies = [record.latency_s for record in self._ticks]
        skipped = sum(1 for record in self._ticks if record.skipped)
        total = len(self._ticks)
        skip_rate = float(skipped) / total if total else 0.0
        p95 = self._percentile(latencies, 95.0) if latencies else 0.0
        avg_latency = sum(latencies) / total if total else 0.0
        queue_depth = max(self._queue_depths) if self._queue_depths else 0
        return {
            "timestamp": ts.isoformat(),
            "ticks": total,
            "avg_latency_s": round(avg_latency, 6),
            "p95_latency_s": round(p95, 6),
            "skip_rate": round(skip_rate, 6),
            "queue_depth_max": queue_depth,
            "error_counts": dict(self._errors),
        }

    def iter_ticks(self) -> Iterable[TickRecord]:
        return list(self._ticks)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _percentile(values: Iterable[float], percentile: float) -> float:
        seq = sorted(values)
        if not seq:
            return 0.0
        k = (len(seq) - 1) * (percentile / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return seq[int(k)]
        d0 = seq[int(f)] * (c - k)
        d1 = seq[int(c)] * (k - f)
        return d0 + d1


__all__ = ["MetricsRecorder", "TickRecord"]

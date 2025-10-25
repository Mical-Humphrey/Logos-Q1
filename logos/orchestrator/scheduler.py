from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional


@dataclass(frozen=True)
class StrategySpec:
    """Configuration describing how a strategy should be scheduled."""

    name: str
    cadence: timedelta
    time_budget: timedelta
    jitter: timedelta = timedelta(0)
    heartbeat_timeout: Optional[timedelta] = None

    def __post_init__(self) -> None:
        if self.cadence <= timedelta(0):  # pragma: no cover - guard
            raise ValueError("cadence must be positive")
        if self.time_budget <= timedelta(0):  # pragma: no cover - guard
            raise ValueError("time_budget must be positive")
        if self.jitter < timedelta(0):  # pragma: no cover - guard
            raise ValueError("jitter must be non-negative")


@dataclass
class StrategyState:
    """Mutable runtime state associated with a strategy."""

    next_run: datetime
    last_run: Optional[datetime] = None
    running: bool = False
    started_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None
    overruns: int = 0
    skips: int = 0
    executions: int = 0
    total_runtime: timedelta = field(default_factory=lambda: timedelta(0))

    def mark_running(self, when: datetime) -> None:
        self.running = True
        self.started_at = when

    def mark_finished(self, when: datetime, runtime: timedelta) -> None:
        self.running = False
        self.last_run = when
        self.started_at = None
        self.executions += 1
        self.total_runtime += runtime

    @property
    def average_runtime(self) -> Optional[timedelta]:
        if self.executions == 0:
            return None
        return self.total_runtime / self.executions


class Scheduler:
    """Coordinate many strategies while honouring guardrails.

    Key features:
    - Per-strategy cadence with optional jitter.
    - Time budgets with skip-on-overrun behaviour.
    - Heartbeat tracking for watchdogs.
    - Deterministic outcomes when seeded (useful for tests/fixtures).
    """

    def __init__(
        self,
        *,
        now: Optional[datetime] = None,
        seed: Optional[int] = None,
    ) -> None:
        self._rng = random.Random(seed)
        self._specs: Dict[str, StrategySpec] = {}
        self._states: Dict[str, StrategyState] = {}
        self._now = now or datetime.utcnow()

    # ------------------------------------------------------------------
    # Registration & configuration
    # ------------------------------------------------------------------
    def register(
        self,
        spec: StrategySpec,
        *,
        start_at: Optional[datetime] = None,
    ) -> None:
        if spec.name in self._specs:
            raise ValueError(f"Strategy '{spec.name}' already registered")
        anchor = start_at or self._now
        first_run = self._apply_jitter(anchor, spec)
        if first_run < self._now:
            first_run = self._now
        self._specs[spec.name] = spec
        self._states[spec.name] = StrategyState(next_run=first_run)

    def register_many(
        self,
        specs: Iterable[StrategySpec],
        *,
        start_at: Optional[datetime] = None,
    ) -> None:
        for spec in specs:
            self.register(spec, start_at=start_at)

    # ------------------------------------------------------------------
    # Execution flow
    # ------------------------------------------------------------------
    def due(self, now: Optional[datetime] = None) -> List[str]:
        current = now or datetime.utcnow()
        due: List[str] = []
        for name, state in self._states.items():
            if state.running:
                continue
            if current >= state.next_run:
                due.append(name)
        due.sort(key=lambda n: self._states[n].next_run)
        return due

    def mark_start(self, name: str, when: Optional[datetime] = None) -> None:
        state = self._states[name]
        if state.running:
            raise RuntimeError(f"Strategy '{name}' already running")
        state.mark_running(when or datetime.utcnow())

    def mark_finish(self, name: str, when: Optional[datetime] = None) -> None:
        spec = self._specs[name]
        state = self._states[name]
        if not state.running:
            raise RuntimeError(f"Strategy '{name}' is not marked running")
        end_time = when or datetime.utcnow()
        runtime = end_time - (state.started_at or end_time)
        state.mark_finished(end_time, runtime)

        over_budget = runtime > spec.time_budget
        if over_budget:
            state.overruns += 1

        next_base = end_time + spec.cadence
        if over_budget:
            # Skip the next cadence entirely to avoid compounding lag.
            next_base = next_base + spec.cadence
            state.skips += 1
        state.next_run = self._apply_jitter(next_base, spec)

    # ------------------------------------------------------------------
    # Heartbeats & watchdogs
    # ------------------------------------------------------------------
    def record_heartbeat(self, name: str, when: Optional[datetime] = None) -> None:
        state = self._states[name]
        state.last_heartbeat = when or datetime.utcnow()

    def late_heartbeats(self, now: Optional[datetime] = None) -> List[str]:
        current = now or datetime.utcnow()
        late: List[str] = []
        for name, spec in self._specs.items():
            timeout = spec.heartbeat_timeout or spec.cadence * 2
            last = self._states[name].last_heartbeat
            if last is None or current - last > timeout:
                late.append(name)
        return late

    def running_over_budget(self, now: Optional[datetime] = None) -> List[str]:
        current = now or datetime.utcnow()
        offenders: List[str] = []
        for name, spec in self._specs.items():
            state = self._states[name]
            if not state.running or state.started_at is None:
                continue
            if current - state.started_at > spec.time_budget:
                offenders.append(name)
        return offenders

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    def stats(self) -> Dict[str, Dict[str, object]]:
        payload: Dict[str, Dict[str, object]] = {}
        for name, state in self._states.items():
            payload[name] = {
                "next_run": state.next_run.isoformat(),
                "running": state.running,
                "executions": state.executions,
                "overruns": state.overruns,
                "skips": state.skips,
                "avg_runtime_s": (
                    state.average_runtime.total_seconds()
                    if state.average_runtime is not None
                    else None
                ),
            }
        return payload

    def next_run(self, name: str) -> datetime:
        return self._states[name].next_run

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _apply_jitter(self, anchor: datetime, spec: StrategySpec) -> datetime:
        if spec.jitter <= timedelta(0):
            return anchor
        jitter_seconds = spec.jitter.total_seconds()
        offset = self._rng.uniform(-jitter_seconds, jitter_seconds)
        return anchor + timedelta(seconds=offset)


__all__ = ["StrategySpec", "Scheduler"]

"""Orchestration utilities for coordinating strategy execution and order flow."""

from importlib import import_module
from typing import Any

from .scheduler import StrategySpec, Scheduler
from .router import (
    OrderRouter,
    OrderRequest,
    OrderDecision,
    FillReport,
    ReconciliationResult,
    RouterSnapshot,
)
from .metrics import MetricsRecorder

__all__ = [
    "StrategySpec",
    "Scheduler",
    "OrderRouter",
    "OrderRequest",
    "OrderDecision",
    "FillReport",
    "ReconciliationResult",
    "RouterSnapshot",
    "MetricsRecorder",
    "run_smoke",
    "SmokeResult",
]


def __getattr__(name: str) -> Any:
    if name in {"run_smoke", "SmokeResult"}:
        module = import_module("logos.orchestrator.smoke")
        return getattr(module, name)
    raise AttributeError(f"module 'logos.orchestrator' has no attribute {name!r}")

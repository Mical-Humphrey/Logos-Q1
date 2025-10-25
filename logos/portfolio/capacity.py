from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

__all__ = [
    "CapacityConfig",
    "compute_adv_notional",
    "compute_participation",
]


@dataclass(slots=True)
class CapacityConfig:
    """Capacity and turnover guard rails."""

    adv_lookback_days: int = 20
    warn_participation: float = 0.03
    max_participation: float = 0.05


def compute_adv_notional(observations: Iterable[float]) -> float:
    """Average daily notional volume helper with NaN filtering."""

    data = [float(x) for x in observations if np.isfinite(x)]
    if not data:
        return 0.0
    return float(np.mean(data))


def compute_participation(order_notional: float, adv_notional: float) -> float:
    """Return participation ratio guarding against divide-by-zero."""

    if adv_notional <= 0.0:
        return 0.0
    return float(abs(order_notional) / adv_notional)

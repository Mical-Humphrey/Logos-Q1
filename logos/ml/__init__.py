"""Offline machine learning advisory utilities (Phase 11).

The modules exposed here generate advisory insights only; application code must
collect explicit human approval before any recommendation is promoted into live
allocation or execution paths.
"""

from __future__ import annotations

from .regime import RegimeAdvisor, RegimeReport, classify_regime
from .vol import VolatilityAdvisor, VolatilityEnvelope
from .meta_allocator import (
    MetaAllocator,
    MetaAllocatorConfig,
    MetaAllocationProposal,
)
from .drift import DriftReport, detect_feature_drift, detect_pnl_drift

__all__ = [
    "RegimeAdvisor",
    "RegimeReport",
    "classify_regime",
    "VolatilityAdvisor",
    "VolatilityEnvelope",
    "MetaAllocator",
    "MetaAllocatorConfig",
    "MetaAllocationProposal",
    "DriftReport",
    "detect_feature_drift",
    "detect_pnl_drift",
]

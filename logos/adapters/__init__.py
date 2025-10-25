from __future__ import annotations

"""Hardened broker adapter implementations.

This namespace holds concrete connectors for supported venues.  The adapters
embed retry/backoff semantics, per-venue rate limiting, and idempotent order
tracking so orchestration code can remain small and deterministic during paper
soaks.
"""

from .common import (
    AdapterError,
    FatalAdapterError,
    OrderConflictError,
    RateLimitExceeded,
    RateLimiter,
    RetryConfig,
    RetryableError,
    retry,
)
from .ccxt_hardened import CCXTHardenedAdapter
from .alpaca import AlpacaAdapter
from .oanda import OandaAdapter

__all__ = [
    "AdapterError",
    "FatalAdapterError",
    "OrderConflictError",
    "RateLimitExceeded",
    "RateLimiter",
    "RetryConfig",
    "RetryableError",
    "retry",
    "CCXTHardenedAdapter",
    "AlpacaAdapter",
    "OandaAdapter",
]

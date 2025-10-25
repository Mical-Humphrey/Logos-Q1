"""Utility façade exported at ``logos.utils``.

The project historically exposed helpers directly off ``logos.utils``.  While
the package now houses indexing helpers and test shims, we keep the public
surface untouched by implementing the legacy helpers here.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Dict

from ..paths import ensure_dirs as _ensure_dirs

__all__ = ["ensure_dirs", "setup_logging", "parse_params"]


def ensure_dirs(extra: Iterable[Path] | None = None) -> None:
    """Idempotently create standard directories; keeps CLI/backfills happy."""

    _ensure_dirs(extra)


def setup_logging(level: str = "INFO") -> None:
    """Proxy to the shared logging configurator for legacy callers."""
    from ..logging_setup import setup_app_logging

    setup_app_logging(level)


def parse_params(param_str: str | None) -> Dict[str, float | int | str]:
    """Parse ``k=v`` pairs with soft typing (int, float, else str)."""

    params: Dict[str, float | int | str] = {}
    if not param_str:
        return params
    for raw_pair in param_str.split(","):
        pair = raw_pair.strip()
        if not pair or "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        key = key.strip()
        token = value.strip()
        if token.isdigit():
            params[key] = int(token)
            continue
        try:
            params[key] = float(token)
        except ValueError:
            params[key] = token
    return params

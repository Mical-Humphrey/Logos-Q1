# src/utils.py
# =============================================================================
# Purpose:
#   Small utilities used across the project.
#
# Summary:
#   - ensure_dirs(): idempotently create input_data/runs/notebooks directories
#   - setup_logging(): configure console+file logging
#   - parse_params(): convert "k=v,k=v" strings to a dict with basic typing
#
# Design Notes:
#   - Keep helpers minimal and dependency-free.
# =============================================================================
from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable

from .logging_setup import setup_app_logging
from .paths import ensure_dirs as _ensure_dirs


def ensure_dirs(extra: Iterable[Path] | None = None) -> None:
    """Proxy to `logos.paths.ensure_dirs` kept for backwards compatibility."""
    _ensure_dirs(extra)


def setup_logging(level: str = "INFO") -> None:
    """Proxy to the shared logging configurator for legacy callers."""
    setup_app_logging(level)


def parse_params(param_str: str | None) -> Dict[str, float | int | str]:
    """Parse a simple 'k=v,k=v' string into a dict with best-effort typing.

    Integers remain int; floats remain float; everything else is str.
    """
    params: Dict[str, float | int | str] = {}
    if not param_str:
        return params
    for pair in param_str.split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        v = v.strip()
        if v.isdigit():
            params[k.strip()] = int(v)
        else:
            try:
                params[k.strip()] = float(v)
            except ValueError:
                params[k.strip()] = v
    return params

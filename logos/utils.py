# src/utils.py
# =============================================================================
# Purpose:
#   Small utilities used across the project.
#
# Summary:
#   - ensure_dirs(): idempotently create data/runs/notebooks directories
#   - setup_logging(): configure console+file logging
#   - parse_params(): convert "k=v,k=v" strings to a dict with basic typing
#
# Design Notes:
#   - Keep helpers minimal and dependency-free.
# =============================================================================
from __future__ import annotations
import os
import logging
from typing import Dict

def ensure_dirs() -> None:
    """Create project directories for data and outputs if they don't exist."""
    os.makedirs("data", exist_ok=True)
    os.makedirs("runs", exist_ok=True)
    os.makedirs(os.path.join("runs", "logs"), exist_ok=True)
    os.makedirs("notebooks", exist_ok=True)

def setup_logging(level: str = "INFO") -> None:
    """Configure logging to both a file and the console.
    
    File logs help with debugging and historical record of runs.
    """
    ensure_dirs()
    log_file = os.path.join("runs", "logs", "app.log")
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(log_file, mode="a"),
            logging.StreamHandler(),
        ],
    )

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

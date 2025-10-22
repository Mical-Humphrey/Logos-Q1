"""Lightweight state persistence for live trading runs."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from core.io.atomic_write import atomic_write_text
from core.io.dirs import ensure_dir


@dataclass
class LiveState:
    """Snapshot persisted between loop iterations."""

    session_id: str
    last_bar_iso: Optional[str] = None
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    equity: float = 0.0
    peak_equity: float = 0.0
    open_orders: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    positions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    consecutive_rejects: int = 0


def default_state(session_id: str) -> LiveState:
    return LiveState(session_id=session_id)


def load_state(path: Path, session_id: str) -> LiveState:
    if not path.exists():
        return default_state(session_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("session_id", None)
    return LiveState(session_id=session_id, **data)


def save_state(state: LiveState, path: Path) -> None:
    atomic_write_text(
        path,
        json.dumps(asdict(state), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def append_event(event: Dict[str, Any], path: Path) -> None:
    """Append a structured event to the jsonl log."""
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")
        fh.flush()
        os.fsync(fh.fileno())

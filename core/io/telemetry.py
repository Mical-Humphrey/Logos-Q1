"""Lightweight telemetry writer for structured JSONL events."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .dirs import ensure_dir


def _serialize_event(event: Mapping[str, Any]) -> str:
    return json.dumps(event, sort_keys=True, separators=(",", ":"))


def record_event(
    path: Path,
    event_type: str,
    payload: Mapping[str, Any] | None = None,
    *,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Append a telemetry event to ``path`` as a JSON line."""

    ensure_dir(path.parent)
    now = timestamp or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    event: dict[str, Any] = {
        "ts": now.isoformat(),
        "event": event_type,
    }
    if payload:
        event.update(payload)

    line = _serialize_event(event)
    with path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return event


__all__ = ["record_event"]

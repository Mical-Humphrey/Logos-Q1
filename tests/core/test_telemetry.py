from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from core.io.telemetry import record_event


def test_record_event_appends_jsonl(tmp_path: Path) -> None:
    log_path = tmp_path / "telemetry.jsonl"
    ts = datetime(2025, 10, 21, 12, 0, 0, tzinfo=timezone.utc)

    payload = {"reason": "ingest_accepted", "rows": 3}
    event = record_event(log_path, "ingest", payload, timestamp=ts)

    assert event["ts"] == ts.isoformat()
    assert event["event"] == "ingest"
    assert event["rows"] == 3

    text = log_path.read_text(encoding="utf-8").strip()
    assert text
    stored = json.loads(text)
    assert stored == event


def test_record_event_newline_normalized(tmp_path: Path) -> None:
    log_path = tmp_path / "telemetry.jsonl"

    record_event(log_path, "ingest", {"rows": 1})
    record_event(log_path, "ingest", {"rows": 2})

    raw = log_path.read_bytes()
    assert b"\r\n" not in raw
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2

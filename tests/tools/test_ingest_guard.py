from __future__ import annotations

import json
import datetime as dt
from pathlib import Path

from core.io.ingest_guard import GuardConfig, guard_file


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    headers = list(rows[0].keys()) if rows else []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        if headers:
            handle.write(",".join(headers) + "\n")
        for row in rows:
            line = ",".join(str(row.get(col, "")) for col in headers)
            handle.write(line + "\n")


def _load_json_lines(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_guard_accepts_valid_file(tmp_path: Path) -> None:
    csv_path = tmp_path / "prices.csv"
    rows = [
        {
            "timestamp": "2025-01-01T09:30:00+00:00",
            "symbol": "MSFT",
            "price": 100.0,
        },
        {
            "timestamp": "2025-01-01T09:31:00+00:00",
            "symbol": "MSFT",
            "price": 101.0,
        },
    ]
    _write_csv(csv_path, rows)

    schema = {
        "type": "object",
        "required": ["timestamp", "symbol", "price"],
        "properties": {
            "timestamp": {"type": "string"},
            "symbol": {"type": "string"},
            "price": {"type": "string", "pattern": r"^-?\d+(?:\.\d+)?$"},
        },
    }
    telemetry_path = tmp_path / "telemetry.jsonl"
    config = GuardConfig(
        timestamp_column="timestamp",
        stale_after_seconds=3600,
        schema=schema,
    )

    current = dt.datetime(2025, 1, 1, 9, 31, 30, tzinfo=dt.timezone.utc)

    result = guard_file(
        csv_path,
        config=config,
        telemetry_path=telemetry_path,
        now=lambda: current,
    )

    assert result.status == "accepted"
    assert result.reason is None
    assert result.rows == 2
    assert result.metadata["newest_timestamp"].startswith("2025-01-01T09:31")

    events = _load_json_lines(telemetry_path)
    assert len(events) == 1
    assert events[0]["event"] == "ingest_accepted"
    assert events[0]["rows"] == 2


def test_guard_quarantines_on_schema_failure(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad.csv"
    rows = [
        {
            "timestamp": "2025-01-01T09:30:00+00:00",
            "symbol": "MSFT",
            "price": "not-a-number",
        }
    ]
    _write_csv(csv_path, rows)

    schema = {
        "type": "object",
        "required": ["timestamp", "symbol", "price"],
        "properties": {
            "timestamp": {"type": "string"},
            "symbol": {"type": "string"},
            "price": {"type": "string", "pattern": r"^-?\d+(?:\.\d+)?$"},
        },
    }
    telemetry_path = tmp_path / "telemetry.jsonl"
    quarantine_root = tmp_path / "quarantine"

    result = guard_file(
        csv_path,
        config=GuardConfig(schema=schema),
        telemetry_path=telemetry_path,
        quarantine_root=quarantine_root,
    )

    assert result.status == "quarantined"
    assert result.reason == "schema_validation_error"
    assert result.quarantine_path is not None
    assert result.quarantine_path.exists()
    assert not csv_path.exists()

    events = _load_json_lines(telemetry_path)
    assert events and events[0]["event"] == "ingest_quarantined"
    assert events[0]["reason"] == "schema_validation_error"


def test_guard_quarantines_stale_data(tmp_path: Path) -> None:
    csv_path = tmp_path / "stale.csv"
    rows = [
        {
            "timestamp": "2025-01-01T09:30:00+00:00",
            "symbol": "MSFT",
            "price": 100.0,
        }
    ]
    _write_csv(csv_path, rows)

    telemetry_path = tmp_path / "telemetry.jsonl"
    quarantine_root = tmp_path / "quarantine"

    result = guard_file(
        csv_path,
        config=GuardConfig(timestamp_column="timestamp", stale_after_seconds=60),
        telemetry_path=telemetry_path,
        quarantine_root=quarantine_root,
        now=lambda: dt.datetime(2025, 1, 1, 9, 32, tzinfo=dt.timezone.utc),
    )

    assert result.status == "quarantined"
    assert result.reason == "stale_data"
    assert result.quarantine_path is not None
    assert not csv_path.exists()

    events = _load_json_lines(telemetry_path)
    assert events and events[0]["reason"] == "stale_data"

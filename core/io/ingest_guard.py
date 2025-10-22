"""CSV ingestion guard with schema validation, stale-data checks, and telemetry."""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .chunked_reader import (
    ChunkedCSVIterator,
    ReaderLimitError,
    SchemaValidationError,
    Sample,
    read_csv_chunked,
)
from .quarantine import move_to_quarantine
from .telemetry import record_event

logger = logging.getLogger(__name__)

UTC = dt.timezone.utc


@dataclass(slots=True)
class GuardConfig:
    """Configuration for :func:`guard_file`."""

    timestamp_column: str = "timestamp"
    stale_after_seconds: float | None = None
    max_rows: int | None = None
    max_bytes: int | None = None
    max_seconds: float | None = None
    sample_lines: int = 5
    schema: Mapping[str, Any] | None = None


@dataclass(slots=True)
class GuardResult:
    """Outcome returned by :func:`guard_file`."""

    path: Path
    status: str
    reason: str | None
    rows: int
    bytes_read: int
    sample: Sample | None
    metadata: dict[str, Any]
    quarantine_path: Path | None
    telemetry: dict[str, Any] | None


class _TimestampError(ValueError):
    pass


def _parse_timestamp(value: str) -> dt.datetime:
    token = value.strip()
    if token.endswith("Z"):
        token = token[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(token)
    except ValueError as exc:  # pragma: no cover - defensive
        raise _TimestampError(f"invalid ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _ensure_timestamp(raw: Any, column: str) -> dt.datetime:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise _TimestampError(f"missing timestamp column '{column}'")
    if not isinstance(raw, str):
        raw = str(raw)
    return _parse_timestamp(raw)


def _sample_from(iterator: ChunkedCSVIterator | None) -> Sample | None:
    if iterator is None:
        return None
    return iterator.metadata.sample


def guard_file(
    path: Path,
    *,
    config: GuardConfig,
    telemetry_path: Path | None = None,
    quarantine_root: Path | None = None,
    now: Callable[[], dt.datetime] | None = None,
) -> GuardResult:
    """Evaluate *path* using ``config`` and return the guard outcome."""

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"ingest guard cannot locate {path}")

    iterator: ChunkedCSVIterator | None = None
    rows = 0
    newest: dt.datetime | None = None
    oldest: dt.datetime | None = None

    def _emit_telemetry(event_type: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if telemetry_path is None:
            return None
        event_ts = now() if now is not None else dt.datetime.now(UTC)
        if event_ts.tzinfo is None:
            event_ts = event_ts.replace(tzinfo=UTC)
        return record_event(telemetry_path, event_type, payload, timestamp=event_ts)

    def _quarantine(reason: str, detail: str, sample: Sample | None, meta: dict[str, Any]) -> GuardResult:
        dest = move_to_quarantine(
            path,
            quarantine_root=quarantine_root,
            reason=reason,
            sample_lines=list(sample.lines) if sample else None,
        )
        telemetry_payload = {
            "path": str(path),
            "dest_path": str(dest),
            "reason": reason,
            "detail": detail,
            "rows": meta.get("rows", 0),
            "bytes_read": meta.get("bytes_read", 0),
        }
        telemetry_event = _emit_telemetry("ingest_quarantined", telemetry_payload)
        return GuardResult(
            path=path,
            status="quarantined",
            reason=reason,
            rows=meta.get("rows", 0),
            bytes_read=meta.get("bytes_read", 0),
            sample=sample,
            metadata=meta,
            quarantine_path=dest,
            telemetry=telemetry_event,
        )

    try:
        iterator = read_csv_chunked(
            path,
            schema=config.schema,
            max_rows=config.max_rows,
            max_bytes=config.max_bytes,
            max_seconds=config.max_seconds,
            sample_lines=config.sample_lines,
        )
        meta = iterator.metadata
        for row in iterator:
            rows += 1
            ts = _ensure_timestamp(row.get(config.timestamp_column), config.timestamp_column)
            if oldest is None or ts < oldest:
                oldest = ts
            if newest is None or ts > newest:
                newest = ts
    except ReaderLimitError as exc:
        metadata = {
            "rows": rows if rows else (iterator.metadata.rows if iterator else 0),
            "bytes_read": iterator.metadata.bytes_read if iterator else 0,
            "sample_sha256": iterator.metadata.sample.sha256 if iterator else None,
        }
        return _quarantine("limit_exceeded", str(exc), _sample_from(iterator), metadata)
    except SchemaValidationError as exc:
        metadata = {
            "rows": iterator.metadata.rows if iterator else rows,
            "bytes_read": iterator.metadata.bytes_read if iterator else 0,
            "sample_sha256": iterator.metadata.sample.sha256 if iterator else None,
        }
        return _quarantine("schema_validation_error", str(exc), _sample_from(iterator), metadata)
    except _TimestampError as exc:
        metadata = {
            "rows": iterator.metadata.rows if iterator else rows,
            "bytes_read": iterator.metadata.bytes_read if iterator else 0,
            "sample_sha256": iterator.metadata.sample.sha256 if iterator else None,
        }
        return _quarantine("timestamp_error", str(exc), _sample_from(iterator), metadata)
    except Exception as exc:  # pragma: no cover - defensive guardrail
        logger.exception("ingest guard encountered unexpected failure reading %s", path)
        metadata = {
            "rows": iterator.metadata.rows if iterator else rows,
            "bytes_read": iterator.metadata.bytes_read if iterator else 0,
            "sample_sha256": iterator.metadata.sample.sha256 if iterator else None,
        }
        return _quarantine("unexpected_error", str(exc), _sample_from(iterator), metadata)

    assert iterator is not None
    meta = iterator.metadata
    now_ts = now() if now is not None else dt.datetime.now(UTC)
    if now_ts.tzinfo is None:
        now_ts = now_ts.replace(tzinfo=UTC)

    metadata: dict[str, Any] = {
        "rows": meta.rows,
        "bytes_read": meta.bytes_read,
        "sample_sha256": meta.sample.sha256,
        "sample_lines": list(meta.sample.lines),
        "oldest_timestamp": oldest.isoformat() if oldest else None,
        "newest_timestamp": newest.isoformat() if newest else None,
    }

    if newest is not None:
        metadata["age_seconds"] = (now_ts - newest).total_seconds()
    if newest is not None and oldest is not None:
        metadata["span_seconds"] = (newest - oldest).total_seconds()

    if config.stale_after_seconds is not None:
        if newest is None:
            return _quarantine(
                "stale_data",
                "no timestamp data available",
                meta.sample,
                metadata,
            )
        age = (now_ts - newest).total_seconds()
        if age > config.stale_after_seconds:
            detail = (
                f"age={int(age)}s exceeds threshold={int(config.stale_after_seconds)}s"
            )
            return _quarantine("stale_data", detail, meta.sample, metadata)

    telemetry_payload = {
        "path": str(path),
        "rows": meta.rows,
        "bytes_read": meta.bytes_read,
        "newest_timestamp": metadata.get("newest_timestamp"),
        "oldest_timestamp": metadata.get("oldest_timestamp"),
    }
    telemetry_event = _emit_telemetry("ingest_accepted", telemetry_payload)

    return GuardResult(
        path=path,
        status="accepted",
        reason=None,
        rows=meta.rows,
        bytes_read=meta.bytes_read,
        sample=meta.sample,
        metadata=metadata,
        quarantine_path=None,
        telemetry=telemetry_event,
    )


__all__ = ["GuardConfig", "GuardResult", "guard_file"]

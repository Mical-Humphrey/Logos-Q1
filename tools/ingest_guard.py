"""CLI wrapper around :mod:`core.io.ingest_guard`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from core.io.ingest_guard import GuardConfig, guard_file


def _load_schema(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate CSV inputs before ingestion")
    parser.add_argument("paths", nargs="+", help="CSV files to evaluate")
    parser.add_argument("--schema", type=Path, help="Optional JSON schema for rows")
    parser.add_argument(
        "--timestamp-column",
        default="timestamp",
        help="Column containing ISO-8601 timestamps (default: timestamp)",
    )
    parser.add_argument(
        "--stale-seconds",
        type=float,
        default=None,
        help="Quarantine files whose newest timestamp is older than this many seconds",
    )
    parser.add_argument(
        "--telemetry",
        type=Path,
        default=Path("logos/logs/ingest_telemetry.jsonl"),
        help="Telemetry log destination (JSONL)",
    )
    parser.add_argument(
        "--quarantine-root",
        type=Path,
        default=Path("input_data/quarantine"),
        help="Root directory for quarantined files",
    )
    parser.add_argument("--max-rows", type=int, help="Abort if rows exceed this limit")
    parser.add_argument(
        "--max-bytes",
        type=int,
        help="Abort if logical bytes read exceed this limit",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        help="Abort if reading exceeds this many seconds",
    )
    parser.add_argument(
        "--sample-lines",
        type=int,
        default=5,
        help="Number of preview lines recorded in metadata",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    schema = _load_schema(args.schema)
    config = GuardConfig(
        timestamp_column=args.timestamp_column,
        stale_after_seconds=args.stale_seconds,
        max_rows=args.max_rows,
        max_bytes=args.max_bytes,
        max_seconds=args.max_seconds,
        sample_lines=args.sample_lines,
        schema=schema,
    )

    failures = 0
    for raw_path in args.paths:
        path = Path(raw_path)
        try:
            result = guard_file(
                path,
                config=config,
                telemetry_path=args.telemetry,
                quarantine_root=args.quarantine_root,
            )
        except FileNotFoundError as exc:
            print(f"[FAIL] {exc}", file=sys.stderr)
            failures += 1
            continue

        status = "OK" if result.status == "accepted" else "QUARANTINED"
        reason = f" reason={result.reason}" if result.reason else ""
        print(
            f"[{status}] {path}{reason} rows={result.rows} bytes={result.bytes_read}"
        )
        if result.status != "accepted":
            failures += 1

    return 0 if failures == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

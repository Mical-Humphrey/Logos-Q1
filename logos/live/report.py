"""Reporting helpers for live trading sessions."""

from __future__ import annotations

import csv
import datetime as dt
import os
from pathlib import Path
from typing import Dict, Iterable

from core.io.atomic_write import atomic_write_text
from core.io.dirs import ensure_dir

from logos.utils.security import csv_cell_sanitize, redact_text


def _append_row(path: Path, headers: Iterable[str], row: Dict[str, object]) -> None:
    ensure_dir(path.parent)
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(headers), lineterminator="\n")
        if not exists:
            writer.writeheader()
        sanitized = {key: csv_cell_sanitize(row.get(key)) for key in headers}
        writer.writerow(sanitized)
        fh.flush()
        os.fsync(fh.fileno())


def append_trade(path: Path, *, ts: dt.datetime, **fields: object) -> None:
    headers = [
        "ts",
        "session_id",
        "symbol",
        "strategy",
        "id",
        "side",
        "qty",
        "price",
        "fees",
        "slip_bps",
        "order_type",
    ]
    row = {"ts": ts.isoformat(timespec="seconds"), **fields}
    _append_row(path, headers, row)


def append_order(path: Path, *, ts: dt.datetime, **fields: object) -> None:
    headers = [
        "ts",
        "session_id",
        "symbol",
        "strategy",
        "id",
        "side",
        "order_type",
        "qty",
        "limit_price",
        "state",
        "reject_reason",
        "broker_order_id",
    ]
    row = {"ts": ts.isoformat(timespec="seconds"), **fields}
    _append_row(path, headers, row)


def append_position(path: Path, *, ts: dt.datetime, **fields: object) -> None:
    headers = [
        "ts",
        "session_id",
        "symbol",
        "strategy",
        "qty",
        "avg_price",
        "unrealized_pnl",
    ]
    row = {"ts": ts.isoformat(timespec="seconds"), **fields}
    _append_row(path, headers, row)


def append_account(path: Path, *, ts: dt.datetime, **fields: object) -> None:
    headers = [
        "ts",
        "session_id",
        "symbol",
        "strategy",
        "cash",
        "equity",
        "buying_power",
        "currency",
    ]
    row = {"ts": ts.isoformat(timespec="seconds"), **fields}
    _append_row(path, headers, row)


def write_session_summary(path: Path, lines: str) -> None:
    atomic_write_text(path, redact_text(lines.strip() + "\n"), encoding="utf-8")

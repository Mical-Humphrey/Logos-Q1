"""Reporting helpers for live trading sessions."""

from __future__ import annotations

import datetime as dt
import csv
from pathlib import Path
from typing import Dict, Iterable


def _append_row(path: Path, headers: Iterable[str], row: Dict[str, object]) -> None:
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(headers))
        if not exists:
            writer.writeheader()
        writer.writerow(row)


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
    headers = ["ts", "session_id", "symbol", "strategy", "qty", "avg_price", "unrealized_pnl"]
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
    path.write_text(lines.strip() + "\n", encoding="utf-8")

from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

from logos.live import report
from logos.live.state import append_event


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        return list(reader)


def test_append_trade_creates_header_and_row(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "trades.csv"
    ts = dt.datetime(2024, 1, 1, 9, 30, tzinfo=dt.timezone.utc)

    report.append_trade(
        path,
        ts=ts,
        session_id="session",
        symbol="MSFT",
        strategy="mean_reversion",
        id="fill-1",
        side="buy",
        qty=10,
        price=101.5,
        fees=0.25,
        slip_bps=1.2,
        order_type="market",
    )

    rows = _read_rows(path)
    assert len(rows) == 1
    assert rows[0]["id"] == "fill-1"
    assert rows[0]["ts"] == ts.isoformat(timespec="seconds")

    report.append_trade(
        path,
        ts=ts,
        session_id="session",
        symbol="MSFT",
        strategy="mean_reversion",
        id="fill-2",
        side="sell",
        qty=5,
        price=102.0,
        fees=0.0,
        slip_bps=0.0,
        order_type="limit",
    )

    rows = _read_rows(path)
    assert [row["id"] for row in rows] == ["fill-1", "fill-2"]


def test_write_session_summary_trims_and_terminates(tmp_path: Path) -> None:
    summary_path = tmp_path / "session.md"
    report.write_session_summary(summary_path, "hello\n\n")
    assert summary_path.read_text(encoding="utf-8") == "hello\n"


def test_append_event_creates_jsonl(tmp_path: Path) -> None:
    events_path = tmp_path / "logs" / "state.jsonl"
    append_event({"type": "state", "equity": 100.0}, events_path)
    append_event({"type": "heartbeat", "ts": "2024-01-01T00:00:00+00:00"}, events_path)

    lines = events_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["equity"] == 100.0
    assert json.loads(lines[1])["type"] == "heartbeat"

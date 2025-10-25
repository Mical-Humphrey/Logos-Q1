"""Utilities for managing per-session directories and logs."""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from pathlib import Path

from core.io.atomic_write import atomic_write_text
from core.io.dirs import ensure_dir, ensure_dirs

from logos.logging_setup import attach_run_file_handler
from logos.paths import (
    RUNS_LIVE_LATEST_LINK,
    RUNS_LIVE_REPORTS_DIR,
    RUNS_LIVE_SESSIONS_DIR,
    RUNS_LIVE_TRADES_DIR,
    runs_live_latest_symlink,
    safe_slug,
)


@dataclass
class SessionPaths:
    """Bundle of directories/files allocated for a live run."""

    session_id: str
    base_dir: Path
    logs_dir: Path
    state_file: Path
    state_events_file: Path
    trades_file: Path
    orders_file: Path
    positions_file: Path
    account_file: Path
    session_report: Path
    latest_file: Path
    orchestrator_metrics_file: Path
    router_state_file: Path


def _write_header(path: Path, header: str) -> None:
    if path.exists():
        return
    atomic_write_text(path, header + "\n", encoding="utf-8")


def _pointer_contents(session_dir: Path) -> str:
    return str(session_dir.resolve())


def _update_latest_pointer(session_dir: Path) -> None:
    latest = runs_live_latest_symlink()
    ensure_dir(latest.parent)
    atomic_write_text(latest, _pointer_contents(session_dir), encoding="utf-8")


def create_session(
    symbol: str, strategy: str, when: dt.datetime | None = None
) -> tuple[SessionPaths, logging.Handler]:
    """Allocate a new session directory tree and logging handler."""

    when = when or dt.datetime.now(dt.timezone.utc)
    session_id = (
        f"{when.strftime('%Y-%m-%d_%H%M')}_{safe_slug(symbol)}_{safe_slug(strategy)}"
    )
    base_dir = RUNS_LIVE_SESSIONS_DIR / session_id
    logs_dir = base_dir / "logs"
    ensure_dirs(
        [
            (RUNS_LIVE_SESSIONS_DIR, True),
            (logs_dir, True),
            (RUNS_LIVE_TRADES_DIR, True),
            (RUNS_LIVE_REPORTS_DIR, True),
        ]
    )

    state_file = base_dir / "state.json"
    state_events_file = base_dir / "state.jsonl"
    trades_file = base_dir / "trades.csv"
    orders_file = base_dir / "orders.csv"
    positions_file = base_dir / "positions.csv"
    account_file = base_dir / "account.csv"
    session_report = base_dir / "session.md"
    orchestrator_metrics_file = base_dir / "orchestrator_metrics.jsonl"
    router_state_file = base_dir / "router_state.json"
    latest_file = RUNS_LIVE_LATEST_LINK

    _write_header(
        trades_file,
        "# v1 trades\nts,session_id,symbol,strategy,id,side,qty,price,fees,slip_bps,order_type",
    )
    _write_header(
        orders_file,
        "# v1 orders\nts,session_id,symbol,strategy,id,side,order_type,qty,limit_price,state,reject_reason,broker_order_id",
    )
    _write_header(
        positions_file,
        "# v1 positions\nts,session_id,symbol,strategy,qty,avg_price,unrealized_pnl",
    )
    _write_header(
        account_file,
        "# v1 account\nts,session_id,symbol,strategy,cash,equity,buying_power,currency",
    )

    _update_latest_pointer(base_dir)
    handler = attach_run_file_handler(logs_dir / "run.log")

    paths = SessionPaths(
        session_id=session_id,
        base_dir=base_dir,
        logs_dir=logs_dir,
        state_file=state_file,
        state_events_file=state_events_file,
        trades_file=trades_file,
        orders_file=orders_file,
        positions_file=positions_file,
        account_file=account_file,
        session_report=session_report,
        latest_file=latest_file,
        orchestrator_metrics_file=orchestrator_metrics_file,
        router_state_file=router_state_file,
    )
    return paths, handler

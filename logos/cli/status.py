from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from ..config import Settings
from ..paths import RUNS_LIVE_SESSIONS_DIR, RUNS_LIVE_LATEST_LINK

from .common import DEFAULT_ENV_PATH, load_env


@dataclass
class StatusPayload:
    run_id: str
    equity: float
    pnl: float
    positions: Dict[str, Dict[str, float]]
    last_signal: str
    last_updated: datetime
    health: Dict[str, bool]


def register(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    settings: Settings | None = None,
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "status",
        help="Summarise the latest quickstart/live session",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Specific session identifier under runs/live/sessions",
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Explicit session directory",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=RUNS_LIVE_SESSIONS_DIR,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--env-path",
        type=Path,
        default=DEFAULT_ENV_PATH,
        help=argparse.SUPPRESS,
    )
    return parser


def _resolve_run_dir(args: argparse.Namespace) -> Path:
    if args.path is not None:
        return Path(args.path).resolve()
    base = Path(getattr(args, "base_dir", RUNS_LIVE_SESSIONS_DIR)).resolve()
    if args.run_id:
        return (base / args.run_id).resolve()
    latest_link = RUNS_LIVE_LATEST_LINK
    if latest_link.exists() or latest_link.is_symlink():
        try:
            target = latest_link.resolve(strict=True)
            if target.exists():
                return target
        except FileNotFoundError:
            pass
    # fallback to newest directory
    candidates = [p for p in base.iterdir() if p.is_dir()]
    if not candidates:
        raise SystemExit(f"No sessions found under {base}")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _load_snapshot(run_dir: Path) -> Dict[str, object]:
    snapshot_path = run_dir / "snapshot.json"
    if not snapshot_path.exists():
        raise SystemExit(f"snapshot.json missing in {run_dir}")
    return json.loads(snapshot_path.read_text(encoding="utf-8"))


def _load_metrics(run_dir: Path) -> Dict[str, object]:
    metrics_path = run_dir / "artifacts" / "metrics.json"
    if not metrics_path.exists():
        raise SystemExit(f"metrics.json missing in {metrics_path.parent}")
    return json.loads(metrics_path.read_text(encoding="utf-8"))


def _infer_signal(snapshot: Dict[str, object]) -> str:
    fills = snapshot.get("fills") or []
    if fills:
        last = fills[-1]
        side = str(last.get("side", "")).lower()
        if side == "buy":
            return "long"
        if side == "sell":
            return "short"
    positions = snapshot.get("positions") or {}
    if isinstance(positions, dict):
        for data in positions.values():
            qty = float(data.get("quantity", 0.0))
            if qty > 0:
                return "long"
            if qty < 0:
                return "short"
    return "flat"


def _health(snapshot: Dict[str, object], env_values: Dict[str, str]) -> Dict[str, bool]:
    last_fill = snapshot.get("fills") or []
    ref_ts = datetime.utcnow().replace(tzinfo=timezone.utc)
    if last_fill:
        ts = last_fill[-1].get("ts")
        try:
            last_ts = datetime.fromisoformat(str(ts))
        except Exception:
            last_ts = ref_ts
    else:
        clock = snapshot.get("clock")
        try:
            last_ts = datetime.fromisoformat(str(clock))
        except Exception:
            last_ts = ref_ts
    if last_ts.tzinfo is None:
        last_ts = last_ts.replace(tzinfo=timezone.utc)
    else:
        last_ts = last_ts.astimezone(timezone.utc)
    age = (ref_ts - last_ts).total_seconds()
    offline = env_values.get("LOGOS_OFFLINE_ONLY", "0").strip().lower() in {"1", "true", "yes", "on"}
    return {
        "offline_only": offline,
        "stale": age > 3600,
        "open_positions": bool(snapshot.get("positions")),
    }


def _build_status(run_dir: Path, env_values: Dict[str, str]) -> StatusPayload:
    snapshot = _load_snapshot(run_dir)
    metrics = _load_metrics(run_dir)
    account = snapshot.get("account") or {}
    equity = float(account.get("equity", 0.0))
    realized = float(account.get("realized_pnl", 0.0))
    unrealized = float(account.get("unrealized_pnl", 0.0))
    pnl = realized + unrealized
    positions = snapshot.get("positions") or {}
    if not isinstance(positions, dict):
        positions = {}
    last_signal = _infer_signal(snapshot)
    clock = snapshot.get("clock")
    try:
        last_updated = datetime.fromisoformat(str(clock)) if clock else None
    except Exception:
        last_updated = None
    if last_updated is None:
        last_updated = datetime.utcnow().replace(tzinfo=timezone.utc)
    elif last_updated.tzinfo is None:
        last_updated = last_updated.replace(tzinfo=timezone.utc)
    else:
        last_updated = last_updated.astimezone(timezone.utc)
    health = _health(snapshot, env_values)
    run_id = str(snapshot.get("run_id") or run_dir.name)
    return StatusPayload(
        run_id=run_id,
        equity=equity,
        pnl=pnl,
        positions={key: dict(value) for key, value in positions.items()},
        last_signal=last_signal,
        last_updated=last_updated,
        health=health,
    )


def _print_status(run_dir: Path, payload: StatusPayload, metrics: Dict[str, object]) -> None:
    print(f"Run: {payload.run_id}")
    print(f"Location: {run_dir}")
    print(f"Last Updated: {payload.last_updated.isoformat()}")
    print(f"Equity: ${payload.equity:,.2f}")
    print(f"PnL: ${payload.pnl:,.2f}")
    sharpe = metrics.get("Sharpe") or metrics.get("sharpe")
    if isinstance(sharpe, (int, float)):
        print(f"Sharpe: {sharpe:.2f}")
    print(f"Last Signal: {payload.last_signal}")
    if payload.positions:
        print("Positions:")
        for symbol, info in payload.positions.items():
            qty = float(info.get("quantity", 0.0))
            avg = float(info.get("average_price", 0.0))
            print(f"  - {symbol}: qty={qty:.6f} avg=${avg:.2f}")
    else:
        print("Positions: None")
    flags = ", ".join(f"{key}={'yes' if value else 'no'}" for key, value in payload.health.items())
    print(f"Health: {flags}")


def run(args: argparse.Namespace, *, settings: Settings | None = None) -> int:
    env_values = load_env(getattr(args, "env_path", DEFAULT_ENV_PATH))
    run_dir = _resolve_run_dir(args)
    payload = _build_status(run_dir, env_values)
    metrics = _load_metrics(run_dir)
    _print_status(run_dir, payload, metrics)
    return 0

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from ..config import Settings
from ..paths import PROJECT_ROOT, RUNS_DIR, LOGOS_DIR

from .common import DEFAULT_ENV_PATH, load_env


@dataclass
class CheckResult:
    name: str
    ok: bool
    details: str


def register(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    settings: Settings | None = None,
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "doctor",
        help="Run environment diagnostics",
    )
    parser.add_argument(
        "--env-path",
        type=Path,
        default=DEFAULT_ENV_PATH,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=RUNS_DIR,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--logs-dir",
        type=Path,
        default=LOGOS_DIR,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Check that offline safeguards are enabled",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser


def _python_version() -> CheckResult:
    version = sys.version_info
    ok = version >= (3, 10)
    return CheckResult(
        name="python-version",
        ok=ok,
        details=f"Python {version.major}.{version.minor}.{version.micro}",
    )


def _write_permission(path: Path) -> CheckResult:
    path = path.resolve()
    ok = os.access(path, os.W_OK | os.X_OK)
    return CheckResult(
        name=f"write-perms:{path.name}",
        ok=ok,
        details="OK" if ok else f"Missing write permissions for {path}",
    )


def _disk_check(path: Path) -> CheckResult:
    usage = shutil.disk_usage(path)
    free_ratio = usage.free / max(usage.total, 1)
    threshold = 0.05
    ok = free_ratio >= threshold
    percent = free_ratio * 100
    return CheckResult(
        name="disk-space",
        ok=ok,
        details=f"{percent:.1f}% free on {path}",
    )


def _clock_check() -> CheckResult:
    wall = datetime.utcnow().replace(tzinfo=timezone.utc)
    sys_now = datetime.now(timezone.utc)
    delta = abs((wall - sys_now).total_seconds())
    ok = delta < 5
    return CheckResult(
        name="clock-sync",
        ok=ok,
        details=f"Difference {delta:.2f}s",
    )


def _sqlite_wal(runs_dir: Path) -> CheckResult:
    temp_db = runs_dir / "doctor_temp.sqlite"
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute("PRAGMA journal_mode=WAL;")
        mode = str(cursor.fetchone()[0]).lower()
        ok = mode == "wal"
    except Exception as exc:
        return CheckResult("sqlite-wal", False, f"Failed enabling WAL: {exc}")
    finally:
        if conn is not None:
            conn.close()
        if temp_db.exists():
            try:
                temp_db.unlink()
            except OSError:
                pass
    return CheckResult("sqlite-wal", ok, "WAL available" if ok else "WAL not supported")


def _retention_policy(env_values: dict[str, str]) -> CheckResult:
    flag = env_values.get("LOGOS_RETENTION_ENABLED", "0").strip().lower()
    if flag in {"0", "false", "no", ""}:
        return CheckResult("retention", True, "Retention disabled (default)")
    max_days = env_values.get("LOGOS_RETENTION_MAX_DAYS", "").strip()
    ok = max_days.isdigit() and int(max_days) > 0
    details = (
        f"Retention enabled with max days={max_days}"
        if ok
        else "Retention enabled without LOGOS_RETENTION_MAX_DAYS"
    )
    return CheckResult("retention", ok, details)


def _offline_guard(off: bool, env_values: dict[str, str]) -> CheckResult:
    if not off:
        return CheckResult("offline-flag", True, "Offline check skipped")
    token = env_values.get("LOGOS_OFFLINE_ONLY", "").strip().lower()
    ok = token in {"1", "true", "yes", "on"}
    details = "LOGOS_OFFLINE_ONLY=1" if ok else "Set LOGOS_OFFLINE_ONLY=1 in .env"
    return CheckResult("offline-flag", ok, details)


def run(args: argparse.Namespace, *, settings: Settings | None = None) -> int:
    env_values = load_env(getattr(args, "env_path", DEFAULT_ENV_PATH))
    runs_dir = Path(getattr(args, "runs_dir", RUNS_DIR)).resolve()
    logs_dir = Path(getattr(args, "logs_dir", LOGOS_DIR)).resolve()

    checks: List[CheckResult] = []
    checks.append(_python_version())
    checks.append(_write_permission(runs_dir))
    checks.append(_write_permission(logs_dir))
    checks.append(_disk_check(PROJECT_ROOT))
    checks.append(_clock_check())
    checks.append(_sqlite_wal(runs_dir))
    checks.append(_retention_policy(env_values))
    checks.append(_offline_guard(getattr(args, "offline", False), env_values))

    failed = [c for c in checks if not c.ok]

    if getattr(args, "json", False):
        import json

        payload = [c.__dict__ for c in checks]
        print(json.dumps(payload, indent=2))
    else:
        for check in checks:
            status = "PASS" if check.ok else "FAIL"
            print(f"[{status}] {check.name}: {check.details}")

    if failed:
        print(f"\n{len(failed)} check(s) failed. Review the messages above.")
        return 1
    print("\nAll doctor checks passed.")
    return 0

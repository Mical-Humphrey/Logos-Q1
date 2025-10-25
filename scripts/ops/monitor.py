from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict, List

DEFAULT_ALERT_TEMPLATE = "[{channel}] {message}"


def _load_state(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def _save_state(path: Path, data: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _send_alert(message: str) -> None:
    webhook = os.getenv("LOGOS_ALERT_WEBHOOK")
    if not webhook:
        print(f"alert (dry-run): {message}")
        return
    channel = os.getenv("LOGOS_ALERT_CHANNEL", "logos-ops")
    payload = {"text": DEFAULT_ALERT_TEMPLATE.format(channel=channel, message=message)}
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        webhook,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10):
        pass


def _check_sentinel(now: float) -> List[str]:
    issues: List[str] = []
    sentinel_path = Path(os.getenv("LOGOS_SENTINEL_FILE", "/app/logs/live/heartbeat.json"))
    stale_seconds = float(os.getenv("LOGOS_SENTINEL_STALE_SECONDS", "900"))
    if not sentinel_path.exists():
        issues.append(f"sentinel file missing at {sentinel_path}")
        return issues
    age = now - sentinel_path.stat().st_mtime
    if age > stale_seconds:
        issues.append(
            f"sentinel {sentinel_path} stale ({int(age)}s) exceeds {int(stale_seconds)}s"
        )
    return issues


def _check_disk() -> List[str]:
    issues: List[str] = []
    target = Path(os.getenv("LOGOS_DISK_PATH", "/app"))
    threshold = float(os.getenv("LOGOS_DISK_THRESHOLD", "90"))
    usage = shutil.disk_usage(target)
    percent = (usage.used / usage.total) * 100
    if percent >= threshold:
        issues.append(f"disk usage {percent:.1f}% on {target} exceeds {threshold}%")
    return issues


def _check_errors(state: Dict[str, object]) -> List[str]:
    issues: List[str] = []
    log_path = Path(os.getenv("LOGOS_ERROR_LOG", "/app/logs/run.log"))
    if not log_path.exists():
        return issues
    last_size = int(state.get("error_log_size", 0))
    current_size = log_path.stat().st_size
    if current_size <= last_size:
        state["error_log_size"] = current_size
        return issues
    with log_path.open("r", encoding="utf-8", errors="ignore") as handle:
        handle.seek(last_size)
        window = handle.read()
    state["error_log_size"] = current_size
    if "ERROR" in window or "Traceback" in window:
        issues.append(f"errors detected in {log_path} (size {current_size})")
    return issues


def _run_checks(state_path: Path) -> None:
    now = time.time()
    state = _load_state(state_path)
    issues: List[str] = []
    issues.extend(_check_sentinel(now))
    issues.extend(_check_disk())
    issues.extend(_check_errors(state))
    _save_state(state_path, state)
    for issue in issues:
        _send_alert(issue)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Logos deployment monitor")
    parser.add_argument("--loop", action="store_true", help="Run continuously")
    parser.add_argument("--interval", type=int, default=300, help="Sleep seconds when looping")
    args = parser.parse_args(argv)
    state_path = Path(os.getenv("LOGOS_MONITOR_STATE", "/app/logs/monitor_state.json"))
    if not args.loop:
        _run_checks(state_path)
        return 0
    while True:
        try:
            _run_checks(state_path)
        except Exception as exc:  # noqa: BLE001
            print(f"monitor failure: {exc}", file=sys.stderr)
        time.sleep(args.interval)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

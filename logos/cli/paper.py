from __future__ import annotations

import argparse
import json
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

from ..config import Settings
from ..paths import RUNS_PAPER_LATEST_LINK, RUNS_PAPER_SESSIONS_DIR
from ..live.session_manager import create_session
from core.io.atomic_write import atomic_write_text
from core.io.dirs import ensure_dir


DEFAULT_SYMBOL = "DEMO"
DEFAULT_STRATEGY = "paper"


def register(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    settings: Settings | None = None,
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "paper",
        help="Run a long-running paper session that emits periodic metrics",
    )
    parser.add_argument(
        "--symbol",
        default=DEFAULT_SYMBOL,
        help="Symbol label used for session naming only (default: DEMO)",
    )
    parser.add_argument(
        "--strategy",
        default=DEFAULT_STRATEGY,
        help="Strategy label used for session naming only (default: paper)",
    )
    parser.add_argument(
        "--duration-sec",
        type=int,
        default=300,
        help="Total duration to run (seconds)",
    )
    parser.add_argument(
        "--heartbeat-sec",
        type=int,
        default=60,
        help="Heartbeat interval for metrics.json updates (seconds)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="No-op flag for parity with other commands; session runs offline",
    )
    return parser


_TERMINATE = False


def _install_signal_handlers() -> None:
    def handler(signum, frame):  # noqa: ARG001 - signature required by signal
        global _TERMINATE
        _TERMINATE = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, handler)
        except Exception:
            pass


def _write_json(path: Path, payload: dict) -> None:
    ensure_dir(path.parent)
    atomic_write_text(path, json.dumps(payload, indent=2), encoding="utf-8")


def run(args: argparse.Namespace, *, settings: Settings | None = None) -> int:
    symbol = str(getattr(args, "symbol", DEFAULT_SYMBOL))
    strategy = str(getattr(args, "strategy", DEFAULT_STRATEGY))
    duration = max(int(getattr(args, "duration_sec", 300)), 1)
    heartbeat = max(int(getattr(args, "heartbeat_sec", 60)), 1)

    paths, log_handler = create_session(
        symbol,
        strategy,
        sessions_dir=RUNS_PAPER_SESSIONS_DIR,
        latest_link=RUNS_PAPER_LATEST_LINK,
    )
    try:
        artifacts = paths.base_dir / "artifacts"
        ensure_dir(artifacts)
        metrics_path = artifacts / "metrics.json"

        started = datetime.now(timezone.utc)
        pid = os.getpid()
        _install_signal_handlers()

        # Initial write
        _write_json(
            metrics_path,
            {
                "ts": started.isoformat(),
                "pid": pid,
                "symbol": symbol,
                "strategy": strategy,
                "uptime_sec": 0,
                "note": "paper heartbeat session started",
            },
        )

        # Emit a JSONL heartbeat to orchestrator_metrics as well
        try:
            with paths.orchestrator_metrics_file.open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(
                        {"ts": started.isoformat(), "event": "start", "pid": pid}
                    )
                    + "\n"
                )
        except Exception:
            pass

        deadline = time.time() + duration
        next_beat = time.time() + heartbeat
        while time.time() < deadline and not _TERMINATE:
            time.sleep(0.25)
            now = time.time()
            if now >= next_beat:
                uptime = int(now - started.timestamp())
                payload = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "pid": pid,
                    "symbol": symbol,
                    "strategy": strategy,
                    "uptime_sec": uptime,
                }
                _write_json(metrics_path, payload)
                try:
                    with paths.orchestrator_metrics_file.open(
                        "a", encoding="utf-8"
                    ) as fh:
                        fh.write(
                            json.dumps(
                                {
                                    "ts": payload["ts"],
                                    "event": "heartbeat",
                                    "uptime_sec": uptime,
                                }
                            )
                            + "\n"
                        )
                except Exception:
                    pass
                next_beat = now + heartbeat

        # Finalize
        ended = datetime.now(timezone.utc)
        final_payload = {
            "ts": ended.isoformat(),
            "pid": pid,
            "symbol": symbol,
            "strategy": strategy,
            "uptime_sec": int(ended.timestamp() - started.timestamp()),
            "ended": True,
        }
        _write_json(metrics_path, final_payload)
        try:
            with paths.orchestrator_metrics_file.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": final_payload["ts"], "event": "end"}) + "\n")
        except Exception:
            pass

        print("Paper session complete.\n")
        print(f"Session Dir : {paths.base_dir}")
        print(f"Metrics     : {metrics_path}")
        print(f"Run Log     : {paths.logs_dir / 'run.log'}")
        return 0
    finally:
        try:
            import logging

            root = logging.getLogger()
            if log_handler in root.handlers:
                root.removeHandler(log_handler)
        except Exception:
            pass

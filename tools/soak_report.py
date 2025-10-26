#!/usr/bin/env python3
"""
Daily soak report generator.

Invoked by scripts/test_2_week.sh at end-of-day to produce a markdown report
and a small JSON summary. It is tolerant of missing metrics and focuses on
creating a useful human-readable summary from available artifacts.

Usage:
  python tools/soak_report.py \
    --runs-dir runs \
    --day YYYY-MM-DD \
    --orchestrator-log runs/soak/logs/YYYY-MM-DD.log \
    --restarts-log runs/soak/YYYY-MM-DD/restarts.log \
    --out-dir runs/soak/reports/YYYY-MM-DD
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate daily soak report")
    p.add_argument("--runs-dir", required=True)
    p.add_argument("--day", required=True, help="ISO date YYYY-MM-DD (UTC)")
    p.add_argument("--orchestrator-log", default="", help="Path to harness log")
    p.add_argument("--restarts-log", default="", help="Path to child restarts log")
    p.add_argument("--out-dir", required=True, help="Output directory for the report")
    return p.parse_args()


def _same_utc_day(path: Path, day_iso: str) -> bool:
    try:
        mtime = datetime.utcfromtimestamp(path.stat().st_mtime).date().isoformat()
        return mtime == day_iso
    except Exception:
        return False


def _collect_metrics_files(runs_dir: Path, day_iso: str) -> List[Path]:
    results: List[Path] = []
    for p in runs_dir.rglob("artifacts/metrics.json"):
        if _same_utc_day(p, day_iso):
            results.append(p)
    return sorted(results)


def _read_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _tail_lines(path: Path, n: int = 200) -> List[str]:
    if not path.exists():
        return []
    # Efficient tail reader without loading whole file
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            block = 2048
            data = b""
            while size > 0 and data.count(b"\n") <= n:
                step = min(block, size)
                fh.seek(size - step)
                data = fh.read(step) + data
                size -= step
            text = data.decode("utf-8", errors="replace")
            lines = text.splitlines()
            return lines[-n:]
    except Exception:
        return []


def _write_lines(path: Path, lines: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for line in lines:
            if not line.endswith("\n"):
                line += "\n"
            fh.write(line)


def _render_metrics_summary(metrics_files: List[Path], base: Path) -> tuple[str, dict]:
    if not metrics_files:
        return "No metrics.json artifacts were found for this day.", {}

    summary: dict[str, dict] = {}
    for mf in metrics_files:
        payload = _read_json(mf)
        label = str(mf.resolve())
        try:
            label = str(mf.resolve().relative_to(base))
        except Exception:
            pass
        if isinstance(payload, dict):
            show: dict = {}
            # Keep a few common keys if present
            for k in ("ts", "uptime_sec", "trades", "pnl", "ended", "equity", "cash"):
                if k in payload:
                    show[k] = payload[k]
            # Fallback: small subset of arbitrary keys
            if not show:
                for k in list(payload.keys())[:6]:
                    show[k] = payload.get(k)
            summary[label] = show
        else:
            summary[label] = {"_raw": payload}

    text = json.dumps(summary, indent=2)
    block = "```\n" + text + "\n```"
    return block, summary


def generate_report(
    runs_dir: Path,
    day_iso: str,
    orchestrator_log: Path | None,
    restarts_log: Path | None,
    out_dir: Path,
) -> Path | None:
    metrics_files = _collect_metrics_files(runs_dir, day_iso)
    metrics_block, summary = _render_metrics_summary(metrics_files, runs_dir)

    md: list[str] = []
    md.append(f"# Soak Report — {day_iso}")
    md.append("")
    md.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    md.append(f"Artifacts found: {len(metrics_files)} metrics.json file(s)")
    md.append("")

    md.append("## Metrics summary")
    md.append(metrics_block)
    md.append("")

    md.append("## Orchestrator log (tail)")
    if orchestrator_log and orchestrator_log.exists():
        tail = _tail_lines(orchestrator_log, n=200)
        if tail:
            md.append("```")
            md.extend(tail)
            md.append("```")
        else:
            md.append("_No lines available_")
    else:
        md.append("_Not provided_")
    md.append("")

    if restarts_log and restarts_log.exists():
        md.append("## Restarts")
        try:
            content = restarts_log.read_text(encoding="utf-8").strip()
        except Exception:
            content = ""
        if content:
            md.append("```")
            md.append(content)
            md.append("```")
        else:
            md.append("_None_")

    # Write outputs
    out_dir.mkdir(parents=True, exist_ok=True)
    report_md = out_dir / "report.md"
    report_json = out_dir / "report.json"
    _write_lines(report_md, md)
    try:
        report_json.write_text(
            json.dumps(
                {
                    "day": day_iso,
                    "metrics_files": [str(p) for p in metrics_files],
                    "summary": summary,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        # Non-fatal if JSON fails
        pass
    return report_md


def main() -> int:
    args = _parse_args()
    try:
        runs_dir = Path(args.runs_dir)
        out_dir = Path(args.out_dir)
        day = str(args.day)
        orch = Path(args.orchestrator_log) if args.orchestrator_log else None
        restarts = Path(args.restarts_log) if args.restarts_log else None

        rep = generate_report(runs_dir, day, orch, restarts, out_dir)
        if rep and rep.exists():
            print(f"Report written: {rep}", file=sys.stderr)
            return 0
        print("Report generation did not produce a file", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"soak_report.py: unexpected error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

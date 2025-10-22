"""Retention janitor for runs/, logs/, data/cache/, and quarantine trees."""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

logger = logging.getLogger(__name__)


@dataclass
class Entry:
    path: Path
    size: int
    mtime: float


def _gather_entries(paths: Iterable[Path]) -> List[Entry]:
    entries: List[Entry] = []
    for base in paths:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.is_file():
                try:
                    st = p.stat()
                except Exception:
                    continue
                entries.append(Entry(path=p, size=st.st_size, mtime=st.st_mtime))
    return entries


def _plan_purge(
    entries: List[Entry],
    *,
    max_bytes: int | None = None,
    max_days: int | None = None,
    max_count: int | None = None,
) -> List[Path]:
    entries = sorted(entries, key=lambda e: e.mtime)
    now = time.time()
    marked: List[Entry] = []
    remaining = entries

    if max_days is not None:
        cutoff = now - max_days * 24 * 3600
        older = [e for e in remaining if e.mtime < cutoff]
        marked.extend(older)
        remaining = [e for e in remaining if e.mtime >= cutoff]

    if max_count is not None and len(remaining) > max_count:
        overflow = len(remaining) - max_count
        marked.extend(remaining[:overflow])
        remaining = remaining[overflow:]

    if max_bytes is not None:
        total_bytes = sum(e.size for e in remaining)
        idx = 0
        while total_bytes > max_bytes and idx < len(remaining):
            marked.append(remaining[idx])
            total_bytes -= remaining[idx].size
            idx += 1

    # Deduplicate while preserving order
    seen: set[Path] = set()
    plan: List[Path] = []
    for entry in marked:
        if entry.path not in seen:
            seen.add(entry.path)
            plan.append(entry.path)
    return plan


def plan_and_execute(
    target_paths: Iterable[Path],
    quotas: Dict[str, int],
    *,
    enable: bool = False,
    dry_run: bool = True,
) -> Dict[str, List[str]]:
    entries = _gather_entries(target_paths)
    plan = [] if not quotas else _plan_purge(
        entries,
        max_bytes=quotas.get("max_bytes"),
        max_days=quotas.get("max_days"),
        max_count=quotas.get("max_count"),
    )

    decisions = [{"path": str(p), "action": "delete"} for p in plan]
    logger.info(
        "retention_plan",
        extra={
            "event": "retention_plan",
            "paths": [str(p) for p in target_paths],
            "quotas": quotas,
            "planned": decisions,
            "dry_run": dry_run,
            "enable": enable,
        },
    )

    result: Dict[str, List[str]] = {"plan": [d["path"] for d in decisions], "deleted": []}
    can_delete = enable and not dry_run and bool(quotas)
    if not can_delete:
        if enable and not quotas:
            logger.warning("retention_enable_without_quotas", extra={"event": "retention_noop", "reason": "missing_quotas"})
        return result

    for path in plan:
        try:
            os.remove(path)
            result["deleted"].append(str(path))
            logger.info(
                "retention_delete",
                extra={"event": "retention_delete", "path": str(path)},
            )
        except Exception as exc:  # pragma: no cover - best effort cleanup
            logger.exception("failed to delete path=%s err=%s", path, exc)
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", nargs="+", help="Paths to scan", required=True)
    ap.add_argument("--max-bytes", type=int, help="Max retained bytes")
    ap.add_argument("--max-days", type=int, help="Purge files older than N days")
    ap.add_argument("--max-count", type=int, help="Max retained files count")
    ap.add_argument("--enable", action="store_true", help="Enable deletion (requires quotas)")
    ap.add_argument("--no-dry-run", dest="dry_run", action="store_false")
    args = ap.parse_args()
    quotas = {k: v for k, v in [("max_bytes", args.max_bytes), ("max_days", args.max_days), ("max_count", args.max_count)] if v is not None}
    paths = [Path(p) for p in args.paths]
    res = plan_and_execute(paths, quotas, enable=args.enable, dry_run=args.dry_run)
    print(json.dumps(res, indent=2))

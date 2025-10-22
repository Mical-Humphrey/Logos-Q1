"""Quarantine utilities for isolating malformed input files safely."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import List

from core.io.atomic_write import atomic_write, atomic_write_text
from core.io.dirs import ensure_dir

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _read_sample(src: Path, limit: int) -> list[str]:
    lines: list[str] = []
    with src.open("r", encoding="utf-8", errors="replace") as fh:
        for _ in range(limit):
            line = fh.readline()
            if not line:
                break
            lines.append(line.rstrip("\n"))
    return lines


def _copy_with_hash(src: Path, dest: Path) -> str:
    hasher = hashlib.sha256()

    def _writer(fh) -> None:
        with src.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 128), b""):
                hasher.update(chunk)
                fh.write(chunk)

    atomic_write(dest, _writer, mode="wb")
    return hasher.hexdigest()


def move_to_quarantine(
    src: Path,
    *,
    quarantine_root: Path | None = None,
    reason: str = "malformed_input",
    detected_at: str | None = None,
    sample_lines: List[str] | None = None,
    sample_limit: int = 10,
) -> Path:
    """Copy *src* into the quarantine tree and write metadata alongside it."""

    src = src.resolve()
    if quarantine_root is None:
        quarantine_root = Path("input_data") / "quarantine"
    date_dir = quarantine_root / dt.date.today().strftime("%Y%m%d")
    ensure_dir(date_dir)

    dest = date_dir / src.name
    sample = sample_lines or _read_sample(src, sample_limit)
    sha = _copy_with_hash(src, dest)

    meta = {
        "reason": reason,
        "detected_at": detected_at or _now_iso(),
        "source_path": str(src),
        "sample_lines": sample,
        "sha256": sha,
    }
    meta_path = dest.with_name(f"{dest.name}.quarantine.json")
    atomic_write_text(meta_path, json.dumps(meta, indent=2), encoding="utf-8")

    try:
        os.remove(src)
    except FileNotFoundError:
        pass
    except Exception as exc:  # pragma: no cover - best effort cleanup
        logger.warning("failed to remove quarantined source path=%s err=%s", src, exc)

    logger.info(
        "quarantine_move",
        extra={
            "event": "quarantine_move",
            "source_path": str(src),
            "dest_path": str(dest),
            "reason": reason,
            "sha256": sha,
        },
    )
    return dest


__all__ = ["move_to_quarantine"]

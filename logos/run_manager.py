from __future__ import annotations

import csv
import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union

import pandas as pd
from pandas import DataFrame
import yaml

from core.io.dirs import ensure_dir, ensure_dirs

from .paths import (
    RUNS_DIR,
    RUNS_LESSONS_DIR,
    RUNS_LATEST_LINK,
    safe_slug,
)
from .logging_setup import attach_run_file_handler, detach_handler
from .window import Window
from .utils.atomic import atomic_write, atomic_write_text

# Timestamp format: 2025-10-19_1702
TS_FMT = "%Y-%m-%d_%H%M%S"
REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class RunContext:
    run_id: str
    run_dir: Path
    logs_dir: Path
    config_file: Path
    metrics_file: Path
    trades_file: Path
    equity_png: Path
    run_log_file: Path
    log_handler: logging.Handler


def resolve_git_sha() -> str | None:
    """Return the current repository HEAD SHA if available."""
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT
        ).decode("utf-8")
    except Exception:
        return None
    return sha.strip()


def _compose_run_id(symbol: str, strategy: str, when: Optional[datetime] = None) -> str:
    ts = (when or datetime.now(timezone.utc)).strftime(TS_FMT)
    sym = safe_slug(symbol)
    strat = safe_slug(strategy.lower())
    return f"{ts}_{sym}_{strat}"


def _safe_symlink(src: Path, dst: Path) -> None:
    """
    Create/replace a symlink dst -> src. On platforms that do not allow symlinks,
    replace with a small text pointer file.
    """
    if dst.exists() or dst.is_symlink():
        try:
            if dst.is_dir() and not dst.is_symlink():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        except Exception:
            pass
    try:
        dst.symlink_to(src, target_is_directory=True)
    except Exception:
        dst.write_text(str(src), encoding="utf-8")


def new_run(
    symbol: str,
    strategy: str,
    base_dir: Path = RUNS_DIR,
    when: Optional[datetime] = None,
    set_latest: bool = True,
    logger: Optional[logging.Logger] = None,
) -> RunContext:
    """
    Create an isolated run directory with standardized artifacts and a per-run logger attached.
    """
    ensure_dir(base_dir)

    run_id = _compose_run_id(symbol, strategy, when=when)
    run_dir = base_dir / run_id
    logs_dir = run_dir / "logs"
    ensure_dir(logs_dir)

    config_file = run_dir / "config.yaml"
    metrics_file = run_dir / "metrics.json"
    trades_file = run_dir / "trades.csv"
    equity_png = run_dir / "equity.png"
    run_log_file = logs_dir / "run.log"

    # Attach per-run log handler
    handler = attach_run_file_handler(
        run_log_file, level=logger.level if logger else None
    )

    if set_latest and base_dir == RUNS_DIR:
        _safe_symlink(run_dir, RUNS_LATEST_LINK)

    return RunContext(
        run_id=run_id,
        run_dir=run_dir,
        logs_dir=logs_dir,
        config_file=config_file,
        metrics_file=metrics_file,
        trades_file=trades_file,
        equity_png=equity_png,
        run_log_file=run_log_file,
        log_handler=handler,
    )


def write_config(
    ctx: RunContext, config: Dict[str, Any], env: Optional[Dict[str, Any]] = None
) -> None:
    """
    Persist the effective configuration, including selected environment values.
    """
    payload = {"config": config}
    if env:
        payload["env"] = env
    atomic_write_text(
        ctx.config_file,
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


def write_metrics(
    ctx: RunContext, metrics: Dict[str, Any], provenance: Dict[str, Any] | None = None
) -> None:
    serializable = {
        key: (float(value) if hasattr(value, "__float__") else value)
        for key, value in metrics.items()
    }
    if provenance:
        serializable["provenance"] = provenance
    atomic_write_text(
        ctx.metrics_file, json.dumps(serializable, indent=2), encoding="utf-8"
    )


def write_trades(ctx: RunContext, trades: Union[DataFrame, list, tuple]) -> None:
    if isinstance(trades, pd.DataFrame):

        def _write_frame(fh: Any) -> None:
            trades.to_csv(fh, index=False)

        atomic_write(ctx.trades_file, _write_frame, newline="")
        return

    rows = trades if isinstance(trades, (list, tuple)) else []

    def _write_rows(fh: Any) -> None:
        if rows and isinstance(rows[0], dict):
            fieldnames = list(rows[0].keys())
            dict_writer = csv.DictWriter(fh, fieldnames=fieldnames)
            dict_writer.writeheader()
            dict_writer.writerows(rows)  # type: ignore[arg-type]
        else:
            row_writer = csv.writer(fh)
            row_writer.writerows(rows)  # type: ignore[arg-type]

    atomic_write(ctx.trades_file, _write_rows, newline="")


def write_provenance(
    ctx: RunContext,
    payload: Dict[str, Any],
    *,
    window: Window | None = None,
) -> Path:
    """Persist provenance metadata alongside run artifacts."""
    serializable = dict(payload)
    if window is not None:
        existing = serializable.get("window")
        extras: Dict[str, Any] = {}
        if isinstance(existing, dict):
            extras = {
                key: value
                for key, value in existing.items()
                if key not in {"start_iso", "end_iso", "tz"}
            }
        serializable["window"] = {**extras, **window.to_dict()}
    else:
        maybe_window = serializable.get("window")
        if isinstance(maybe_window, Window):
            serializable["window"] = maybe_window.to_dict()
        elif isinstance(maybe_window, dict):
            serializable["window"] = {
                **{
                    key: value
                    for key, value in maybe_window.items()
                    if key
                    not in {"start_iso", "end_iso", "tz", "start", "end", "timezone"}
                },
                "start_iso": maybe_window.get("start_iso")
                or maybe_window.get("start")
                or "",
                "end_iso": maybe_window.get("end_iso") or maybe_window.get("end") or "",
                "tz": maybe_window.get("tz") or maybe_window.get("timezone") or "UTC",
            }
    path = ctx.run_dir / "provenance.json"
    atomic_write_text(path, json.dumps(serializable, indent=2), encoding="utf-8")
    return path


def write_session_markdown(ctx: RunContext, lines: list[str]) -> Path:
    """Write a concise markdown summary for the run."""
    path = ctx.run_dir / "session.md"
    content = "\n".join(lines).rstrip() + "\n"
    atomic_write_text(path, content, encoding="utf-8")
    return path


def save_equity_plot(ctx: RunContext, fig: Any) -> Path:
    """Persist an equity figure to disk and return the saved path."""
    logger = logging.getLogger(__name__)
    try:
        fig.savefig(ctx.equity_png, dpi=144, bbox_inches="tight")
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Failed to save equity plot: %s", exc)
    return ctx.equity_png


def capture_env(keys: list[str]) -> Dict[str, str]:
    """
    Helper to capture specific env keys into config.yaml for reproducibility.
    """
    return {k: os.getenv(k, "") for k in keys}


def close_run_context(ctx: RunContext) -> None:
    try:
        detach_handler(ctx.log_handler)
    except ValueError:  # pragma: no cover - defensive
        pass


# Lesson runs -----------------------------------------------------------------


@dataclass
class LessonPaths:
    lesson: str
    timestamp: str
    lesson_dir: Path
    run_dir: Path
    plots_dir: Path
    logs_dir: Path
    log_file: Path


def prepare_lesson_paths(lesson: str, when: Optional[datetime] = None) -> LessonPaths:
    ensure_dir(RUNS_LESSONS_DIR)
    ts = (when or datetime.now(timezone.utc)).strftime(TS_FMT)
    lesson_dir = RUNS_LESSONS_DIR / lesson
    run_dir = lesson_dir / ts
    plots_dir = run_dir / "plots"
    logs_dir = run_dir / "logs"
    ensure_dirs([lesson_dir, run_dir, plots_dir, logs_dir])
    log_file = logs_dir / "run.log"
    return LessonPaths(
        lesson=lesson,
        timestamp=ts,
        lesson_dir=lesson_dir,
        run_dir=run_dir,
        plots_dir=plots_dir,
        logs_dir=logs_dir,
        log_file=log_file,
    )

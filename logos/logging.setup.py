from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from .paths import APP_LOGS_DIR, ensure_dirs

APP_LOG_FILE = APP_LOGS_DIR / "app.log"

def setup_app_logging(level: int = logging.INFO) -> logging.Logger:
    """
    Configure a root application logger that writes to console and logos/logs/app.log
    (not per-run). Call once on startup (CLI/entrypoint).
    """
    ensure_dirs([APP_LOGS_DIR])

    logger = logging.getLogger()  # root
    logger.setLevel(level)

    # Clear existing handlers (idempotent setup)
    logger.handlers.clear()

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    logger.addHandler(ch)

    # Rotating file handler for app-level logs
    fh = logging.handlers.RotatingFileHandler(
        APP_LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(level)
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    logger.addHandler(fh)

    return logger


def attach_run_file_handler(logger: logging.Logger, run_log_file: Path, level: int = logging.INFO) -> None:
    """
    Attach a file handler that logs to runs/{id}/logs/run.log for the provided logger.
    """
    run_log_file.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(run_log_file, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    logger.addHandler(fh)
from __future__ import annotations

import logging
from logging import Handler, Formatter, StreamHandler, getLogger
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Union

from core.io.dirs import ensure_dir

from .paths import APP_LOG_FILE, LIVE_LOG_FILE
from .utils.security import RedactingFilter

_configured = False
_live_handler: Optional[logging.Handler] = None

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
MAX_LOG_BYTES = 5 * 1024 * 1024
LOG_BACKUPS = 3


def _resolve_level(level: Union[str, int, None]) -> int:
    if isinstance(level, int):
        return level
    if isinstance(level, str):
        named = getattr(logging, level.upper(), None)
        if isinstance(named, int):
            return named
        try:
            return int(level)
        except ValueError:
            return logging.INFO
    return logging.INFO


def setup_app_logging(level: Union[str, int] = "INFO") -> None:
    """Configure global application logging once."""
    global _configured
    ensure_dir(APP_LOG_FILE.parent)
    resolved = _resolve_level(level)
    root = logging.getLogger()
    if not _configured:
        for handler in list(root.handlers):
            root.removeHandler(handler)
            handler.close()
        file_handler = _build_rotating_handler(APP_LOG_FILE, level=resolved)
        stream_handler = StreamHandler()
        stream_handler.setFormatter(Formatter(LOG_FORMAT))
        stream_handler.setLevel(resolved)
        stream_handler.addFilter(RedactingFilter())
        root.addHandler(file_handler)
        root.addHandler(stream_handler)
        _configured = True
    root.setLevel(resolved)
    for handler in root.handlers:
        handler.setLevel(resolved)


def attach_run_file_handler(
    log_file: Path, level: Optional[Union[str, int]] = None
) -> logging.Handler:
    """Attach a per-run log handler and return it for later removal."""
    handler = _build_rotating_handler(
        log_file, level=_resolve_level(level) if level is not None else None
    )
    getLogger().addHandler(handler)
    return handler


def detach_handler(handler: logging.Handler) -> None:
    """Remove and close a previously attached handler."""
    root = logging.getLogger()
    root.removeHandler(handler)
    handler.close()


def attach_live_runtime_handler(level: Union[str, int] = "INFO") -> logging.Handler:
    """Attach (or update) the shared live trading log handler."""
    global _live_handler
    ensure_dir(LIVE_LOG_FILE.parent)
    resolved = _resolve_level(level)
    if _live_handler is not None:
        _live_handler.setLevel(resolved)
        return _live_handler
    handler = _build_rotating_handler(LIVE_LOG_FILE, level=resolved)
    logging.getLogger().addHandler(handler)
    _live_handler = handler
    return handler


def _build_rotating_handler(path: Path, level: Optional[int] = None) -> Handler:
    ensure_dir(path.parent)
    handler = RotatingFileHandler(
        path,
        mode="a",
        encoding="utf-8",
        maxBytes=MAX_LOG_BYTES,
        backupCount=LOG_BACKUPS,
    )
    handler.setFormatter(Formatter(LOG_FORMAT))
    handler.addFilter(RedactingFilter())
    if level is not None:
        handler.setLevel(level)
    return handler

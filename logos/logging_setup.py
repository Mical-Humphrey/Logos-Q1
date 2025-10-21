from __future__ import annotations

import logging
import re
from logging import Filter, Handler, Formatter, StreamHandler, getLogger
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Union

from core.io.dirs import ensure_dir

from .paths import APP_LOG_FILE, LIVE_LOG_FILE

_configured = False
_live_handler: Optional[logging.Handler] = None

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
MAX_LOG_BYTES = 5 * 1024 * 1024
LOG_BACKUPS = 3


class SensitiveDataFilter(Filter):
    """Redact common secret patterns from log messages."""

    _KEY_VALUE_PATTERN = re.compile(
        r"(?i)(apikey|api_key|api-key|secret|token|password|passphrase|key)\s*[:=]\s*([^\s,;]+)"
    )
    _BEARER_PATTERN = re.compile(r"(?i)Bearer\s+[A-Za-z0-9._\-]+")

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - thin shim
        message = record.getMessage()
        redacted, changed = self._redact(message)
        if changed:
            record.msg = redacted
            record.args = ()
        return True

    @classmethod
    def _redact(cls, message: str) -> tuple[str, bool]:
        changed = False

        def key_repl(match: re.Match[str]) -> str:
            nonlocal changed
            changed = True
            return f"{match.group(1)}=<redacted>"

        message = cls._KEY_VALUE_PATTERN.sub(key_repl, message)

        def bearer_repl(match: re.Match[str]) -> str:
            nonlocal changed
            changed = True
            return "Bearer <redacted>"

        message = cls._BEARER_PATTERN.sub(bearer_repl, message)
        return message, changed


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
        stream_handler.addFilter(SensitiveDataFilter())
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
    handler.addFilter(SensitiveDataFilter())
    if level is not None:
        handler.setLevel(level)
    return handler

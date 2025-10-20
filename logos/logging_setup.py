from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Union

from .paths import APP_LOG_FILE, LIVE_LOG_FILE, ensure_dirs

_configured = False
_live_handler: Optional[logging.Handler] = None


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
	ensure_dirs([APP_LOG_FILE.parent])
	resolved = _resolve_level(level)
	if _configured:
		logging.getLogger().setLevel(resolved)
		return
	logging.basicConfig(
		level=resolved,
		format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
		handlers=[
			logging.FileHandler(APP_LOG_FILE, mode="a", encoding="utf-8"),
			logging.StreamHandler(),
		],
	)
	_configured = True


def attach_run_file_handler(log_file: Path, level: Optional[Union[str, int]] = None) -> logging.Handler:
	"""Attach a per-run log handler and return it for later removal."""
	ensure_dirs([log_file.parent])
	handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
	handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
	if level is not None:
		handler.setLevel(_resolve_level(level))
	root = logging.getLogger()
	root.addHandler(handler)
	return handler


def detach_handler(handler: logging.Handler) -> None:
	"""Remove and close a previously attached handler."""
	root = logging.getLogger()
	root.removeHandler(handler)
	handler.close()


def attach_live_runtime_handler(level: Union[str, int] = "INFO") -> logging.Handler:
	"""Attach (or update) the shared live trading log handler."""
	global _live_handler
	ensure_dirs([LIVE_LOG_FILE.parent])
	resolved = _resolve_level(level)
	if _live_handler is not None:
		_live_handler.setLevel(resolved)
		return _live_handler
	handler = logging.FileHandler(LIVE_LOG_FILE, mode="a", encoding="utf-8")
	handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
	handler.setLevel(resolved)
	logging.getLogger().addHandler(handler)
	_live_handler = handler
	return handler

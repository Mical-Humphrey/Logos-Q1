"""Atomic file writing utilities with cross-platform fsync semantics.

This module ensures crash-safe writes by:
- writing to a temporary file in the target directory (guaranteeing same-filesystem replacement),
- flushing and `os.fsync`-ing the temporary handle,
- atomically swapping it into place via `os.replace`,
- optionally syncing the parent directory to persist the rename on POSIX platforms.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import IO, Any, Callable, Dict

from os import fspath

from .dirs import ensure_dir

logger = logging.getLogger(__name__)


class AtomicWriteError(RuntimeError):
    """Raised when an atomic write cannot be completed safely."""


def _fsync_directory(path: Path) -> None:
    """Best-effort directory fsync, no-op on unsupported platforms."""

    try:
        dir_fd = os.open(fspath(path), os.O_RDONLY)
    except (FileNotFoundError, NotADirectoryError, PermissionError, OSError):
        return

    try:
        os.fsync(dir_fd)
    except OSError:
        # Windows typically does not support directory fsync; log at debug level.
        logger.debug("directory fsync unsupported path=%s", path)
    finally:
        os.close(dir_fd)


def atomic_write(
    path: Path,
    write: Callable[[IO[Any]], None],
    *,
    mode: str = "w",
    encoding: str = "utf-8",
    newline: str | None = None,
    sync_directory: bool = True,
) -> None:
    """Atomically write to *path* using *write* to populate a temporary file."""

    parent = path.parent
    ensure_dir(parent)

    tmp_path: Path | None = None
    options: Dict[str, Any] = {
        "mode": mode,
        "dir": parent,
        "delete": False,
    }

    binary_mode = "b" in mode
    if binary_mode:
        if newline is not None:
            raise ValueError("newline is unsupported in binary mode")
    else:
        options["encoding"] = encoding
        if newline is not None:
            options["newline"] = newline

    try:
        with tempfile.NamedTemporaryFile(**options) as tmp:
            tmp_path = Path(tmp.name)
            write(tmp)
            tmp.flush()
            os.fsync(tmp.fileno())
    except Exception:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        raise

    assert tmp_path is not None
    try:
        os.replace(tmp_path, path)
        if sync_directory:
            _fsync_directory(parent)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Atomically write text *content* to *path*."""

    def _writer(fh: IO[str]) -> None:
        fh.write(content)

    atomic_write(path, _writer, mode="w", encoding=encoding)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Atomically write binary *data* to *path*."""

    def _writer(fh: IO[bytes]) -> None:
        fh.write(data)

    atomic_write(path, _writer, mode="wb")


__all__ = [
    "atomic_write",
    "atomic_write_bytes",
    "atomic_write_text",
    "AtomicWriteError",
]

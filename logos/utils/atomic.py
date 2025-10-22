from __future__ import annotations

import warnings
from pathlib import Path
from typing import IO, Any, Callable

import core.io.atomic_write as core_atomic_write_module


_MESSAGE = "logos.utils.atomic is deprecated; import from core.io.atomic_write instead."


def atomic_write(
    path: Path,
    write: Callable[[IO[Any]], None],
    *,
    mode: str = "w",
    encoding: str = "utf-8",
    newline: str | None = None,
    sync_directory: bool = True,
) -> None:
    warnings.warn(_MESSAGE, DeprecationWarning, stacklevel=2)
    core_atomic_write_module.atomic_write(
        path,
        write,
        mode=mode,
        encoding=encoding,
        newline=newline,
        sync_directory=sync_directory,
    )


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    warnings.warn(_MESSAGE, DeprecationWarning, stacklevel=2)
    core_atomic_write_module.atomic_write_text(path, content, encoding=encoding)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    warnings.warn(_MESSAGE, DeprecationWarning, stacklevel=2)
    core_atomic_write_module.atomic_write_bytes(path, data)


__all__ = [
    "atomic_write",
    "atomic_write_text",
    "atomic_write_bytes",
]

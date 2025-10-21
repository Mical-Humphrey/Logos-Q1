from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import IO, Any, Callable


def atomic_write(
    path: Path,
    write: Callable[[IO[str]], None],
    *,
    mode: str = "w",
    encoding: str = "utf-8",
    newline: str | None = None,
) -> None:
    """Write to a temporary file in ``path``'s directory and atomically replace it."""

    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)

    tmp_path: Path | None = None
    tmp_kwargs: dict[str, Any] = {
        "mode": mode,
        "dir": parent,
        "delete": False,
    }
    binary_mode = "b" in mode
    if not binary_mode:
        tmp_kwargs["encoding"] = encoding
        if newline is not None:
            tmp_kwargs["newline"] = newline
    else:
        if newline is not None:
            raise ValueError("newline is not supported in binary mode")

    try:
        with tempfile.NamedTemporaryFile(**tmp_kwargs) as tmp:
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
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Atomically write ``content`` to ``path`` as text."""

    def _writer(fh: IO[str]) -> None:
        fh.write(content)

    atomic_write(path, _writer, mode="w", encoding=encoding)

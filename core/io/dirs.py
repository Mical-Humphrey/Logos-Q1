"""Directory management helpers with deterministic logging.

Environment knobs:
- LOGOS_AUTO_CREATE_DIRS (default: true)
- LOGOS_DIR_MODE (default: 0750 on POSIX; ignored on Windows)
- LOGOS_ENFORCE_DIR_MODE (default: false)

Log format for first-time creation:
  created dir path=/abs/path rel=relative/path mode=0750 source=auto component=core.io created=true
Additional keys:
  enforced_mode=true  -> mode re-applied to existing directories when enforcement enabled
  windows=true mode_ignored=true -> emitted when running on Windows where chmod is skipped
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable, Iterator, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WINDOWS = os.name == "nt"
_LOGGER = logging.getLogger(__name__)

_TRUE_LITERALS = {"1", "true", "t", "yes", "y", "on"}
_FALSE_LITERALS = {"0", "false", "f", "no", "n", "off"}


class DirectoryCreationError(RuntimeError):
    """Raised when a directory cannot be created or enforced."""


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    lowered = value.strip().lower()
    if lowered in _TRUE_LITERALS:
        return True
    if lowered in _FALSE_LITERALS:
        return False
    return default


def _parse_mode(value: str) -> int:
    text = value.strip().lower()
    if not text:
        raise ValueError("empty mode value")
    if text.startswith("0o"):
        text = text[2:]
    try:
        return int(text, 8)
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise ValueError(f"invalid POSIX mode literal: {value!r}") from exc


def dir_mode_from_env() -> Tuple[int | None, bool]:
    """Return (mode, usable) tuple derived from LOGOS_DIR_MODE."""

    raw = os.getenv("LOGOS_DIR_MODE")
    if raw is None or raw == "":
        mode = 0o750
    else:
        mode = _parse_mode(raw)
    return (mode, not WINDOWS)


def is_under_repo(path: Path) -> Tuple[bool, Path | None]:
    """Return (is_under_repo, relative_path) for logging convenience."""

    try:
        rel = path.relative_to(PROJECT_ROOT)
    except ValueError:
        return False, None
    return True, rel


def _resolve_mode(mode: int | None) -> Tuple[int | None, bool, bool]:
    env_mode, usable = dir_mode_from_env()
    resolved = mode if mode is not None else env_mode
    enforce = _env_flag("LOGOS_ENFORCE_DIR_MODE", False)
    return resolved, usable, enforce


def _bool_str(value: bool) -> str:
    return "true" if value else "false"


def _normalize_entries(
    paths: Iterable[Path | str | tuple[Path | str, bool]],
    default_owned: bool,
) -> Iterator[tuple[Path, bool]]:
    for entry in paths:
        if isinstance(entry, tuple):
            raw_path, owned = entry
        else:
            raw_path, owned = entry, default_owned
        yield Path(raw_path).expanduser(), bool(owned)


def ensure_dir(
    path: Path | str,
    create: bool | None = None,
    mode: int | None = None,
    *,
    owned: bool = True,
    logger: logging.Logger | None = None,
) -> Path:
    """Ensure that *path* exists, enforcing ownership and mode policies."""

    logger = logger or _LOGGER
    requested = Path(path).expanduser()
    resolved = requested if requested.is_absolute() else requested.resolve()

    create_default = _env_flag("LOGOS_AUTO_CREATE_DIRS", True)
    create_flag = create_default if create is None else bool(create)
    allow_create = create_flag and owned

    exists = resolved.exists()
    if exists and not resolved.is_dir():
        raise DirectoryCreationError(
            f"expected directory path={resolved} but found file"
        )

    if not exists and not allow_create:
        if owned:
            raise DirectoryCreationError(
                f"auto-create disabled for owned path path={resolved} hint='set LOGOS_AUTO_CREATE_DIRS=true or create manually'"
            )
        raise DirectoryCreationError(
            f"external path missing path={resolved} hint='create required input manually'"
        )

    created = False
    if not exists and allow_create:
        try:
            resolved.mkdir(parents=True, exist_ok=False)
            created = True
        except FileExistsError:
            created = False
        except OSError as exc:  # pragma: no cover - system-dependent
            raise DirectoryCreationError(
                f"failed to create directory path={resolved} errno={exc.errno} reason={exc.strerror}"
            ) from exc

    mode_value, mode_usable, enforce_mode = _resolve_mode(mode)
    mode_str = f"{mode_value:04o}" if mode_value is not None else ""
    mode_applied = False
    enforced_mode = False

    if mode_value is not None and mode_usable:
        try:
            if created:
                os.chmod(resolved, mode_value)
                mode_applied = True
            elif enforce_mode:
                os.chmod(resolved, mode_value)
                enforced_mode = True
        except OSError as exc:  # pragma: no cover - system-dependent
            raise DirectoryCreationError(
                f"failed to apply mode path={resolved} mode={mode_str} errno={exc.errno} reason={exc.strerror}"
            ) from exc

    log_creation = created or enforced_mode
    if log_creation:
        source = "auto" if create is None else "explicit"
        _, rel = is_under_repo(resolved)
        rel_text = str(rel) if rel is not None else ""
        fields = {
            "path": str(resolved),
            "rel": rel_text,
            "mode": mode_str,
            "source": source,
            "component": "core.io",
            "created": _bool_str(created),
        }
        if mode_applied:
            fields["mode_applied"] = _bool_str(True)
        if enforced_mode:
            fields["enforced_mode"] = _bool_str(True)
        if WINDOWS and mode_value is not None:
            fields["windows"] = _bool_str(True)
            fields["mode_ignored"] = _bool_str(not mode_usable)
        message = "created dir " + " ".join(
            f"{key}={value}" for key, value in fields.items()
        )
        logger.info(message)

    elif created:
        # A concurrent creator may have raced us; re-run logging for completeness.
        source = "auto" if create is None else "explicit"
        _, rel = is_under_repo(resolved)
        rel_text = str(rel) if rel is not None else ""
        fields = {
            "path": str(resolved),
            "rel": rel_text,
            "mode": mode_str,
            "source": source,
            "component": "core.io",
            "created": _bool_str(False),
            "race": _bool_str(True),
        }
        if WINDOWS and mode_value is not None:
            fields["windows"] = _bool_str(True)
            fields["mode_ignored"] = _bool_str(not mode_usable)
        message = "created dir " + " ".join(
            f"{key}={value}" for key, value in fields.items()
        )
        logger.info(message)

    return resolved


def ensure_dirs(
    paths: Iterable[Path | str | tuple[Path | str, bool]],
    create: bool | None = None,
    mode: int | None = None,
    *,
    owned: bool = True,
    logger: logging.Logger | None = None,
) -> List[Path]:
    """Ensure a batch of directories exists, returning resolved paths."""

    resolved: List[Path] = []
    for entry_path, entry_owned in _normalize_entries(paths, owned):
        resolved.append(
            ensure_dir(
                entry_path,
                create=create,
                mode=mode,
                owned=entry_owned,
                logger=logger,
            )
        )
    return resolved


__all__ = [
    "ensure_dir",
    "ensure_dirs",
    "dir_mode_from_env",
    "is_under_repo",
    "DirectoryCreationError",
]

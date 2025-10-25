from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from logos.paths import APP_LOGS_DIR, DATA_DIR, RUNS_DIR

__all__ = ["PathSandboxError", "DEFAULT_SANDBOX_ROOTS", "safe_resolve"]


class PathSandboxError(ValueError):
    """Raised when a supplied path escapes the configured sandbox roots."""

    def __init__(self, *, path: Path, message: str) -> None:
        super().__init__(message)
        self.path = Path(path)
        self.message = message

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


_DEFAULT_ROOTS: tuple[Path, ...] = (
    RUNS_DIR,
    DATA_DIR,
    APP_LOGS_DIR,
)
DEFAULT_SANDBOX_ROOTS: tuple[Path, ...] = tuple(root.resolve(strict=False) for root in _DEFAULT_ROOTS)


def _normalize_roots(roots: Iterable[Path] | None) -> Sequence[Path]:
    candidates = list(DEFAULT_SANDBOX_ROOTS if roots is None else roots)
    if not candidates:
        raise ValueError("At least one sandbox root is required")
    normalized: list[Path] = []
    for root in candidates:
        resolved = Path(root).expanduser().resolve(strict=False)
        if resolved not in normalized:
            normalized.append(resolved)
    return tuple(normalized)


def _within(root: Path, candidate: Path) -> bool:
    if candidate == root:
        return True
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def safe_resolve(
    value: Path | str,
    *,
    roots: Iterable[Path] | None = None,
    must_exist: bool = False,
    description: str | None = None,
) -> Path:
    """Return an absolute path guaranteed to live under one of *roots*.

    Parameters
    ----------
    value:
        The user-supplied path (relative or absolute).
    roots:
        Optional iterable of allow-listed root directories. When omitted, the
        default sandbox roots ``runs/``, ``data/``, and ``logos/logs/`` are used.
    must_exist:
        When true, ``Path.resolve(strict=True)`` is used to reject nonexistent
        paths early. When false, the function resolves without requiring the
        terminal path component to exist.
    description:
        Optional human-friendly label used in error messages.

    Raises
    ------
    PathSandboxError
        If *value* escapes the configured sandbox roots via absolute paths,
        ``..`` segments, or symlinks.
    """

    description = description or "path"
    candidate = Path(value)
    normalized_roots = _normalize_roots(roots)
    for root in normalized_roots:
        base = Path(root)
        if candidate.is_absolute():
            try:
                resolved = candidate.resolve(strict=must_exist)
            except FileNotFoundError:
                if must_exist:
                    raise
                resolved = candidate.resolve(strict=False)
        else:
            try:
                resolved = (base / candidate).resolve(strict=must_exist)
            except FileNotFoundError:
                if must_exist:
                    raise
                resolved = (base / candidate).resolve(strict=False)
        if _within(base, resolved):
            return resolved
    roots_desc = ", ".join(str(root) for root in normalized_roots)
    message = (
        f"{description} '{candidate}' is outside sandbox roots: {roots_desc}"
    )
    raise PathSandboxError(path=candidate, message=message)

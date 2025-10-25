from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

__all__ = ["YAMLSafetyError", "safe_load", "safe_load_path"]


class YAMLSafetyError(ValueError):
    """Raised when YAML parsing fails under safe loading rules."""

    def __init__(self, message: str, *, path: Path | None = None) -> None:
        super().__init__(message)
        self.path = path


def safe_load(data: Any) -> Any:
    """Wrapper around :func:`yaml.safe_load` with friendlier errors."""

    try:
        return yaml.safe_load(data)
    except yaml.YAMLError as exc:  # pragma: no cover - thin shim
        raise YAMLSafetyError(f"Unsafe or invalid YAML payload: {exc}") from exc


def safe_load_path(path: Path) -> Any:
    """Read and safely parse YAML from *path*."""

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:  # pragma: no cover - defensive
        raise YAMLSafetyError(f"YAML file not found: {path}", path=path) from exc
    except OSError as exc:  # pragma: no cover - defensive
        raise YAMLSafetyError(f"Unable to read YAML file: {path}", path=path) from exc
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise YAMLSafetyError(
            f"Unsafe or invalid YAML payload in {path}: {exc}", path=path
        ) from exc

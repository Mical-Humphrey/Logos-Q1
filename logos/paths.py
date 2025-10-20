from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOGOS_DIR = PROJECT_ROOT / "logos"
DOCS_DIR = PROJECT_ROOT / "docs"

_LEGACY_INPUT_DATA = PROJECT_ROOT / "input_data"

DATA_DIR = PROJECT_ROOT / "data"
if _LEGACY_INPUT_DATA.exists() and not DATA_DIR.exists():
    DATA_DIR = _LEGACY_INPUT_DATA

DATA_RAW_DIR = DATA_DIR / "raw"
DATA_CACHE_DIR = DATA_DIR / "cache"
CACHE_EQUITY_DIR = DATA_CACHE_DIR / "equity"
CACHE_CRYPTO_DIR = DATA_CACHE_DIR / "crypto"
CACHE_FOREX_DIR = DATA_CACHE_DIR / "forex"

RUNS_DIR = PROJECT_ROOT / "runs"
RUNS_LESSONS_DIR = RUNS_DIR / "lessons"
RUNS_LATEST_LINK = RUNS_DIR / "latest"

APP_LOGS_DIR = LOGOS_DIR / "logs"
APP_LOG_FILE = APP_LOGS_DIR / "app.log"

_CACHE_DIRS = {
    "equity": CACHE_EQUITY_DIR,
    "crypto": CACHE_CRYPTO_DIR,
    "forex": CACHE_FOREX_DIR,
}

DEFAULT_DIRS: list[Path] = [
    APP_LOGS_DIR,
    DATA_RAW_DIR,
    DATA_CACHE_DIR,
    *(_CACHE_DIRS.values()),
    RUNS_DIR,
    RUNS_LESSONS_DIR,
]


def ensure_dirs(extra: Iterable[Path] | None = None) -> None:
    """Create canonical directories (and any extras supplied)."""
    for path in list(DEFAULT_DIRS) + list(extra or []):
        path.mkdir(parents=True, exist_ok=True)


def resolve_cache_subdir(asset_class: str) -> Path:
    """Return the proper cache directory for the asset class."""
    key = asset_class.lower()
    if key == "fx":
        key = "forex"
    path = _CACHE_DIRS.get(key)
    if path is None:
        path = DATA_CACHE_DIR / key
        path.mkdir(parents=True, exist_ok=True)
        _CACHE_DIRS[key] = path
    return path


def runs_latest_symlink() -> Path:
    return RUNS_LATEST_LINK


def env_seed(default: int = 7) -> int:
    value = os.getenv("LOGOS_SEED")
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


def safe_slug(value: str) -> str:
    return value.replace("/", "-").replace("=", "-").replace(" ", "-")
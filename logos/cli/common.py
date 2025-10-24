from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Dict

from dotenv import dotenv_values

from core.io.atomic_write import atomic_write_text
from core.io.dirs import ensure_dir

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


def resolve_offline_flag(flag: bool | None) -> bool:
    if flag:
        return True
    value = os.getenv("LOGOS_OFFLINE_ONLY")
    if value is None:
        return False
    token = value.strip().lower()
    return token in {"1", "true", "yes", "on"}


def load_env(path: Path = DEFAULT_ENV_PATH) -> Dict[str, str]:
    if not path.exists():
        return {}
    data = dotenv_values(path)
    return {key: str(value) for key, value in data.items() if value is not None}


def write_env(values: Dict[str, str], path: Path = DEFAULT_ENV_PATH) -> None:
    lines = [f"{key}={value}" for key, value in sorted(values.items())]
    if lines and not lines[-1].endswith("\n"):
        lines[-1] = lines[-1] + "\n"
    content = "\n".join(lines)
    if not content.endswith("\n"):
        content += "\n"
    atomic_write_text(path, content, encoding="utf-8")


def update_symlink(target: Path, link: Path) -> None:
    link = link.resolve()
    ensure_dir(link.parent)
    if link.exists() or link.is_symlink():
        try:
            if link.is_symlink() or link.is_file():
                link.unlink()
            else:
                shutil.rmtree(link)
        except Exception:
            pass
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except Exception:
        atomic_write_text(link, str(target), encoding="utf-8")

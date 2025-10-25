from __future__ import annotations

from pathlib import Path

import pytest

from logos.paths import RUNS_DIR
from logos.utils.paths import PathSandboxError, safe_resolve


def test_safe_resolve_allows_runs_root() -> None:
    target = safe_resolve(RUNS_DIR / "demo" / "file.txt")
    assert target == (RUNS_DIR / "demo" / "file.txt").resolve()


def test_safe_resolve_within_custom_root(tmp_path: Path) -> None:
    sandbox_root = tmp_path / "sandbox"
    sandbox_root.mkdir()
    target = safe_resolve("demo/file.txt", roots=[sandbox_root])
    assert target == sandbox_root.resolve() / "demo" / "file.txt"


def test_safe_resolve_blocks_parent_escape(tmp_path: Path) -> None:
    sandbox_root = tmp_path / "escape"
    sandbox_root.mkdir()
    with pytest.raises(PathSandboxError) as exc:
        safe_resolve("../outside.txt", roots=[sandbox_root])
    assert "outside sandbox" in str(exc.value).lower()


def test_safe_resolve_blocks_symlink_escape(tmp_path: Path) -> None:
    sandbox_root = tmp_path / "symlink"
    sandbox_root.mkdir()
    target_dir = tmp_path / "outside"
    target_dir.mkdir()
    target_file = target_dir / "secret.txt"
    target_file.write_text("secret", encoding="utf-8")
    link_path = sandbox_root / "link"
    link_path.symlink_to(target_dir, target_is_directory=True)
    with pytest.raises(PathSandboxError) as exc:
        safe_resolve("link/secret.txt", roots=[sandbox_root])
    assert "outside" in str(exc.value).lower()

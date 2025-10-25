from __future__ import annotations

import runpy
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "ops" / "monitor.py"


@pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="monitor script missing")
def test_check_disk_invalid_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    namespace = runpy.run_path(str(SCRIPT_PATH))
    check_disk = namespace["_check_disk"]

    invalid_path = tmp_path / "missing"
    monkeypatch.setenv("LOGOS_DISK_PATH", str(invalid_path))
    issues = check_disk()
    assert issues
    assert f"disk path invalid: {invalid_path}" in issues

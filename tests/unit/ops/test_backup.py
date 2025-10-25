from __future__ import annotations

import os
import subprocess
import tarfile
from contextlib import closing
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "ops" / "backup.sh"


@pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="backup script missing")
def test_backup_honours_env_overrides(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs_override"
    configs_dir = tmp_path / "configs_override"
    out_dir = tmp_path / "out"
    runs_dir.mkdir()
    configs_dir.mkdir()
    out_dir.mkdir()

    (runs_dir / "sentinel.txt").write_text("runs", encoding="utf-8")
    (configs_dir / "config.yaml").write_text("configs", encoding="utf-8")

    env = os.environ.copy()
    env.update(
        {
            "RUNS_DIR": str(runs_dir),
            "CONFIGS_DIR": str(configs_dir),
            "OUT_DIR": str(out_dir),
            "ALLOW_OUTSIDE_BACKUP": "1",
        }
    )

    result = subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    archives = sorted(out_dir.glob("logos_backup_*.tar.gz"))
    assert len(archives) == 1

    archive = archives[0]
    with tarfile.open(archive) as handle:
        names = handle.getnames()
        assert any(name.startswith("runs/") for name in names)
        assert any(name.startswith("configs/") for name in names)
        assert any(name.startswith("manifest/") for name in names)
        assert all(not name.startswith("/") for name in names)

        runs_member = handle.getmember("runs/sentinel.txt")
        stream_runs = handle.extractfile(runs_member)
        assert stream_runs is not None
        with closing(stream_runs) as stream:
            assert stream.read().decode("utf-8") == "runs"

        manifest_member = handle.getmember("manifest/manifest.txt")
        stream_manifest = handle.extractfile(manifest_member)
        assert stream_manifest is not None
        with closing(stream_manifest) as stream:
            manifest_text = stream.read().decode("utf-8")
            assert str(runs_dir.resolve()) in manifest_text
            assert str(configs_dir.resolve()) in manifest_text


@pytest.mark.skipif(not SCRIPT_PATH.exists(), reason="backup script missing")
def test_backup_disallows_outside_when_flag_disabled(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs_outside"
    configs_dir = tmp_path / "configs_outside"
    runs_dir.mkdir()
    configs_dir.mkdir()
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    env = os.environ.copy()
    env.update(
        {
            "RUNS_DIR": str(runs_dir),
            "CONFIGS_DIR": str(configs_dir),
            "OUT_DIR": str(out_dir),
            "ALLOW_OUTSIDE_BACKUP": "0",
        }
    )

    result = subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "outside" in result.stderr.lower() or "outside" in result.stdout.lower()
    assert not list(out_dir.glob("logos_backup_*.tar.gz"))

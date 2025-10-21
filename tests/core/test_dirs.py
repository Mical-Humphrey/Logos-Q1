from __future__ import annotations

import logging
import os
import stat
import sys
import warnings

import pytest

from core.io.dirs import DirectoryCreationError, ensure_dir, ensure_dirs


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX-specific")
def test_ensure_dir_auto_create_enabled_creates_and_logs_once_posix(
    tmp_path, caplog, monkeypatch
):
    target = tmp_path / "owned"
    monkeypatch.setenv("LOGOS_AUTO_CREATE_DIRS", "true")
    monkeypatch.delenv("LOGOS_ENFORCE_DIR_MODE", raising=False)
    monkeypatch.delenv("LOGOS_DIR_MODE", raising=False)

    caplog.set_level(logging.INFO, logger="core.io.dirs")

    ensure_dir(target)
    ensure_dir(target)

    records = [
        record
        for record in caplog.records
        if record.name == "core.io.dirs" and "created dir" in record.message
    ]
    assert len(records) == 1
    message = records[0].message
    assert f"path={target.resolve()}" in message
    assert "created=true" in message
    assert "source=auto" in message
    assert "component=core.io" in message


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows only")
def test_ensure_dir_auto_create_enabled_windows_logs_mode_ignored(
    tmp_path, caplog, monkeypatch
):
    target = tmp_path / "owned"
    monkeypatch.setenv("LOGOS_AUTO_CREATE_DIRS", "true")

    caplog.set_level(logging.INFO, logger="core.io.dirs")

    ensure_dir(target)

    records = [
        record
        for record in caplog.records
        if record.name == "core.io.dirs" and "created dir" in record.message
    ]
    assert len(records) == 1
    message = records[0].message
    assert "windows=true" in message
    assert "mode_ignored=true" in message


def test_ensure_dir_auto_create_disabled_owned_path_errors_and_creates_nothing(
    tmp_path, monkeypatch
):
    target = tmp_path / "owned"
    monkeypatch.setenv("LOGOS_AUTO_CREATE_DIRS", "false")

    with pytest.raises(DirectoryCreationError) as excinfo:
        ensure_dir(target)

    assert "auto-create disabled for owned path" in str(excinfo.value)
    assert not target.exists()


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX-specific")
def test_ensure_dir_mode_applied_on_create_posix_only(tmp_path, monkeypatch):
    target = tmp_path / "owned"
    monkeypatch.setenv("LOGOS_AUTO_CREATE_DIRS", "true")
    monkeypatch.setenv("LOGOS_DIR_MODE", "0710")

    ensure_dir(target)

    mode = stat.S_IMODE(os.stat(target).st_mode)
    assert mode == 0o710


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX-specific")
def test_ensure_dir_enforce_mode_on_existing_when_env_true_posix_only(
    tmp_path, caplog, monkeypatch
):
    target = tmp_path / "owned"
    target.mkdir(parents=True)
    os.chmod(target, 0o755)

    monkeypatch.setenv("LOGOS_AUTO_CREATE_DIRS", "true")
    monkeypatch.setenv("LOGOS_ENFORCE_DIR_MODE", "true")
    monkeypatch.setenv("LOGOS_DIR_MODE", "0700")

    caplog.set_level(logging.INFO, logger="core.io.dirs")

    ensure_dir(target)

    mode = stat.S_IMODE(os.stat(target).st_mode)
    assert mode == 0o700

    records = [
        record
        for record in caplog.records
        if record.name == "core.io.dirs" and "created dir" in record.message
    ]
    assert len(records) == 1
    message = records[0].message
    assert "created=false" in message
    assert "enforced_mode=true" in message


def test_ensure_dirs_batch_mixed_paths_and_owned_flags(tmp_path, monkeypatch):
    owned = tmp_path / "owned"
    external = tmp_path / "external"
    external.mkdir()

    monkeypatch.setenv("LOGOS_AUTO_CREATE_DIRS", "true")

    results = ensure_dirs([(owned, True), (external, False)])

    assert owned in results and external in results
    assert owned.exists()
    assert external.exists()


def test_paths_shim_emits_deprecation_once_and_forwards(tmp_path, monkeypatch):
    import logos.paths as logos_paths

    extra_dir = tmp_path / "shim"
    monkeypatch.setenv("LOGOS_AUTO_CREATE_DIRS", "true")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("default", DeprecationWarning)
        logos_paths.ensure_dirs(extra=[extra_dir])

    assert any(
        "logos.paths.ensure_dirs is deprecated" in str(item.message) for item in caught
    )
    assert extra_dir.exists()

    with warnings.catch_warnings(record=True) as caught_again:
        warnings.simplefilter("default", DeprecationWarning)
        logos_paths.ensure_dirs(extra=[extra_dir])

    assert not caught_again

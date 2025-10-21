from __future__ import annotations

import logging
from pathlib import Path

import pytest

from core.io.dirs import DirectoryCreationError

import logos.logging_setup as logging_setup


@pytest.fixture(autouse=True)
def reset_root_logger():
    """Restore the root logger between tests to avoid cross-test leakage."""

    original_handlers = list(logging.getLogger().handlers)
    try:
        yield
    finally:
        root = logging.getLogger()
        for handler in list(root.handlers):
            root.removeHandler(handler)
            handler.close()
        for handler in original_handlers:
            root.addHandler(handler)
        logging_setup._configured = False
        logging_setup._live_handler = None


def test_setup_app_logging_logs_directory_creation(tmp_path, monkeypatch, caplog):
    app_logs = tmp_path / "logs"
    app_file = app_logs / "app.log"

    monkeypatch.setattr(logging_setup, "APP_LOG_FILE", app_file, raising=False)
    logging_setup._configured = False

    caplog.set_level(logging.INFO, logger="core.io.dirs")

    monkeypatch.setenv("LOGOS_AUTO_CREATE_DIRS", "true")
    monkeypatch.delenv("LOGOS_DIR_MODE", raising=False)
    monkeypatch.delenv("LOGOS_ENFORCE_DIR_MODE", raising=False)

    logging_setup.setup_app_logging()

    messages = [
        record.message for record in caplog.records if record.name == "core.io.dirs"
    ]
    expected_path = str(app_logs.resolve())
    assert any(
        "created dir" in message and expected_path in message for message in messages
    )


def test_setup_app_logging_respects_auto_create_disabled(tmp_path, monkeypatch):
    app_logs = tmp_path / "logs"
    app_file = app_logs / "app.log"

    monkeypatch.setattr(logging_setup, "APP_LOG_FILE", app_file, raising=False)
    logging_setup._configured = False

    monkeypatch.setenv("LOGOS_AUTO_CREATE_DIRS", "false")

    with pytest.raises(DirectoryCreationError) as excinfo:
        logging_setup.setup_app_logging()

    assert "auto-create disabled" in str(excinfo.value)
    assert not app_logs.exists()


def test_attach_run_file_handler_registers_handler(tmp_path):
    log_file = tmp_path / "run.log"
    root = logging.getLogger()
    handler = logging_setup.attach_run_file_handler(log_file, level="DEBUG")

    try:
        assert handler in root.handlers
        assert Path(handler.baseFilename) == log_file
        assert handler.level == logging.DEBUG
    finally:
        logging_setup.detach_handler(handler)


def test_attach_live_runtime_handler_reuses_existing(tmp_path, monkeypatch):
    live_file = tmp_path / "live.log"
    monkeypatch.setattr(logging_setup, "LIVE_LOG_FILE", live_file, raising=False)
    logging_setup._live_handler = None

    first = logging_setup.attach_live_runtime_handler(level="WARNING")
    second = logging_setup.attach_live_runtime_handler(level="ERROR")

    try:
        assert first is second
        assert first.level == logging.ERROR
    finally:
        logging_setup.detach_handler(first)

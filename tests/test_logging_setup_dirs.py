from __future__ import annotations

import logging

import pytest

from core.io.dirs import DirectoryCreationError

import logos.logging_setup as logging_setup


@pytest.fixture(autouse=True)
def reset_root_logger():
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

    messages = [record.message for record in caplog.records if record.name == "core.io.dirs"]
    expected_path = str(app_logs.resolve())
    assert any("created dir" in message and expected_path in message for message in messages)


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
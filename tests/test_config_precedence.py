from __future__ import annotations

import logging

import pytest

from logos.config import load_settings


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("START_DATE", raising=False)
    monkeypatch.delenv("END_DATE", raising=False)
    monkeypatch.delenv("SYMBOL", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)


def test_precedence_cli_wins(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="logos.config")
    monkeypatch.setenv("START_DATE", "2024-01-01")

    settings, sources = load_settings(
        cli_overrides={"start": "2024-02-01"},
        env_policy={"start": True},
        include_sources=True,
    )

    assert settings.start == "2024-02-01"
    assert sources["start"] == "cli"
    assert any(
        "config_resolved key=start" in record.message and "source=cli" in record.message
        for record in caplog.records
    )


def test_precedence_env_allowed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="logos.config")
    monkeypatch.setenv("END_DATE", "2024-03-01")

    settings, sources = load_settings(env_policy={"end": True}, include_sources=True)

    assert settings.end == "2024-03-01"
    assert sources["end"] == "env"
    assert any(
        "config_resolved key=end" in record.message and "source=env" in record.message
        for record in caplog.records
    )


def test_precedence_env_blocked(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="logos.config")
    monkeypatch.setenv("START_DATE", "2024-04-01")

    settings, sources = load_settings(env_policy={"start": False}, include_sources=True)

    assert settings.start == "2023-01-01"
    assert sources["start"] == "default"
    assert any(
        "config_resolved key=start" in record.message
        and "source=default" in record.message
        for record in caplog.records
    )


def test_precedence_redacts_secrets(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="logos.config")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "super-secret")

    settings, sources = load_settings(include_sources=True)

    assert settings.alpaca_secret_key == "super-secret"
    assert sources["alpaca_secret_key"] == "env"
    assert any(
        "config_resolved key=alpaca_secret_key" in record.message
        and "value=***" in record.message
        for record in caplog.records
    )

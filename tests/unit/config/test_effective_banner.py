from __future__ import annotations

import logging

import pytest

from logos.config import Settings
from logos.live import main as live_main


def test_effective_config_banner_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="logos.live.main")
    settings = Settings(start="2024-01-01", end="2024-02-01", symbol="MSFT")
    limits = {
        "max_notional": 5_000.0,
        "max_position": 500.0,
        "max_drawdown_bps": 250.0,
        "portfolio_drawdown_cap": 0.15,
        "daily_portfolio_loss_cap": 0.05,
    }
    live_main._emit_effective_config_banner(
        settings,
        broker="paper",
        mode="paper",
        send_orders=False,
        kill_switch_enabled=False,
        limits=limits,
    )
    messages = [
        record.message
        for record in caplog.records
        if "Effective Config" in record.message
    ]
    assert messages, "Expected banner log entry"
    banner = messages[0]
    assert "mode=paper" in banner
    assert "broker=paper" in banner
    assert "notional_cap=$5,000" in banner
    assert "daily_loss=5.0%" in banner

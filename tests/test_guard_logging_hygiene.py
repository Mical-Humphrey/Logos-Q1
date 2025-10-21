from __future__ import annotations

import importlib
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Union, cast

import pytest

from logos.live.risk import (
    RiskContext,
    RiskLimits,
    check_circuit_breakers,
    check_order_limits,
)


def _ctx(**overrides: Union[float, int]) -> RiskContext:
    payload: dict[str, Union[float, int]] = {
        "equity": 100_000.0,
        "position_quantity": 0.0,
        "realized_drawdown_bps": 0.0,
        "consecutive_rejects": 0,
        "last_bar_ts": 0.0,
        "now_ts": 0.0,
    }
    payload.update(overrides)
    return RiskContext(
        equity=float(payload["equity"]),
        position_quantity=float(payload["position_quantity"]),
        realized_drawdown_bps=float(payload["realized_drawdown_bps"]),
        consecutive_rejects=int(payload["consecutive_rejects"]),
        last_bar_ts=float(payload["last_bar_ts"]),
        now_ts=float(payload["now_ts"]),
    )


def test_guard_kill_switch_triggers_halt(tmp_path: Path) -> None:
    kill_file = tmp_path / "kill.switch"
    kill_file.write_text("halt", encoding="utf-8")
    limits = RiskLimits(kill_switch_file=kill_file)
    decision = check_circuit_breakers(limits, _ctx(now_ts=100.0, last_bar_ts=0.0))
    assert not decision.allowed
    assert decision.reason == "kill_switch_triggered"


def test_guard_stale_data_fencepost() -> None:
    limits = RiskLimits(stale_data_threshold_s=300.0)
    before = check_circuit_breakers(limits, _ctx(now_ts=299.9, last_bar_ts=0.0))
    assert before.allowed
    at_threshold = check_circuit_breakers(limits, _ctx(now_ts=300.0, last_bar_ts=0.0))
    assert not at_threshold.allowed
    assert at_threshold.reason == "data_stale"


def test_guard_exact_limits_allowed() -> None:
    limits = RiskLimits(max_notional=1_000.0, symbol_position_limits={"MSFT": 10.0})
    ctx = _ctx(position_quantity=5.0)
    decision = check_order_limits(
        "MSFT", quantity=5.0, price=200.0, limits=limits, ctx=ctx
    )
    assert decision.allowed
    decision_position = check_order_limits(
        "MSFT",
        quantity=-5.0,
        price=200.0,
        limits=limits,
        ctx=_ctx(position_quantity=10.0),
    )
    assert decision_position.allowed


def test_logging_rotates_and_redacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module("logos.logging_setup")
    module = importlib.reload(module)
    monkeypatch.setattr(module, "APP_LOG_FILE", tmp_path / "app.log", raising=False)
    monkeypatch.setattr(module, "LIVE_LOG_FILE", tmp_path / "live.log", raising=False)
    module.setup_app_logging()

    root = logging.getLogger()
    file_handlers = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
    assert file_handlers, "Expected rotating file handlers to be configured"
    for handler in file_handlers:
        assert handler.maxBytes == module.MAX_LOG_BYTES
        assert handler.backupCount == module.LOG_BACKUPS
        assert any(
            isinstance(flt, module.SensitiveDataFilter) for flt in handler.filters
        )

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg="Posting token=%s secret:%s",
        args=("abc123", "s3cr3t"),
        exc_info=None,
        func=None,
        sinfo=None,
    )
    for handler in file_handlers:
        for flt in handler.filters:
            if hasattr(flt, "filter"):
                flt.filter(record)
            else:
                flt(record)
    message = record.getMessage()
    assert "abc123" not in message
    assert "s3cr3t" not in message
    assert "<redacted>" in message

    for root_handler in list(root.handlers):
        root.removeHandler(root_handler)
        root_handler.close()
    importlib.reload(module)


def test_live_handler_uses_rotation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module("logos.logging_setup")
    module = importlib.reload(module)
    monkeypatch.setattr(module, "LIVE_LOG_FILE", tmp_path / "live.log", raising=False)
    handler_generic = module.attach_live_runtime_handler()
    assert isinstance(handler_generic, RotatingFileHandler)
    handler = cast(RotatingFileHandler, handler_generic)
    assert handler.maxBytes == module.MAX_LOG_BYTES
    assert handler.backupCount == module.LOG_BACKUPS
    assert any(isinstance(flt, module.SensitiveDataFilter) for flt in handler.filters)
    logging.getLogger().removeHandler(handler)
    handler.close()
    importlib.reload(module)

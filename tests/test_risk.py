import tempfile
from pathlib import Path

import pytest

from logos.live.risk import (
    RiskContext,
    RiskDecision,
    RiskLimits,
    check_circuit_breakers,
    check_order_limits,
)


def test_check_order_limits_blocks_notional_and_position():
    limits = RiskLimits(max_notional=1_000.0, max_position=10.0)
    ctx = RiskContext(
        equity=10_000.0,
        position_quantity=0.0,
        realized_drawdown_bps=0.0,
        consecutive_rejects=0,
        last_bar_ts=0.0,
        now_ts=0.0,
    )
    decision = check_order_limits(quantity=20.0, price=100.0, limits=limits, ctx=ctx)
    assert not decision.allowed and decision.reason == "max_notional_exceeded"

    ctx = RiskContext(
        equity=10_000.0,
        position_quantity=9.0,
        realized_drawdown_bps=0.0,
        consecutive_rejects=0,
        last_bar_ts=0.0,
        now_ts=0.0,
    )
    decision = check_order_limits(quantity=5.0, price=50.0, limits=limits, ctx=ctx)
    assert not decision.allowed and decision.reason == "max_position_exceeded"


def test_check_circuit_breakers_handles_kill_switch_and_drawdown(tmp_path: Path):
    kill_file = tmp_path / "kill"
    kill_file.write_text("halt", encoding="utf-8")
    limits = RiskLimits(max_drawdown_bps=100.0, kill_switch_file=kill_file, max_consecutive_rejects=3, stale_data_threshold_s=10.0)
    ctx = RiskContext(
        equity=9_000.0,
        position_quantity=0.0,
        realized_drawdown_bps=-120.0,
        consecutive_rejects=4,
        last_bar_ts=0.0,
        now_ts=20.0,
    )

    decision = check_circuit_breakers(limits, ctx)
    assert not decision.allowed
    assert decision.reason == "kill_switch_triggered"

    kill_file.unlink()
    decision = check_circuit_breakers(limits, ctx)
    assert not decision.allowed
    assert decision.reason == "drawdown_limit_reached"

    ctx = RiskContext(
        equity=9_500.0,
        position_quantity=0.0,
        realized_drawdown_bps=-80.0,
        consecutive_rejects=4,
        last_bar_ts=0.0,
        now_ts=20.0,
    )
    decision = check_circuit_breakers(limits, ctx)
    assert not decision.allowed and decision.reason == "reject_limit_reached"

    ctx = RiskContext(
        equity=9_500.0,
        position_quantity=0.0,
        realized_drawdown_bps=-80.0,
        consecutive_rejects=0,
        last_bar_ts=0.0,
        now_ts=20.0,
    )
    decision = check_circuit_breakers(limits, ctx)
    assert not decision.allowed and decision.reason == "data_stale"

    ctx = RiskContext(
        equity=9_500.0,
        position_quantity=0.0,
        realized_drawdown_bps=-80.0,
        consecutive_rejects=0,
        last_bar_ts=15.0,
        now_ts=20.0,
    )
    decision = check_circuit_breakers(limits, ctx)
    assert decision.allowed

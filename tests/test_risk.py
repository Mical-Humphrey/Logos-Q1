from pathlib import Path

from logos.live.risk import (
    RiskContext,
    RiskDecision,
    RiskLimits,
    check_circuit_breakers,
    check_order_limits,
    enforce_guards,
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
    decision = check_order_limits(symbol="AAPL", quantity=20.0, price=100.0, limits=limits, ctx=ctx)
    assert not decision.allowed and decision.reason == "max_notional_exceeded"

    ctx = RiskContext(
        equity=10_000.0,
        position_quantity=9.0,
        realized_drawdown_bps=0.0,
        consecutive_rejects=0,
        last_bar_ts=0.0,
        now_ts=0.0,
    )
    decision = check_order_limits(symbol="AAPL", quantity=5.0, price=50.0, limits=limits, ctx=ctx)
    assert not decision.allowed and decision.reason == "max_position_exceeded"


def test_enforce_guards_logs_and_persists_on_first_violation(caplog):
    limits = RiskLimits(max_notional=1_000.0, symbol_position_limits={"MSFT": 100.0}, max_drawdown_bps=200.0)
    ctx = RiskContext(
        equity=10_000.0,
        position_quantity=0.0,
        realized_drawdown_bps=-50.0,
        consecutive_rejects=0,
        last_bar_ts=0.0,
        now_ts=0.0,
    )

    snapshot_calls = []

    def persist(decision: RiskDecision) -> None:
        snapshot_calls.append(decision.reason)

    with caplog.at_level("ERROR"):
        decision = enforce_guards(
            symbol="MSFT",
            quantity=15.0,
            price=100.0,
            limits=limits,
            ctx=ctx,
            persist_snapshot=persist,
        )

    assert not decision.allowed
    assert decision.reason == "max_notional_exceeded"
    assert snapshot_calls == ["max_notional_exceeded"]
    assert "risk_guard_halt" in caplog.records[0].message
    assert "max_notional_exceeded" in caplog.records[0].message


def test_enforce_guards_halts_on_position_before_drawdown(caplog):
    limits = RiskLimits(
        max_notional=100_000.0,
        symbol_position_limits={"BTC-USD": 1.0},
        max_drawdown_bps=50.0,
    )
    ctx = RiskContext(
        equity=20_000.0,
        position_quantity=0.8,
        realized_drawdown_bps=-100.0,
        consecutive_rejects=0,
        last_bar_ts=0.0,
        now_ts=0.0,
    )

    with caplog.at_level("ERROR"):
        decision = enforce_guards(
            symbol="BTC-USD",
            quantity=0.5,
            price=10_000.0,
            limits=limits,
            ctx=ctx,
        )

    assert not decision.allowed
    assert decision.reason == "max_position_exceeded"
    assert any("max_position_exceeded" in rec.message for rec in caplog.records)


def test_enforce_guards_halts_on_drawdown(caplog):
    limits = RiskLimits(max_notional=50_000.0, max_position=1_000.0, max_drawdown_bps=100.0)
    ctx = RiskContext(
        equity=5_000.0,
        position_quantity=100.0,
        realized_drawdown_bps=-150.0,
        consecutive_rejects=0,
        last_bar_ts=0.0,
        now_ts=0.0,
    )

    with caplog.at_level("ERROR"):
        decision = enforce_guards(
            symbol="AAPL",
            quantity=10.0,
            price=150.0,
            limits=limits,
            ctx=ctx,
        )

    assert not decision.allowed
    assert decision.reason == "session_drawdown_limit"
    assert any("session_drawdown_limit" in rec.message for rec in caplog.records)


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
    assert decision.reason == "session_drawdown_limit"

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

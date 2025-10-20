"""Translator quantisation tests (minimal slice).

These tests verify price tick and lot-size rounding for the translator. Other
behaviours remain skipped until later milestones.
"""

from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path

import pytest

from logos.live.translator import SymbolMetadataRegistry, Translator
from logos.live.types import Account, OrderSide, SizingInstruction

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "live"


@pytest.fixture(scope="module")
def metadata_registry() -> SymbolMetadataRegistry:
    """Load symbol metadata for translator tests."""

    return SymbolMetadataRegistry.from_yaml(FIXTURES / "symbols.yaml")


@pytest.fixture(scope="module")
def account_state() -> Account:
    """Account snapshot aligned with fixture payload."""

    payload = json.loads((FIXTURES / "account_start.json").read_text())
    return Account(
        equity=Decimal(str(payload["equity"])),
        cash=Decimal(str(payload["cash"])),
        positions={},
    )


def test_quantization_respects_precision_and_lot_size(
    metadata_registry: SymbolMetadataRegistry,
    account_state: Account,
) -> None:
    translator = Translator(metadata_registry)
    sizing = SizingInstruction.fixed_notional(Decimal("250"))

    intent = translator.build_order_intent(
        signal_symbol="BTC-USD",
        side=OrderSide.BUY,
        signal_price=Decimal("34123.4567"),
        sizing=sizing,
        account=account_state,
    )

    assert intent.price.limit == Decimal("34123.46")
    assert intent.quantity == Decimal("0.007")
    assert intent.metadata.symbol == "BTC-USD"


def test_notional_caps_and_rejects_out_of_bounds_orders(
    metadata_registry: SymbolMetadataRegistry,
    account_state: Account,
) -> None:
    translator = Translator(metadata_registry)

    sizing_large = SizingInstruction.fixed_notional(Decimal("80000"))
    with pytest.raises(ValueError) as oversized:
        translator.build_order_intent(
            signal_symbol="BTC-USD",
            side=OrderSide.BUY,
            signal_price=Decimal("34000"),
            sizing=sizing_large,
            account=account_state,
        )
    assert "exceeds max notional" in str(oversized.value)

    original_min_notional = metadata_registry._entries["AAPL"].min_notional
    metadata_registry._entries["AAPL"].min_notional = Decimal("500")
    try:
        sizing_small = SizingInstruction.fixed_notional(Decimal("200"))
        with pytest.raises(ValueError) as undersized:
            translator.build_order_intent(
                signal_symbol="AAPL",
                side=OrderSide.BUY,
                signal_price=Decimal("170.10"),
                sizing=sizing_small,
                account=account_state,
            )
        assert "below min notional" in str(undersized.value)
    finally:
        metadata_registry._entries["AAPL"].min_notional = original_min_notional


@pytest.mark.skip(reason="Percent-of-equity sizing delivered in a later milestone")
def test_sizing_rules_fixed_vs_percent_of_equity() -> None:
    raise NotImplementedError


def test_symbol_metadata_resolution_and_legacy_aliases(
    metadata_registry: SymbolMetadataRegistry,
    account_state: Account,
) -> None:
    translator = Translator(metadata_registry)
    sizing = SizingInstruction.fixed_notional(Decimal("3500"))

    intent = translator.build_order_intent(
        signal_symbol="BTCUSD",
        side=OrderSide.SELL,
        signal_price=Decimal("35000"),
        sizing=sizing,
        account=account_state,
    )

    assert intent.symbol == "BTC-USD"
    assert intent.metadata.symbol == "BTC-USD"
    assert intent.quantity == Decimal("0.1")


def test_unknown_symbol_raises_informative_error(
    metadata_registry: SymbolMetadataRegistry,
    account_state: Account,
) -> None:
    translator = Translator(metadata_registry)

    with pytest.raises(KeyError) as excinfo:
        translator.build_order_intent(
            signal_symbol="UNKNOWN",
            side=OrderSide.BUY,
            signal_price=Decimal("100"),
            sizing=SizingInstruction.fixed_notional(Decimal("1000")),
            account=account_state,
        )

    assert "Unknown symbol or alias" in str(excinfo.value)

"""Strategy signal to order intent translator stub.

Sprint A will replace the placeholders with deterministic quantisation logic
and metadata-driven validation. For now the scaffolding exists so tests can
assert desired behaviour and fail until implementation lands.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from pathlib import Path
from typing import Dict

from logos.live.types import (
    Account,
    OrderIntent,
    OrderSide,
    Pricing,
    SizingInstruction,
    SymbolMetadata,
)
from logos.utils.yaml_safe import safe_load_path


class SymbolMetadataRegistry:
    """Resolve symbol metadata (including aliases) for live trading."""

    def __init__(self, entries: Dict[str, SymbolMetadata]) -> None:
        self._entries = entries
        self._aliases: Dict[str, SymbolMetadata] = {}
        for metadata in entries.values():
            for alias in metadata.aliases:
                self._aliases[alias] = metadata
            self._aliases[metadata.venue_symbol] = metadata

    @classmethod
    def from_yaml(cls, path: Path) -> "SymbolMetadataRegistry":
        """Load metadata records from a YAML payload."""

        payload = safe_load_path(path) or {}
        entries: Dict[str, SymbolMetadata] = {}

        for symbol, raw in payload.items():
            entries[symbol] = SymbolMetadata(
                symbol=symbol,
                venue_symbol=str(raw["venue_symbol"]),
                price_precision=int(raw["price_precision"]),
                quantity_precision=int(raw["quantity_precision"]),
                lot_size=Decimal(str(raw["lot_size"])),
                min_notional=Decimal(str(raw["min_notional"])),
                max_notional=Decimal(str(raw["max_notional"])),
                aliases=tuple(raw.get("aliases", []) or ()),
            )

        return cls(entries)

    def resolve(self, symbol: str) -> SymbolMetadata:
        """Resolve symbol metadata, supporting legacy aliases."""

        if symbol in self._entries:
            return self._entries[symbol]

        try:
            return self._aliases[symbol]
        except KeyError as exc:
            raise KeyError(f"Unknown symbol or alias: {symbol}") from exc


class Translator:
    """Convert strategy signals into deterministic `OrderIntent`s."""

    def __init__(self, metadata_registry: SymbolMetadataRegistry) -> None:
        self._metadata_registry = metadata_registry

    def build_order_intent(
        self,
        *,
        signal_symbol: str,
        side: OrderSide,
        signal_price: Decimal,
        sizing: SizingInstruction,
        account: Account,
    ) -> OrderIntent:
        """Translate signals into broker-ready order intents."""
        metadata = self._metadata_registry.resolve(signal_symbol)

        # Order of operations is intentional: resolve metadata, round price, round
        # quantity, then apply notional/side validations so the error messages are
        # deterministic and easy to reason about.
        price_step = Decimal("1").scaleb(-metadata.price_precision)
        price = signal_price.quantize(price_step, rounding=ROUND_HALF_UP)

        if sizing.mode != "fixed_notional":
            raise NotImplementedError(f"Sizing mode {sizing.mode} not supported yet")

        raw_quantity = sizing.value / price if price != 0 else Decimal("0")
        lots = (raw_quantity / metadata.lot_size).to_integral_value(rounding=ROUND_DOWN)
        quantity = (lots * metadata.lot_size).quantize(
            Decimal("1").scaleb(-metadata.quantity_precision),
            rounding=ROUND_DOWN,
        )

        if quantity == 0:
            raise ValueError(
                f"Quantity quantized to zero for {metadata.symbol}; lot size is {metadata.lot_size}"
            )

        price_container = Pricing(limit=price)
        notional = (price * quantity).quantize(price_step, rounding=ROUND_HALF_UP)

        if notional < metadata.min_notional:
            raise ValueError(
                f"Notional {notional} for {metadata.symbol} below min notional {metadata.min_notional}"
            )

        if notional > metadata.max_notional:
            raise ValueError(
                f"Notional {notional} for {metadata.symbol} exceeds max notional {metadata.max_notional}"
            )

        return OrderIntent(
            symbol=metadata.symbol,
            side=side,
            quantity=quantity,
            price=price_container,
            notional=notional,
            metadata=metadata,
            sizing=sizing,
        )

    @property
    def metadata_registry(self) -> SymbolMetadataRegistry:
        """Expose the registry for collaborator access (tests/docs)."""

        return self._metadata_registry

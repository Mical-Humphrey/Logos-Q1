"""Strategy signal to order intent translator stub.

Sprint A will replace the placeholders with deterministic quantisation logic
and metadata-driven validation. For now the scaffolding exists so tests can
assert desired behaviour and fail until implementation lands.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Dict

import yaml

from logos.live.types import Account, OrderIntent, OrderSide, Pricing, SizingInstruction, SymbolMetadata


class SymbolMetadataRegistry:
    """Resolve symbol metadata (including aliases) for live trading."""

    def __init__(self, entries: Dict[str, SymbolMetadata]) -> None:
        self._entries = entries

    @classmethod
    def from_yaml(cls, path: Path) -> "SymbolMetadataRegistry":
        """Load metadata records from a YAML payload."""

        raise NotImplementedError("Translator metadata loading not implemented yet")

    def resolve(self, symbol: str) -> SymbolMetadata:
        """Resolve symbol metadata, supporting legacy aliases."""

        raise NotImplementedError("Symbol resolution not implemented yet")


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

        raise NotImplementedError("Order translation not implemented yet")

    @property
    def metadata_registry(self) -> SymbolMetadataRegistry:
        """Expose the registry for collaborator access (tests/docs)."""

        return self._metadata_registry

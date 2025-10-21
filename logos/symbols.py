"""Symbol canonicalization utilities for Logos.

This module centralizes knowledge about supported symbols across asset
classes. It exposes a small API that allows callers to resolve user provided
aliases into canonical identifiers while providing helpful error messages when a
symbol is unknown.

The canonicalization pipeline is intentionally opinionated:

* Crypto and FX symbols are validated against a curated alias map so common
  mistakes (missing separators, wrong suffix) can be detected early.
* Equities are treated as pass-through because the universe is effectively
  unbounded; we still normalize casing for consistency.
* Research/backfill tooling can opt-in to bypass validation so experiments with
  brand new symbols do not block workflows.
"""

from __future__ import annotations

import logging
import os
import threading
from collections import OrderedDict
from functools import lru_cache
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Sequence, Tuple

__all__ = [
    "CanonicalSymbol",
    "UnknownSymbolError",
    "SymbolAssetClassMismatch",
    "canonicalize_symbol",
    "list_known_symbols",
    "clear_symbol_log_cache",
    "configure_symbol_log_dedup",
]


logger = logging.getLogger(__name__)
_LOG_DEDUP_DEFAULT_MAX_KEYS = 10_000


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    token = raw.strip().lower()
    if token in {"0", "false", "no", "off"}:
        return False
    if token in {"1", "true", "yes", "on"}:
        return True
    return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(1, value)


_LOG_DEDUP_ENABLED = _env_flag("LOGOS_LOG_DEDUP_ENABLED", True)
_LOG_DEDUP_MAX_KEYS = _env_int("LOGOS_LOG_DEDUP_MAX_KEYS", _LOG_DEDUP_DEFAULT_MAX_KEYS)


class _LogDedupCache:
    def __init__(self, max_keys: int) -> None:
        self._lock = threading.Lock()
        self._entries: "OrderedDict[Tuple[str, str, str, str], None]" = OrderedDict()
        self._max_keys = max(1, max_keys)

    def configure(self, max_keys: int) -> None:
        limit = max(1, max_keys)
        with self._lock:
            self._max_keys = limit
            while len(self._entries) > limit:
                self._entries.popitem(last=False)

    def check_and_add(self, key: Tuple[str, str, str, str]) -> bool:
        with self._lock:
            if key in self._entries:
                self._entries.move_to_end(key)
                return False
            self._entries[key] = None
            if len(self._entries) > self._max_keys:
                self._entries.popitem(last=False)
            return True

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_SUCCESS_LOG_CACHE = _LogDedupCache(_LOG_DEDUP_MAX_KEYS)


def configure_symbol_log_dedup(
    *, enabled: bool | None = None, max_keys: int | None = None
) -> None:
    global _LOG_DEDUP_ENABLED
    if enabled is not None:
        _LOG_DEDUP_ENABLED = bool(enabled)
    if max_keys is not None:
        _SUCCESS_LOG_CACHE.configure(max_keys)


def clear_symbol_log_cache() -> None:
    _SUCCESS_LOG_CACHE.clear()


def _normalized_input_for_key(
    raw_value: str, asset_class: str, canonical: str | None
) -> str:
    if canonical:
        return canonical.strip().upper()
    token = raw_value.strip().upper().replace(" ", "")
    if asset_class == "crypto":
        return token.replace("_", "-").replace("/", "-")
    if asset_class == "forex":
        base = (
            token.replace("=X", "").replace("-", "").replace("_", "").replace("/", "")
        )
        if not base:
            return "=X"
        return f"{base}=X"
    return token


def _build_success_dedup_key(
    raw_value: str,
    asset_class: str,
    adapter: str | None,
    context: str | None,
    canonical: str | None,
) -> Tuple[str, str, str, str]:
    normalized = _normalized_input_for_key(raw_value, asset_class, canonical)
    adapter_key = (adapter or "").strip().lower()
    context_key = (context or "").strip().lower()
    asset_key = (asset_class or "").strip().lower()
    return (asset_key, normalized, adapter_key, context_key)


def _should_log_success(
    raw_value: str,
    asset_class: str,
    adapter: str | None,
    context: str | None,
    canonical: str | None,
) -> bool:
    if not logger.isEnabledFor(logging.INFO):
        return False
    if not _LOG_DEDUP_ENABLED:
        return True
    key = _build_success_dedup_key(raw_value, asset_class, adapter, context, canonical)
    return _SUCCESS_LOG_CACHE.check_and_add(key)


def _log_event(level: int, event: str, **fields: Any) -> None:
    if not logger.isEnabledFor(level):
        return
    parts: list[str] = [event]
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={value}")
    logger.log(level, " ".join(parts))


@dataclass(frozen=True, slots=True)
class CanonicalSymbol:
    """Resolved symbol metadata."""

    symbol: str
    asset_class: str
    download_symbol: str | None = None
    alias: str | None = None
    ext: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _SymbolEntry:
    symbol: str
    asset_class: str
    aliases: Tuple[str, ...]
    download_symbol: str | None = None
    ext: Dict[str, Any] = field(default_factory=dict)


class UnknownSymbolError(ValueError):
    """Raised when a symbol cannot be canonicalized."""

    def __init__(
        self,
        symbol: str,
        asset_class: str | None,
        suggestions: Sequence[str] | None = None,
        *,
        context: str | None = None,
    ) -> None:
        parts = [f"Unknown symbol '{symbol}'"]
        if asset_class:
            parts.append(f"for asset class '{asset_class}'")
        if context:
            parts.append(f"in context '{context}'")
        message = " ".join(parts)
        if suggestions:
            unique = list(dict.fromkeys(suggestions))
            message = f"{message}. Suggestions: {', '.join(unique)}"
        else:
            message = f"{message}."
        super().__init__(message)
        self.symbol = symbol
        self.asset_class = asset_class
        self.suggestions = list(dict.fromkeys(suggestions or []))
        self.context = context


class SymbolAssetClassMismatch(ValueError):
    """Raised when an alias maps to a different asset class than requested."""

    def __init__(self, symbol: str, requested: str, actual: str) -> None:
        message = f"Symbol '{symbol}' is registered as '{actual}' but '{requested}' was requested."
        super().__init__(message)
        self.symbol = symbol
        self.requested = requested
        self.actual = actual


def _normalize_asset_class(value: str | None) -> str:
    if value is None:
        return "equity"
    token = value.strip().lower()
    if token in {"fx", "forex", "currency", "currencies"}:
        return "forex"
    if token in {"crypto", "cryptocurrency", "digital"}:
        return "crypto"
    if token in {"equity", "equities", "stock", "stocks"}:
        return "equity"
    return token


@lru_cache(maxsize=1024)
def _normalize_alias(value: str) -> str:
    return "".join(ch for ch in value.upper() if ch.isalnum())


REGISTERED_SYMBOLS: Tuple[_SymbolEntry, ...] = (
    _SymbolEntry(
        symbol="BTC-USD",
        asset_class="crypto",
        aliases=("BTC-USD", "BTCUSD", "BTC/USD", "XBTUSD", "btc-usd"),
        download_symbol="BTC-USD",
        ext={"quote": "USD"},
    ),
    _SymbolEntry(
        symbol="ETH-USD",
        asset_class="crypto",
        aliases=("ETH-USD", "ETHUSD", "ETH/USD", "ETHUSDT"),
        download_symbol="ETH-USD",
        ext={"quote": "USD"},
    ),
    _SymbolEntry(
        symbol="SOL-USD",
        asset_class="crypto",
        aliases=("SOL-USD", "SOLUSD", "SOL/USD"),
        download_symbol="SOL-USD",
        ext={"quote": "USD"},
    ),
    _SymbolEntry(
        symbol="EURUSD=X",
        asset_class="forex",
        aliases=("EURUSD=X", "EURUSD", "EUR/USD"),
        download_symbol="EURUSD=X",
        ext={"base": "EUR", "quote": "USD"},
    ),
    _SymbolEntry(
        symbol="GBPUSD=X",
        asset_class="forex",
        aliases=("GBPUSD=X", "GBPUSD", "GBP/USD"),
        download_symbol="GBPUSD=X",
        ext={"base": "GBP", "quote": "USD"},
    ),
    _SymbolEntry(
        symbol="USDJPY=X",
        asset_class="forex",
        aliases=("USDJPY=X", "USDJPY", "USD/JPY"),
        download_symbol="USDJPY=X",
        ext={"base": "USD", "quote": "JPY"},
    ),
)


_ALIAS_LOOKUP: Dict[Tuple[str, str], Tuple[_SymbolEntry, str]] = {}
_ASSET_CANONICAL: Dict[str, List[str]] = {}

for entry in REGISTERED_SYMBOLS:
    asset = entry.asset_class
    _ASSET_CANONICAL.setdefault(asset, []).append(entry.symbol)
    for alias in entry.aliases:
        token = _normalize_alias(alias)
        key = (asset, token)
        if key in _ALIAS_LOOKUP and _ALIAS_LOOKUP[key][0].symbol != entry.symbol:
            existing = _ALIAS_LOOKUP[key][0].symbol
            raise RuntimeError(
                f"Alias collision: '{alias}' maps to both '{existing}' and '{entry.symbol}'"
            )
        _ALIAS_LOOKUP[key] = (entry, alias)

for symbols in _ASSET_CANONICAL.values():
    symbols.sort()


def list_known_symbols(asset_class: str | None = None) -> List[str]:
    """Return sorted canonical symbols for the requested asset class."""

    if asset_class is None:
        seen: Dict[str, None] = {}
        for grouped in _ASSET_CANONICAL.values():
            for symbol in grouped:
                seen.setdefault(symbol, None)
        return sorted(seen.keys())

    asset = _normalize_asset_class(asset_class)
    return list(_ASSET_CANONICAL.get(asset, []))


def canonicalize_symbol(
    symbol: str,
    *,
    asset_class: str | None = None,
    bypass_unknown: bool = False,
    context: str | None = None,
    adapter: str | None = None,
) -> CanonicalSymbol:
    """Return canonical symbol metadata for the provided alias.

    Parameters
    ----------
    symbol:
        User supplied symbol text.
    asset_class:
        Asset class hint. Required for FX/crypto where alias maps can overlap.
    bypass_unknown:
        When true, unknown symbols are returned in a sanitized form instead of
        raising. Intended for research/backfill tooling experimenting with new
        instruments.
    context:
        Optional string describing the caller, used in error messages.
    adapter:
        Optional adapter or exchange name to include in logs. Used to scope the
        deduplication key so independent integrations still log their first
        normalization event.
    """

    if not symbol or not symbol.strip():
        raise UnknownSymbolError(symbol, asset_class, context=context)

    requested_asset = _normalize_asset_class(asset_class)
    raw_value = symbol.strip()
    adapter_token = adapter.strip() if adapter else None

    if requested_asset == "equity":
        canonical = raw_value.upper()
        if _should_log_success(raw_value, "equity", adapter_token, context, canonical):
            _log_event(
                logging.INFO,
                "symbol_normalized",
                input=raw_value,
                canonical=canonical,
                asset="equity",
                adapter=adapter_token,
                source=(context or "unknown"),
            )
        return CanonicalSymbol(
            symbol=canonical,
            asset_class="equity",
            download_symbol=canonical,
            alias=None,
            ext={"source": "pass-through"},
        )

    token = _normalize_alias(raw_value)
    entry_info = _ALIAS_LOOKUP.get((requested_asset, token))
    if entry_info is not None:
        entry, matched_alias = entry_info
        if requested_asset != entry.asset_class:
            raise SymbolAssetClassMismatch(
                raw_value, requested_asset, entry.asset_class
            )
        if _should_log_success(
            raw_value, entry.asset_class, adapter_token, context, entry.symbol
        ):
            _log_event(
                logging.INFO,
                "symbol_normalized",
                input=raw_value,
                canonical=entry.symbol,
                asset=entry.asset_class,
                alias=matched_alias,
                adapter=adapter_token,
                source=(context or "unknown"),
            )
        return CanonicalSymbol(
            symbol=entry.symbol,
            asset_class=entry.asset_class,
            download_symbol=entry.download_symbol or entry.symbol,
            alias=matched_alias,
            ext=dict(entry.ext) if entry.ext else {},
        )

    if bypass_unknown:
        canonical = _sanitize_freeform(raw_value, requested_asset)
        download_symbol = _derive_download_symbol(canonical, requested_asset)
        ext: Dict[str, Any] = {"bypass": True}
        _log_event(
            logging.WARNING,
            "symbol_unknown_bypass",
            input=raw_value,
            canonical=canonical,
            asset=requested_asset,
            source=(context or "unknown"),
            action="warn",
            bypass="true",
        )
        return CanonicalSymbol(
            symbol=canonical,
            asset_class=requested_asset,
            download_symbol=download_symbol,
            alias=None,
            ext=ext,
        )

    suggestions = _suggest_symbols(raw_value, requested_asset)
    suggestion_field = ",".join(suggestions) if suggestions else "none"
    _log_event(
        logging.WARNING,
        "symbol_unknown",
        input=raw_value,
        asset=requested_asset,
        source=(context or "unknown"),
        suggestions=suggestion_field,
        action="fail",
    )
    raise UnknownSymbolError(raw_value, requested_asset, suggestions, context=context)


def _sanitize_freeform(value: str, asset_class: str) -> str:
    token = value.strip().upper()
    if asset_class == "crypto":
        return token.replace(" ", "").replace("_", "-").replace("/", "-")
    if asset_class == "forex":
        clean = (
            token.replace("=X", "").replace("-", "").replace("_", "").replace("/", "")
        )
        if not clean:
            return "=X"
        return f"{clean}=X"
    return token


def _derive_download_symbol(canonical: str, asset_class: str) -> str | None:
    if asset_class == "forex":
        return canonical if canonical.endswith("=X") else f"{canonical}=X"
    return canonical


def _suggest_symbols(value: str, asset_class: str, limit: int = 3) -> List[str]:
    query = value.strip().upper()
    if not query:
        return []

    threshold = 0.4
    scores: Dict[str, float] = {}

    pool = _ASSET_CANONICAL.get(asset_class)
    if not pool:
        pool = [entry.symbol for entry in REGISTERED_SYMBOLS]

    def _maybe_record(candidate: str, target: str) -> None:
        ratio = SequenceMatcher(None, query, target).ratio()
        if ratio < threshold:
            return
        distance = 1.0 - ratio
        best = scores.get(candidate)
        if best is None or distance < best:
            scores[candidate] = distance

    for canonical in pool:
        _maybe_record(canonical, canonical.upper())

    for entry in REGISTERED_SYMBOLS:
        if asset_class and entry.asset_class != asset_class:
            continue
        for alias in entry.aliases:
            _maybe_record(entry.symbol, alias.strip().upper())

    ranked = sorted(
        scores.items(), key=lambda item: (round(item[1], 6), item[0].lower())
    )
    return [symbol for symbol, _ in ranked[:limit]]

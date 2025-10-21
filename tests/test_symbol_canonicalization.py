from __future__ import annotations

import logging
import threading
import time
from typing import Iterator

import pytest

from logos.symbols import (
    canonicalize_symbol,
    clear_symbol_log_cache,
    configure_symbol_log_dedup,
    list_known_symbols,
    UnknownSymbolError,
)


@pytest.fixture(autouse=True)
def reset_symbol_log_cache() -> Iterator[None]:
    configure_symbol_log_dedup(enabled=True, max_keys=10_000)
    clear_symbol_log_cache()
    yield
    configure_symbol_log_dedup(enabled=True, max_keys=10_000)
    clear_symbol_log_cache()


def test_canonicalize_crypto_alias() -> None:
    info = canonicalize_symbol("btc/usd", asset_class="crypto")
    assert info.symbol == "BTC-USD"
    assert info.download_symbol == "BTC-USD"
    assert info.alias is not None
    assert info.alias.replace("/", "-").upper() == "BTC-USD"


@pytest.mark.parametrize(
    "variant",
    [
        "btcusd",
        "BTCUSD",
        "BTC/USD",
        "BTC-USD",
        "btc_usd",
    ],
)
def test_canonicalize_crypto_variant_inputs(variant: str) -> None:
    info = canonicalize_symbol(variant, asset_class="crypto")
    assert info.symbol == "BTC-USD"


def test_canonicalize_forex_alias_adds_suffix() -> None:
    info = canonicalize_symbol("eurusd", asset_class="fx")
    assert info.symbol == "EURUSD=X"
    assert info.download_symbol == "EURUSD=X"


def test_unknown_symbol_surfaces_suggestions() -> None:
    with pytest.raises(UnknownSymbolError) as exc:
        canonicalize_symbol("btc-ussd", asset_class="crypto")
    assert "BTC-USD" in str(exc.value)
    suggestions = exc.value.suggestions
    assert "BTC-USD" in suggestions
    assert suggestions == sorted(suggestions, key=str.lower)


def test_bypass_allows_unknown_forex_symbol() -> None:
    info = canonicalize_symbol("brlusd", asset_class="forex", bypass_unknown=True)
    assert info.symbol == "BRLUSD=X"
    assert info.download_symbol == "BRLUSD=X"
    assert info.ext.get("bypass") is True


def test_list_known_symbols_returns_sorted_catalog() -> None:
    symbols = list_known_symbols("crypto")
    assert symbols == sorted(symbols)
    assert "BTC-USD" in symbols


def test_canonicalize_symbol_idempotent() -> None:
    first = canonicalize_symbol("BTC-USD", asset_class="crypto")
    second = canonicalize_symbol(first.symbol, asset_class="crypto")
    assert second.symbol == first.symbol


@pytest.mark.parametrize(
    "alias",
    ["btcusd", "BTCUSD", "BTC/USD", "BTC-USD", "btc_usd"],
)
def test_canonicalize_symbol_idempotent_for_aliases(alias: str) -> None:
    first = canonicalize_symbol(alias, asset_class="crypto")
    second = canonicalize_symbol(first.symbol, asset_class="crypto")
    assert first.symbol == "BTC-USD"
    assert second.symbol == first.symbol


def test_unknown_symbol_suggestions_are_deterministic() -> None:
    results: list[list[str]] = []
    for _ in range(2):
        with pytest.raises(UnknownSymbolError) as exc:
            canonicalize_symbol("btc-ussd", asset_class="crypto")
        results.append(list(exc.value.suggestions))
    assert results[0] == results[1]


def test_unknown_symbol_suggestions_sorted_case_insensitive() -> None:
    with pytest.raises(UnknownSymbolError) as exc:
        canonicalize_symbol("usd", asset_class="crypto")
    suggestions = exc.value.suggestions
    sorted_copy = sorted(suggestions, key=lambda item: item.lower())
    assert suggestions == sorted_copy


def test_canonicalization_logs_success(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="logos.symbols")
    canonicalize_symbol("BTCUSD", asset_class="crypto", context="unit")
    messages = [record.message for record in caplog.records]
    assert any(
        msg.startswith("symbol_normalized") and "canonical=BTC-USD" in msg
        for msg in messages
    )


def test_canonicalization_logs_unknown(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="logos.symbols")
    with pytest.raises(UnknownSymbolError):
        canonicalize_symbol("btc-ussdd", asset_class="crypto", context="unit")
    messages = [record.message for record in caplog.records]
    assert any(
        msg.startswith("symbol_unknown") and "action=fail" in msg for msg in messages
    )


def test_canonicalization_logs_bypass_warning(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="logos.symbols")
    info = canonicalize_symbol(
        "foobar",
        asset_class="crypto",
        bypass_unknown=True,
        context="research",
    )
    assert info.ext.get("bypass") is True
    messages = [record.message for record in caplog.records]
    assert any(
        msg.startswith("symbol_unknown_bypass") and "action=warn" in msg
        for msg in messages
    )


def test_symbol_log_dedup_suppresses_repeat_and_preserves_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="logos.symbols")
    canonicalize_symbol(
        "BTCUSD",
        asset_class="crypto",
        context="unit.dedup",
        adapter="alpaca",
    )
    canonicalize_symbol(
        "BTC/USD",
        asset_class="crypto",
        context="unit.dedup",
        adapter="alpaca",
    )
    info_messages = [
        record.message
        for record in caplog.records
        if record.levelno == logging.INFO
        and record.message.startswith("symbol_normalized")
    ]
    assert len(info_messages) == 1

    with pytest.raises(UnknownSymbolError):
        canonicalize_symbol(
            "btc-unknown",
            asset_class="crypto",
            context="unit.dedup",
            adapter="alpaca",
        )
    warning_messages = [
        record.message
        for record in caplog.records
        if record.levelno >= logging.WARNING
        and record.message.startswith("symbol_unknown")
    ]
    assert warning_messages


def test_symbol_log_dedup_tracks_adapter_in_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="logos.symbols")
    canonicalize_symbol(
        "BTCUSD",
        asset_class="crypto",
        context="unit.adapters",
        adapter="ccxt",
    )
    canonicalize_symbol(
        "BTCUSD",
        asset_class="crypto",
        context="unit.adapters",
        adapter="alpaca",
    )
    info_messages = [
        record.message
        for record in caplog.records
        if record.levelno == logging.INFO
        and record.message.startswith("symbol_normalized")
    ]
    assert len(info_messages) == 2
    assert any("adapter=ccxt" in msg for msg in info_messages)
    assert any("adapter=alpaca" in msg for msg in info_messages)


def test_symbol_log_dedup_lru_eviction(caplog: pytest.LogCaptureFixture) -> None:
    configure_symbol_log_dedup(max_keys=2)
    clear_symbol_log_cache()
    caplog.set_level(logging.INFO, logger="logos.symbols")

    canonicalize_symbol(
        "BTCUSD",
        asset_class="crypto",
        context="unit.lru",
        adapter="alpaca",
    )
    canonicalize_symbol(
        "ETHUSD",
        asset_class="crypto",
        context="unit.lru",
        adapter="alpaca",
    )
    canonicalize_symbol(
        "SOLUSD",
        asset_class="crypto",
        context="unit.lru",
        adapter="alpaca",
    )
    canonicalize_symbol(
        "BTCUSD",
        asset_class="crypto",
        context="unit.lru",
        adapter="alpaca",
    )

    info_messages = [
        record.message
        for record in caplog.records
        if record.levelno == logging.INFO
        and record.message.startswith("symbol_normalized")
    ]
    btc_messages = [msg for msg in info_messages if "canonical=BTC-USD" in msg]
    assert len(btc_messages) == 2
    assert len(info_messages) == 4


def test_symbol_log_dedup_thread_safety(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="logos.symbols")
    clear_symbol_log_cache()

    def _worker() -> None:
        canonicalize_symbol(
            "BTCUSD",
            asset_class="crypto",
            context="unit.threads",
            adapter="alpaca",
        )

    threads = [threading.Thread(target=_worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    info_messages = [
        record.message
        for record in caplog.records
        if record.levelno == logging.INFO
        and record.message.startswith("symbol_normalized")
    ]
    filtered = [
        msg
        for msg in info_messages
        if "adapter=alpaca" in msg and "source=unit.threads" in msg
    ]
    assert len(filtered) == 1


def test_canonicalization_performance_microbenchmark() -> None:
    start = time.perf_counter()
    for _ in range(5000):
        canonicalize_symbol("BTCUSD", asset_class="crypto")
    duration = time.perf_counter() - start
    assert duration < 0.75

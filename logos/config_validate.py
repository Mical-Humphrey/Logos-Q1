"""Validate environment readiness for Logos live trading."""

from __future__ import annotations

import sys
from typing import List, Tuple

from .config import load_settings
from .paths import (
    APP_LOGS_DIR,
    APP_LOG_FILE,
    DATA_CACHE_DIR,
    RUNS_LIVE_DIR,
    RUNS_LIVE_SESSIONS_DIR,
    RUNS_LIVE_TRADES_DIR,
    ensure_dirs,
)


Check = Tuple[bool, str]


def _check_paths() -> List[Check]:
    ensure_dirs()
    return [
        (APP_LOGS_DIR.exists(), f"log directory exists -> {APP_LOGS_DIR}"),
        (APP_LOG_FILE.parent.exists(), f"app log path parent exists -> {APP_LOG_FILE.parent}"),
        (DATA_CACHE_DIR.exists(), f"data cache directory exists -> {DATA_CACHE_DIR}"),
        (RUNS_LIVE_DIR.exists(), f"live runs directory exists -> {RUNS_LIVE_DIR}"),
        (RUNS_LIVE_SESSIONS_DIR.exists(), f"session directory exists -> {RUNS_LIVE_SESSIONS_DIR}"),
        (RUNS_LIVE_TRADES_DIR.exists(), f"trade archive directory exists -> {RUNS_LIVE_TRADES_DIR}"),
    ]


def _check_broker(settings) -> List[Check]:
    broker = (settings.default_broker or "paper").lower()
    checks: List[Check] = [(True, f"default broker configured -> {broker}")]
    if broker == "ccxt":
        checks.extend(
            [
                (bool(settings.ccxt_exchange), "ccxt exchange configured (CCXT_EXCHANGE)"),
                (bool(settings.ccxt_api_key), "ccxt API key provided (CCXT_API_KEY)"),
                (bool(settings.ccxt_api_secret), "ccxt API secret provided (CCXT_API_SECRET)"),
            ]
        )
    elif broker == "alpaca":
        checks.extend(
            [
                (bool(settings.alpaca_base_url), "Alpaca base URL configured (ALPACA_BASE_URL)"),
                (bool(settings.alpaca_key_id), "Alpaca key configured (ALPACA_KEY_ID)"),
                (bool(settings.alpaca_secret_key), "Alpaca secret configured (ALPACA_SECRET_KEY)"),
            ]
        )
    elif broker in {"ib", "ibkr", "interactive_brokers"}:
        checks.extend(
            [
                (bool(settings.ib_host), "IB host configured (IB_HOST)"),
                (settings.ib_port is not None, "IB port configured (IB_PORT)"),
            ]
        )
    return checks


def _check_mode(settings) -> List[Check]:
    checks: List[Check] = []
    if settings.mode == "live":
        checks.append((True, "MODE=live (live trading enabled)"))
    else:
        checks.append((True, "MODE=paper (live order submission disabled by default)"))
    return checks


def validate_environment() -> int:
    """Run all checks and return process exit code."""

    settings = load_settings()
    results: List[Check] = []
    results.extend(_check_paths())
    results.extend(_check_mode(settings))
    results.extend(_check_broker(settings))

    ok = True
    for passed, message in results:
        prefix = "[ OK ]" if passed else "[FAIL]"
        print(f"{prefix} {message}")
        ok = ok and passed
    return 0 if ok else 1


def main() -> None:
    sys.exit(validate_environment())


if __name__ == "__main__":  # pragma: no cover
    main()

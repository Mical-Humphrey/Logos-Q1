# src/config.py
# =============================================================================
# Purpose:
#   Centralize runtime configuration for the project. Values typically come
#   from a .env file, but we also provide sane defaults so the system runs
#   without extra setup.
#
# Summary:
#   - Defines a Settings dataclass for strongly-typed config
#   - Loads environment variables via python3-dotenv
#   - Exposes load_settings() for consumers (CLI / tests)
#
# Design Notes:
#   - Keep configuration separate from code to ease deployment and testing.
# =============================================================================
from __future__ import annotations
import os
from dataclasses import dataclass
from dotenv import load_dotenv

@dataclass
class Settings:
    """Strongly-typed container for config values."""

    start: str
    end: str
    symbol: str
    log_level: str = "INFO"
    asset_class: str = "equity"
    commission_per_share: float = 0.0035
    slippage_bps: float = 1.0
    mode: str = "paper"
    default_broker: str = "paper"
    default_interval: str = "1m"
    risk_max_dd_bps: float = 500.0
    risk_max_notional: float = 0.0
    risk_max_position: float = 0.0
    ccxt_exchange: str | None = None
    ccxt_api_key: str | None = None
    ccxt_api_secret: str | None = None
    alpaca_key_id: str | None = None
    alpaca_secret_key: str | None = None
    alpaca_base_url: str | None = None
    ib_host: str | None = None
    ib_port: int | None = None

def load_settings() -> Settings:
    """Load environment variables and return a Settings instance.
    
    We call this in the CLI so all downstream modules get consistent settings.
    """
    load_dotenv()
    def _get_float(name: str, default: float) -> float:
        raw = os.getenv(name)
        if raw is None:
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    def _get_int(name: str, default: int | None = None) -> int | None:
        raw = os.getenv(name)
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    return Settings(
        start=os.getenv("START_DATE", "2023-01-01"),
        end=os.getenv("END_DATE", "2025-01-01"),
        symbol=os.getenv("SYMBOL", "MSFT"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        asset_class=os.getenv("DEFAULT_ASSET_CLASS", "equity"),
        commission_per_share=_get_float("DEFAULT_COMMISSION_PER_SHARE", 0.0035),
        slippage_bps=_get_float("DEFAULT_SLIPPAGE_BPS", 1.0),
        mode=os.getenv("MODE", "paper").lower(),
        default_broker=os.getenv("BROKER", "paper").lower(),
        default_interval=os.getenv("INTERVAL", "1m"),
        risk_max_dd_bps=_get_float("RISK_MAX_DD_BPS", 500.0),
        risk_max_notional=_get_float("RISK_MAX_NOTIONAL", 0.0),
        risk_max_position=_get_float("RISK_MAX_POSITION", 0.0),
        ccxt_exchange=os.getenv("CCXT_EXCHANGE"),
        ccxt_api_key=os.getenv("CCXT_API_KEY"),
        ccxt_api_secret=os.getenv("CCXT_API_SECRET"),
        alpaca_key_id=os.getenv("ALPACA_KEY_ID"),
        alpaca_secret_key=os.getenv("ALPACA_SECRET_KEY"),
        alpaca_base_url=os.getenv("ALPACA_BASE_URL"),
        ib_host=os.getenv("IB_HOST"),
        ib_port=_get_int("IB_PORT"),
    )

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

def load_settings() -> Settings:
    """Load environment variables and return a Settings instance.
    
    We call this in the CLI so all downstream modules get consistent settings.
    """
    load_dotenv()
    return Settings(
        start=os.getenv("START_DATE", "2023-01-01"),
        end=os.getenv("END_DATE", "2025-01-01"),
        symbol=os.getenv("SYMBOL", "MSFT"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        asset_class=os.getenv("DEFAULT_ASSET_CLASS", "equity"),
        commission_per_share=float(os.getenv("DEFAULT_COMMISSION_PER_SHARE", "0.0035")),
        slippage_bps=float(os.getenv("DEFAULT_SLIPPAGE_BPS", "1.0")),
    )

# src/data_loader.py
# =============================================================================
# Purpose:
#   Fetch daily OHLCV bars using yfinance, maintain a local CSV cache, and
#   always return a canonical DataFrame with columns:
#     ["Open","High","Low","Close","Adj Close","Volume"]
#
# Summary:
#   - Forces auto_adjust=False (so Adj Close exists reliably)
#   - Flattens MultiIndex columns if present
#   - Merges fresh downloads with cache and de-duplicates by index
#   - Clips to the requested date range before returning
#
# Rationale:
#   - Deterministic schema simplifies downstream code
#   - Local cache avoids re-downloading for iterative research
# =============================================================================
from __future__ import annotations
import logging
import os
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

def _covers_range(df: pd.DataFrame, start: str, end: str) -> bool:
    """Return True if cached df fully covers [start, end]."""
    if df.empty:
        return False
    s, e = pd.to_datetime(start), pd.to_datetime(end)
    return df.index.min() <= s and df.index.max() >= e

def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Some yfinance responses use MultiIndex columns; flatten to single level."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

def get_prices(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Download or load cached OHLCV for 'symbol' in [start, end].
    
    Returns columns: ['Open','High','Low','Close','Adj Close','Volume'].
    """
    os.makedirs("data", exist_ok=True)
    cache = f"data/{symbol}.csv"

    df = None
    if os.path.exists(cache):
        try:
            df = pd.read_csv(cache, parse_dates=["Date"], index_col="Date").sort_index()
        except Exception as ex:
            logger.warning(f"Failed reading cache {cache}: {ex}")

    if df is not None and _covers_range(df, start, end):
        logger.info(f"Using cached data for {symbol}")
    else:
        logger.info(f"Downloading {symbol} from Yahoo Finance")
        new = yf.download(
            symbol, start=start, end=end, auto_adjust=False, actions=False, progress=False
        )
        if new.empty:
            raise RuntimeError(f"No data for {symbol}")
        new.index.name = "Date"
        new = _flatten_columns(new)

        required = ["Open", "High", "Low", "Close", "Volume"]
        missing = [c for c in required if c not in new.columns]
        if missing:
            raise RuntimeError(f"Missing columns from Yahoo response: {missing}")
        if "Adj Close" not in new.columns:
            # If not supplied, mirror Close so downstream code has a consistent schema.
            new["Adj Close"] = new["Close"]

        if df is not None:
            combined = pd.concat([df, new]).sort_index()
            combined = combined[~combined.index.duplicated(keep="last")]
            df = combined
        else:
            df = new

        try:
            df.to_csv(cache)
        except Exception as ex:
            logger.warning(f"Could not write cache: {ex}")

    # Return only the requested range with canonical column order
    df = df.loc[pd.to_datetime(start): pd.to_datetime(end)]
    cols = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
    df = df[cols]
    return df

# src/data_loader.py
# =============================================================================
# Purpose:
#   Fetch OHLCV bars using yfinance with optional intraday intervals, maintain
#   a local CSV cache, and always return a canonical DataFrame with columns:
#   ["Open","High","Low","Close","Adj Close","Volume"] and a DatetimeIndex.
#
# Summary:
#   - Tries native yfinance interval (1d, 1h/60m, 30m, 15m, 10m, 5m)
#   - If not supported natively, downloads daily and resamples logically
#   - Flattens MultiIndex columns if present
#   - Clips to requested date range before return
#
# Notes:
#   - For crypto/FX symbols, Yahoo often supports 1h/1d; we resample when needed.
#   - We keep "Adj Close" consistent; if missing, mirror "Close".
# =============================================================================
from __future__ import annotations
import logging
import os
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

SUPPORTED_NATIVE = {"1d", "60m", "1h", "30m", "15m", "10m", "5m"}

def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

def _ensure_adj_close(df: pd.DataFrame) -> pd.DataFrame:
    if "Adj Close" not in df.columns:
        df["Adj Close"] = df["Close"]
    return df

def _covers_range(df: pd.DataFrame, start: str, end: str) -> bool:
    if df.empty:
        return False
    s, e = pd.to_datetime(start), pd.to_datetime(end)
    return df.index.min() <= s and df.index.max() >= e

def _resample_ohlcv(df: pd.DataFrame, interval: str) -> pd.DataFrame:
    """Resample daily bars to intraday with sane OHLCV aggregation."""
    rule = interval.lower().replace("1h", "60min").replace("m", "min").replace("d", "D")
    ohlc = {
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Adj Close": "last",
        "Volume": "sum",
    }
    out = df.resample(rule).apply(ohlc).dropna(how="any")
    return out

def get_prices(symbol: str, start: str, end: str, interval: str = "1d") -> pd.DataFrame:
    """Download or load cached OHLCV for 'symbol' in [start, end] at 'interval'."""
    os.makedirs("data", exist_ok=True)
    cache = f"data/{symbol.replace('/', '_')}_{interval}.csv"

    df = None
    if os.path.exists(cache):
        try:
            df = pd.read_csv(cache, parse_dates=["Date"], index_col="Date").sort_index()
        except Exception as ex:
            logger.warning(f"Failed reading cache {cache}: {ex}")

    # If cache is stale or missing, download
    need_download = True
    if df is not None and _covers_range(df, start, end):
        need_download = False

    if need_download:
        logger.info(f"Downloading {symbol} [{interval}] from Yahoo Finance")
        yf_ivl = interval if interval in SUPPORTED_NATIVE else "1d"
        new = yf.download(
            symbol,
            start=start,
            end=end,
            interval=yf_ivl,
            auto_adjust=False,
            actions=False,
            progress=False,
        )
        if new.empty:
            raise RuntimeError(f"No data for {symbol} at interval {interval}")
        new.index.name = "Date"
        new = _flatten_columns(new)
        new = _ensure_adj_close(new)

        # If interval unsupported natively, resample from daily
        if interval not in SUPPORTED_NATIVE or yf_ivl != interval:
            new = _resample_ohlcv(new, interval)

        try:
            new.to_csv(cache)
        except Exception as ex:
            logger.warning(f"Could not write cache: {ex}")
        df = new

    # Clip to requested window and enforce canonical column order
    df = df.loc[pd.to_datetime(start): pd.to_datetime(end)]
    cols = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
    df = df[cols]
    return df

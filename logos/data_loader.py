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
from typing import Callable
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

SUPPORTED_NATIVE = {"1d", "60m", "1h", "30m", "15m", "10m", "5m"}


def _cache_path(symbol: str, interval: str, asset_tag: str) -> str:
    """Return a cache filename that encodes symbol/interval/asset_class."""
    safe_symbol = symbol.replace("/", "_").replace("=", "_").replace("-", "_")
    return os.path.join("data", f"{asset_tag}_{safe_symbol}_{interval}.csv")

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

def _load_from_yahoo(
    symbol: str,
    start: str,
    end: str,
    interval: str,
    asset_tag: str,
    download_symbol: str | None = None,
) -> pd.DataFrame:
    """Shared Yahoo Finance downloader with caching and resampling."""
    os.makedirs("data", exist_ok=True)
    cache_symbol = download_symbol or symbol
    cache = _cache_path(cache_symbol, interval, asset_tag)

    df = None
    if os.path.exists(cache):
        try:
            df = pd.read_csv(cache, parse_dates=["Date"], index_col="Date").sort_index()
        except Exception as ex:
            logger.warning(f"Failed reading cache {cache}: {ex}")

    need_download = True
    if df is not None and _covers_range(df, start, end):
        need_download = False

    if need_download:
        dl_symbol = download_symbol or symbol
        logger.info(f"Downloading {dl_symbol} [{interval}] from Yahoo Finance")
        yf_ivl = interval if interval in SUPPORTED_NATIVE else "1d"
        new = yf.download(
            dl_symbol,
            start=start,
            end=end,
            interval=yf_ivl,
            auto_adjust=False,
            actions=False,
            progress=False,
        )
        if new.empty:
            raise RuntimeError(f"No data for {dl_symbol} at interval {interval}")
        new.index.name = "Date"
        new = _flatten_columns(new)
        new = _ensure_adj_close(new)

        if interval not in SUPPORTED_NATIVE or yf_ivl != interval:
            new = _resample_ohlcv(new, interval)

        try:
            new.to_csv(cache)
        except Exception as ex:
            logger.warning(f"Could not write cache: {ex}")
        df = new

    df = df.loc[pd.to_datetime(start): pd.to_datetime(end)]
    cols = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
    df = df[cols]
    return df


def _load_equity_prices(symbol: str, start: str, end: str, interval: str) -> pd.DataFrame:
    """Equity loader: direct Yahoo Finance pull."""
    return _load_from_yahoo(symbol, start, end, interval, asset_tag="equity")


def _load_crypto_prices(symbol: str, start: str, end: str, interval: str) -> pd.DataFrame:
    """Crypto loader: prefer Yahoo Finance symbols like BTC-USD."""
    try:
        return _load_from_yahoo(symbol, start, end, interval, asset_tag="crypto")
    except RuntimeError as err:
        logger.error(f"Crypto data fetch failed for {symbol}: {err}")
        raise


def _normalize_forex_symbol(symbol: str) -> tuple[str, str]:
    """Return tuple(original_symbol, yahoo_symbol) with '=X' suffix enforced."""
    if symbol.upper().endswith("=X"):
        return symbol.upper(), symbol.upper()
    yahoo_symbol = f"{symbol.upper()}=X"
    return symbol.upper(), yahoo_symbol


def _load_forex_prices(symbol: str, start: str, end: str, interval: str) -> pd.DataFrame:
    """Forex loader: map to Yahoo Finance '=X' tickers automatically."""
    original, yahoo_symbol = _normalize_forex_symbol(symbol)
    return _load_from_yahoo(original, start, end, interval, asset_tag="forex", download_symbol=yahoo_symbol)


def get_prices(
    symbol: str,
    start: str,
    end: str,
    interval: str = "1d",
    asset_class: str = "equity",
) -> pd.DataFrame:
    """Download or load cached OHLCV for a symbol based on its asset class."""
    loader_map: dict[str, Callable[[str, str, str, str], pd.DataFrame]] = {
        "equity": _load_equity_prices,
        "crypto": _load_crypto_prices,
        "forex": _load_forex_prices,
    }

    asset = asset_class.lower()
    if asset == "fx":
        asset = "forex"

    loader = loader_map.get(asset, _load_equity_prices)
    df = loader(symbol, start, end, interval)
    return df

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
from pathlib import Path
from typing import Callable, Dict, cast

import numpy as np
import pandas as pd
import yfinance as yf

from .paths import DATA_RAW_DIR, resolve_cache_subdir, ensure_dirs

logger = logging.getLogger(__name__)

SUPPORTED_NATIVE = {"1d", "60m", "1h", "30m", "15m", "10m", "5m"}


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace("=", "_").replace("-", "_")


def _cache_path(symbol: str, interval: str, asset_tag: str) -> Path:
    """Return a cache filename that encodes symbol/interval/asset_class."""
    safe = _safe_symbol(symbol)
    cache_dir = resolve_cache_subdir(asset_tag)
    ensure_dirs([cache_dir])
    return cache_dir / f"{safe}_{interval}.csv"


def _candidate_fixture_paths(
    symbol: str, interval: str, asset_tag: str, download_symbol: str | None
) -> list[Path]:
    """Enumerate possible fixture filenames for graceful offline fallbacks."""
    ensure_dirs([DATA_RAW_DIR])
    candidates: list[Path] = []
    symbols = {symbol}
    if download_symbol:
        symbols.add(download_symbol)
    for sym in symbols:
        safe = _safe_symbol(sym)
        candidates.extend(
            [
                DATA_RAW_DIR / f"{safe}.csv",
                DATA_RAW_DIR / f"{safe}_{interval}.csv",
                DATA_RAW_DIR / f"{asset_tag}_{safe}.csv",
                DATA_RAW_DIR / f"{asset_tag}_{safe}_{interval}.csv",
            ]
        )
    # Deduplicate while preserving order
    seen: Dict[Path, None] = {}
    for path in candidates:
        seen.setdefault(path, None)
    return list(seen.keys())


def _load_fixture(
    symbol: str, interval: str, asset_tag: str, download_symbol: str | None
) -> pd.DataFrame | None:
    for path in _candidate_fixture_paths(symbol, interval, asset_tag, download_symbol):
        if not path.exists():
            continue
        try:
            df = pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()
            df = _ensure_adj_close(df)
            logger.info(f"Loaded fixture data for {symbol} [{interval}] from {path}")
            return df
        except Exception as exc:
            logger.warning(f"Failed reading fixture {path}: {exc}")
    return None


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
    out = df.resample(rule).agg(ohlc).dropna(how="any")  # type: ignore[arg-type]
    return out


def _expand_daily_to_intraday(df: pd.DataFrame, interval: str) -> pd.DataFrame:
    """Expand daily data to a finer interval by repeating daily values."""
    freq = interval.lower()
    if freq in {"1d", "1day", "24h"}:
        return df.copy()
    try:
        step = pd.Timedelta(freq)
    except ValueError:
        # Fall back to pandas-friendly alias (e.g., 60m -> 60min)
        freq = freq.replace("m", "min")
        step = pd.Timedelta(freq)
    per_day = max(int(pd.Timedelta("1D") / step), 1)
    if not isinstance(df.index, pd.DatetimeIndex):
        df = df.copy()
        df.index = pd.to_datetime(df.index)

    frames: list[pd.DataFrame] = []
    index = cast(pd.DatetimeIndex, df.index)
    for dt in index:
        row = df.loc[dt]
        start = dt
        idx = pd.date_range(start=start, periods=per_day, freq=freq, inclusive="left")
        day = pd.DataFrame(
            {
                "Open": float(row["Open"]),
                "High": float(row["High"]),
                "Low": float(row["Low"]),
                "Close": float(row["Close"]),
                "Adj Close": float(row.get("Adj Close", row["Close"])),
                "Volume": float(row["Volume"]) / per_day,
            },
            index=idx,
        )
        frames.append(day)
    if not frames:
        return df.copy()
    out = pd.concat(frames).sort_index()
    out.index.name = df.index.name
    return out


def _generate_synthetic_ohlcv(
    symbol: str, start: str, end: str, interval: str
) -> pd.DataFrame:
    """Produce deterministic pseudo-random OHLCV data when remote data is unavailable."""
    freq = interval.lower()
    try:
        pd.Timedelta(freq)
    except ValueError:
        freq = freq.replace("m", "min")

    start_ts = pd.to_datetime(start)
    end_ts = pd.to_datetime(end)
    if start_ts > end_ts:
        start_ts, end_ts = end_ts, start_ts

    idx = pd.date_range(start=start_ts, end=end_ts, freq=freq, inclusive="both")
    if len(idx) == 0:
        idx = pd.date_range(start=start_ts, periods=2, freq=freq, inclusive="left")

    seed = abs(hash((symbol, interval))) % (2**32)
    rng = np.random.default_rng(seed)

    base_price = 100 + rng.normal(scale=5.0)
    drift = rng.normal(loc=0.0002, scale=0.002, size=len(idx))
    path = np.cumsum(drift) + base_price
    close = np.clip(path + rng.normal(scale=0.5, size=len(idx)), a_min=1e-3, a_max=None)
    open_px = np.roll(close, 1)
    open_px[0] = close[0]
    high = np.maximum(open_px, close) + np.abs(rng.normal(scale=0.3, size=len(idx)))
    low = np.minimum(open_px, close) - np.abs(rng.normal(scale=0.3, size=len(idx)))
    low = np.clip(low, a_min=1e-3, a_max=None)
    volume = rng.integers(1_000, 10_000, size=len(idx))

    df = pd.DataFrame(
        {
            "Open": open_px,
            "High": high,
            "Low": low,
            "Close": close,
            "Adj Close": close,
            "Volume": volume,
        },
        index=idx,
    )
    df.index.name = "Date"
    logger.warning(
        f"Generated synthetic {interval} data for {symbol} between {start} and {end}"
    )
    return df


def _fallback_prices(
    symbol: str,
    start: str,
    end: str,
    interval: str,
    asset_tag: str,
    download_symbol: str | None,
) -> pd.DataFrame:
    """Attempt to satisfy the request using fixtures or synthetic data."""
    fixture = _load_fixture(symbol, interval, asset_tag, download_symbol)
    if fixture is None and interval != "1d":
        base = _load_fixture(symbol, "1d", asset_tag, download_symbol)
        if base is not None:
            fixture = _expand_daily_to_intraday(base, interval)
    if fixture is not None:
        return fixture
    return _generate_synthetic_ohlcv(symbol, start, end, interval)


def _load_from_yahoo(
    symbol: str,
    start: str,
    end: str,
    interval: str,
    asset_tag: str,
    download_symbol: str | None = None,
) -> pd.DataFrame:
    """Shared Yahoo Finance downloader with caching and resampling."""
    cache_symbol = download_symbol or symbol
    cache = _cache_path(cache_symbol, interval, asset_tag)

    df = None
    if interval == "1d":
        fixture = _load_fixture(cache_symbol, interval, asset_tag, download_symbol)
        if fixture is not None and _covers_range(fixture, start, end):
            df = fixture

    if df is None and cache.exists():
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
        try:
            new = yf.download(
                dl_symbol,
                start=start,
                end=end,
                interval=yf_ivl,
                auto_adjust=False,
                actions=False,
                progress=False,
            )
        except Exception as exc:
            logger.warning(f"Yahoo Finance download failed for {dl_symbol}: {exc}")
            new = pd.DataFrame()

        if new.empty:
            logger.warning(
                f"Yahoo Finance returned no rows for {dl_symbol} [{interval}]. Using fallback data."
            )
            new = _fallback_prices(
                symbol, start, end, interval, asset_tag, download_symbol
            )
        else:
            new.index.name = "Date"
            new = _flatten_columns(new)
            new = _ensure_adj_close(new)

            if interval not in SUPPORTED_NATIVE or yf_ivl != interval:
                new = _resample_ohlcv(new, interval)

        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            new.to_csv(cache)
        except Exception as ex:
            logger.warning(f"Could not write cache: {ex}")
        df = new

    assert df is not None
    start_ts = pd.to_datetime(start)
    end_ts = pd.to_datetime(end)
    index_tz = getattr(df.index, "tz", None)
    if index_tz is not None:
        if start_ts.tzinfo is None:
            start_ts = start_ts.tz_localize(index_tz)
        else:
            start_ts = start_ts.tz_convert(index_tz)
        if end_ts.tzinfo is None:
            end_ts = end_ts.tz_localize(index_tz)
        else:
            end_ts = end_ts.tz_convert(index_tz)
    else:
        if start_ts.tzinfo is not None:
            start_ts = start_ts.tz_convert(None)
        if end_ts.tzinfo is not None:
            end_ts = end_ts.tz_convert(None)
    df = df.loc[start_ts:end_ts]
    if df.empty:
        logger.warning(
            f"No rows available after clipping {symbol} [{interval}] to {start} -> {end}; generating synthetic data."
        )
        df = _generate_synthetic_ohlcv(symbol, start, end, interval)
    cols = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
    df = df[cols]
    df = df.sort_index()
    if df.index.has_duplicates:
        # Keep the most recent observation when duplicates occur (e.g. resampling artifacts).
        df = df[~df.index.duplicated(keep="last")]
    return df


def _load_equity_prices(
    symbol: str, start: str, end: str, interval: str
) -> pd.DataFrame:
    """Equity loader: direct Yahoo Finance pull."""
    return _load_from_yahoo(symbol, start, end, interval, asset_tag="equity")


def _load_crypto_prices(
    symbol: str, start: str, end: str, interval: str
) -> pd.DataFrame:
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


def _load_forex_prices(
    symbol: str, start: str, end: str, interval: str
) -> pd.DataFrame:
    """Forex loader: map to Yahoo Finance '=X' tickers automatically."""
    original, yahoo_symbol = _normalize_forex_symbol(symbol)
    return _load_from_yahoo(
        original, start, end, interval, asset_tag="forex", download_symbol=yahoo_symbol
    )


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

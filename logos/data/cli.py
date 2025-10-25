from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from core.io.dirs import ensure_dir

from .. import data_loader
from ..data_loader import get_prices
from ..paths import DATA_CACHE_DIR, safe_slug
from ..window import Window, UTC


def _normalize_interval(interval: str) -> str:
    token = interval.strip()
    if token.endswith("min"):
        return token
    if token.endswith("m") and token[:-1].isdigit():
        return f"{token[:-1]}min"
    if token.endswith("h") and token[:-1].isdigit():
        minutes = int(token[:-1]) * 60
        return f"{minutes}min"
    if token.endswith("d") and token[:-1].isdigit():
        return f"{token[:-1]}D"
    if token.lower() in {"1d", "d"}:
        return "1D"
    return token


def _resample_bars(frame: pd.DataFrame, interval: str) -> pd.DataFrame:
    freq = _normalize_interval(interval)
    ohlc = {
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Adj Close": "last",
        "Volume": "sum",
    }
    return frame.resample(freq).agg(ohlc).dropna(how="any")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic data tooling")
    sub = parser.add_subparsers(dest="command")

    fetch = sub.add_parser("fetch", help="Fetch price data into cache")
    fetch.add_argument("--symbol", required=True)
    fetch.add_argument("--asset-class", default="equity")
    fetch.add_argument("--interval", default="1d")
    fetch.add_argument("--output-interval", default=None)
    fetch.add_argument("--start", required=True)
    fetch.add_argument("--end", required=True)
    fetch.add_argument("--tz", default="UTC")
    fetch.add_argument("--cache-root", type=Path, default=None)
    fetch.add_argument("--output", type=Path, default=None)
    fetch.add_argument("--allow-synthetic", action="store_true")
    fetch.add_argument("--bypass-validation", action="store_true")
    return parser


def _default_output(
    symbol: str, interval: str, asset_class: str, cache_root: Path | None
) -> Path:
    root = cache_root or DATA_CACHE_DIR
    tier = root / asset_class.lower()
    ensure_dir(tier)
    safe = safe_slug(symbol)
    return tier / f"{safe}_{interval}.csv"


def _serialize_metadata(df: pd.DataFrame, extra: dict[str, Any]) -> dict[str, Any]:
    payload = dict(df.attrs.get("logos_price_meta", {}))
    payload.update(extra)
    return payload


def _handle_fetch(args: argparse.Namespace) -> None:
    window = Window.from_bounds(
        start=args.start,
        end=args.end,
        zone=UTC if args.tz.upper() == "UTC" else args.tz,
    )
    df = get_prices(
        args.symbol,
        window,
        interval=args.interval,
        asset_class=args.asset_class,
        allow_synthetic=args.allow_synthetic,
        bypass_symbol_validation=args.bypass_validation,
    )
    output_interval = args.output_interval or args.interval
    # If converting from daily fixtures to an intraday output, expand daily
    # bars deterministically before resampling so we produce sensible
    # intraday OHLCV series instead of empty/aggregated results.
    if output_interval != args.interval:
        if args.interval.lower().endswith("d") and (
            "h" in output_interval or "min" in output_interval
        ):
            df = data_loader._expand_daily_to_intraday(df, output_interval)
        df = _resample_bars(df, output_interval)
    output_path = args.output or _default_output(
        args.symbol, output_interval, args.asset_class, args.cache_root
    )
    ensure_dir(output_path.parent)
    df.to_csv(output_path, index=True)
    metadata = _serialize_metadata(
        df,
        {
            "output_interval": output_interval,
            "source_interval": args.interval,
            "output_path": str(output_path.resolve()),
        },
    )
    meta_path = output_path.with_suffix(".meta.json")
    meta_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"saved {len(df)} rows to {output_path}")


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "fetch":
        _handle_fetch(args)
    else:
        parser.print_help()


if __name__ == "__main__":  # pragma: no cover
    main()

# src/cli.py
# =============================================================================
# Purpose:
#   Command-line interface (CLI) for Logos-Q1.
#   Orchestrates backtests by wiring together configuration, data loading,
#   strategy selection, the simulation engine, and output artifacts.
#
# Summary:
#   - Parses user arguments (symbol, dates, strategy)
#   - NEW: Supports asset classes (equity, crypto, forex) and intervals (1d, 1h, 10m...)
#   - Loads historical data via data_loader.get_prices()
#   - Runs a strategy to generate signals
#   - Calls backtest.engine.run_backtest() with asset-aware costs & annualization
#   - Prints key metrics and saves equity/trades artifacts
#
# Design Philosophy:
#   - Keep CLI thin; business logic lives in modules.
#   - All knobs are arguments; no hidden logic here.
# =============================================================================

from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, Optional, Sequence, cast

import matplotlib.pyplot as plt
import pandas as pd
from zoneinfo import ZoneInfo

from .config import Settings, load_settings
from .logging_setup import setup_app_logging
from .paths import ensure_dirs
from .run_manager import (
    capture_env,
    close_run_context,
    new_run,
    resolve_git_sha,
    save_equity_plot,
    write_config,
    write_metrics,
    write_provenance,
    write_session_markdown,
    write_trades,
)
from .utils import parse_params
from .data_loader import SyntheticDataNotAllowed, get_prices, last_price_metadata
from .window import Window
from .strategies import STRATEGIES
from .backtest.engine import BacktestResult, run_backtest

# Strategy function type alias for registry casts
StrategyFunction = Callable[..., pd.Series]


logger = logging.getLogger(__name__)

ERROR_REQUIRES_WINDOW = "requires either --window or --start/--end"
ERROR_MUTUALLY_EXCLUSIVE = "inputs are mutually exclusive: --window and --start/--end"
ERROR_INVALID_ISO_DURATION = "invalid ISO duration"
ERROR_START_BEFORE_END = "Start date is not before end date"


def _sorted_strategy_names() -> list[str]:
    return sorted(STRATEGIES.keys(), key=str.lower)


def _format_strategy_list() -> str:
    return ",".join(_sorted_strategy_names())


@dataclass
class BacktestValidationResult:
    window: Window
    tz: str
    window_spec: str | None
    env_sources: Dict[str, str]

    @property
    def start(self) -> str:
        return self.window.start_in_label_timezone().date().isoformat()

    @property
    def end(self) -> str:
        return self.window.end_in_label_timezone().date().isoformat()


def _usage_error(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def _resolve_timezone(name: str | None) -> ZoneInfo:
    tz_name = (name or "UTC").strip() or "UTC"
    try:
        return ZoneInfo(tz_name)
    except Exception as exc:  # pragma: no cover - defensive
        _usage_error(
            f"Unknown timezone '{tz_name}'. Provide a valid IANA name (for example UTC or America/New_York)."
        )
        raise exc


def _parse_iso_duration(value: str) -> timedelta:
    token = value.strip().upper()
    pattern = re.compile(r"^P(?:(?P<weeks>\d+)W)?(?:(?P<days>\d+)D)?$")
    match = pattern.match(token)
    if not match:
        _usage_error(f"{ERROR_INVALID_ISO_DURATION}: {value}")
        raise AssertionError("unreachable")
    assert match is not None
    weeks = int(match.group("weeks")) if match.group("weeks") else 0
    days = int(match.group("days")) if match.group("days") else 0
    total_days = weeks * 7 + days
    if total_days <= 0:
        _usage_error(f"{ERROR_INVALID_ISO_DURATION}: {value}")
    return timedelta(days=total_days)


def _parse_date_value(raw: str, tz: ZoneInfo, flag: str) -> datetime:
    text = raw.strip()
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            dt_date = datetime.strptime(text, "%Y-%m-%d")
            dt = dt_date
        except ValueError:
            _usage_error(
                f"Could not parse --{flag} value '{raw}'. Use YYYY-MM-DD or an ISO-8601 timestamp."
            )
    if dt.tzinfo is not None:
        dt = dt.astimezone(tz)
    return dt


def validate_backtest_args(
    args: argparse.Namespace,
    settings: Settings,
    *,
    now: Callable[[ZoneInfo], datetime] | None = None,
) -> BacktestValidationResult:
    tz_name = getattr(args, "tz", "UTC") or "UTC"
    tz = _resolve_timezone(tz_name)
    start_raw = getattr(args, "start", None)
    end_raw = getattr(args, "end", None)
    window_raw = getattr(args, "window", None)
    allow_env = bool(getattr(args, "allow_env_dates", False))

    if window_raw and (start_raw or end_raw):
        _usage_error(ERROR_MUTUALLY_EXCLUSIVE)

    env_sources: Dict[str, str] = {}

    if window_raw:
        duration = _parse_iso_duration(window_raw)
        now_fn = now or (lambda zone: datetime.now(zone))
        end_dt = now_fn(tz)
        end_date = end_dt.date()
        start_date = end_date - duration
        if start_date >= end_date:
            _usage_error(f"{ERROR_START_BEFORE_END}: window={window_raw}")
        try:
            window_obj = Window.from_bounds(start=start_date, end=end_date, zone=tz)
        except ValueError as exc:
            if "ambiguous timezone input" in str(exc).lower():
                _usage_error("ambiguous timezone input")
            raise
        return BacktestValidationResult(
            window=window_obj,
            tz=tz_name,
            window_spec=window_raw,
            env_sources=env_sources,
        )

    if not start_raw or not end_raw:
        if not allow_env:
            _usage_error(
                f"{ERROR_REQUIRES_WINDOW}; pass --allow-env-dates to use START_DATE/END_DATE"
            )
        if not start_raw:
            if not settings.start:
                _usage_error(
                    "START_DATE not found in environment. Provide --start YYYY-MM-DD or set START_DATE in .env."
                )
            start_raw = settings.start
            env_sources["START_DATE"] = settings.start
        if not end_raw:
            if not settings.end:
                _usage_error(
                    "END_DATE not found in environment. Provide --end YYYY-MM-DD or set END_DATE in .env."
                )
            end_raw = settings.end
            env_sources["END_DATE"] = settings.end

    assert start_raw is not None and end_raw is not None
    start_dt = _parse_date_value(start_raw, tz, "start")
    end_dt = _parse_date_value(end_raw, tz, "end")
    try:
        window_obj = Window.from_bounds(start=start_dt, end=end_dt, zone=tz)
    except ValueError as exc:
        if "ambiguous timezone input" in str(exc).lower():
            _usage_error("ambiguous timezone input")
        if "start must be strictly before end" in str(exc).lower():
            _usage_error(f"{ERROR_START_BEFORE_END}: start={start_raw} end={end_raw}")
        raise
    return BacktestValidationResult(
        window=window_obj,
        tz=tz_name,
        window_spec=None,
        env_sources=env_sources,
    )


# -----------------------------------------------------------------------------
# Annualization helpers for different asset classes and bar intervals
# -----------------------------------------------------------------------------
# Base "periods per year" for daily bars by asset class:
BASE_PPY = {"equity": 252, "crypto": 365, "forex": 260}

# How many bars per day for common intraday intervals
BARS_PER_DAY = {
    "1d": 1,
    "60m": 24,
    "1h": 24,
    "30m": 48,
    "15m": 96,
    "10m": 144,
    "5m": 288,
}


def periods_per_year(asset_class: str, interval: str) -> int:
    """Return the appropriate annualization factor for Sharpe/CAGR."""
    asset = asset_class.lower()
    if asset == "fx":
        asset = "forex"
    ivl = interval.lower()
    base = BASE_PPY.get(asset, 252)
    mult = BARS_PER_DAY.get(ivl, 1)
    return base * mult


# -----------------------------------------------------------------------------
# Plotting helper
# -----------------------------------------------------------------------------
def _plot_equity(equity: pd.Series) -> plt.Figure:
    """Render the equity curve and return the Matplotlib figure."""
    fig, ax = plt.subplots(figsize=(10, 4))
    equity.plot(ax=ax, label="Equity Curve")
    ax.set_title("Equity Curve")
    ax.set_xlabel("Date")
    ax.set_ylabel("Equity")
    ax.legend(loc="best")
    fig.tight_layout()
    return fig


# -----------------------------------------------------------------------------
# Backtest command
# -----------------------------------------------------------------------------
def cmd_backtest(args: argparse.Namespace, settings: Settings | None = None) -> None:
    """Run a full backtest with asset-aware costs and interval-aware metrics."""
    s = settings or load_settings()
    setup_app_logging(s.log_level)
    validation = validate_backtest_args(args, s)
    if validation.env_sources:
        start_label = validation.window.start_in_label_timezone().isoformat()
        end_label = validation.window.end_in_label_timezone().isoformat()
        logger.info(
            "Using dates from environment: START=%s, END=%s",
            start_label,
            end_label,
        )

    ensure_dirs()
    logger.info("Starting backtest via CLI")

    # Resolve CLI or .env defaults
    symbol = args.symbol or s.symbol
    window = validation.window
    start = window.start_in_label_timezone().date().isoformat()
    end = window.end_in_label_timezone().date().isoformat()
    tz_name = validation.tz
    window_spec = validation.window_spec
    asset_class = (args.asset_class or s.asset_class).lower()

    allow_synthetic = bool(getattr(args, "allow_synthetic", False))
    if allow_synthetic:
        logger.info("Synthetic data generation permitted via --allow-synthetic flag")

    try:
        df = get_prices(
            symbol,
            window,
            interval=args.interval,
            asset_class=asset_class,
            allow_synthetic=allow_synthetic,
        )
    except SyntheticDataNotAllowed as err:
        _usage_error(str(err))
    price_meta: Dict[str, object] = last_price_metadata() or {}

    run_ctx = new_run(symbol, args.strategy)
    try:
        if args.paper:
            logger.info(
                "Paper trading mode enabled: no live broker interactions will be attempted"
            )

        # Strategy function and params
        strat_func = cast(StrategyFunction, STRATEGIES[args.strategy])
        params = parse_params(args.params)
        signals = strat_func(df, **params) if params else strat_func(df)

        # Compute annualization for metrics (asset + interval)
        ppy = periods_per_year(asset_class, args.interval)

        # Run the engine with asset-aware costs
        res: BacktestResult = run_backtest(
            prices=df,
            signals=signals,
            dollar_per_trade=args.dollar_per_trade,
            slip_bps=args.slip_bps,
            commission_per_share_rate=args.commission,  # equities
            fee_bps=args.fee_bps,  # crypto %
            fx_pip_size=args.fx_pip_size,  # fx pip granularity
            asset_class=asset_class,
            periods_per_year=ppy,
        )

        # Console summary
        print("\n=== Metrics ===")
        for k in ["CAGR", "Sharpe", "MaxDD", "WinRate", "Exposure"]:
            val = res["metrics"].get(k)
            print(f"{k:8s}: {val:.4f}" if isinstance(val, float) else f"{k:8s}: {val}")

        config_payload = {
            "symbol": symbol,
            "strategy": args.strategy,
            "start": start,
            "end": end,
            "tz": tz_name,
            "window": window.to_dict(),
            "asset_class": asset_class,
            "interval": args.interval,
            "dollar_per_trade": args.dollar_per_trade,
            "slip_bps": args.slip_bps,
            "commission_per_share": args.commission,
            "fee_bps": args.fee_bps,
            "fx_pip_size": args.fx_pip_size,
            "params": params or {},
            "paper_mode": bool(args.paper),
            "allow_synthetic": allow_synthetic,
            "data_source": price_meta.get("data_source"),
            "synthetic": bool(price_meta.get("synthetic")),
        }
        if window_spec:
            config_payload["window_spec"] = window_spec
        captured_env = capture_env(
            ["LOGOS_SEED", "YFINANCE_USERNAME", "YFINANCE_PASSWORD"]
        )
        env_payload: Optional[Dict[str, str]] = (
            captured_env if any(captured_env.values()) else None
        )

        seeds = {
            key: value
            for key, value in captured_env.items()
            if key.upper().endswith("SEED") and value
        }
        synthetic_used = bool(price_meta.get("synthetic"))
        data_source_label = str(price_meta.get("data_source") or "unknown")
        fixture_paths = sorted(
            {
                str(item)
                for item in cast(list[str], price_meta.get("fixture_paths") or [])
            }
        )
        cache_paths = sorted(
            {str(item) for item in cast(list[str], price_meta.get("cache_paths") or [])}
        )

        data_details: Dict[str, object] = {
            "source": data_source_label,
            "synthetic": synthetic_used,
        }
        if fixture_paths:
            data_details["fixture_paths"] = fixture_paths
        if cache_paths:
            data_details["cache_paths"] = cache_paths
        download_symbol = price_meta.get("download_symbol")
        if isinstance(download_symbol, str) and download_symbol:
            data_details["download_symbol"] = download_symbol
        resampled_from = price_meta.get("resampled_from")
        if isinstance(resampled_from, str) and resampled_from:
            data_details["resampled_from"] = resampled_from
        synthetic_reason = price_meta.get("synthetic_reason")
        if isinstance(synthetic_reason, str) and synthetic_reason:
            data_details["synthetic_reason"] = synthetic_reason
        generator = price_meta.get("generator")
        if isinstance(generator, str) and generator:
            data_details["generator"] = generator
        row_count = price_meta.get("row_count")
        if isinstance(row_count, int):
            data_details["row_count"] = row_count
        first_ts = price_meta.get("first_timestamp")
        if isinstance(first_ts, str):
            data_details["first_timestamp"] = first_ts
        last_ts = price_meta.get("last_timestamp")
        if isinstance(last_ts, str):
            data_details["last_timestamp"] = last_ts

        window_payload: Dict[str, object] = cast(
            Dict[str, object], dict(window.to_dict())
        )
        if window_spec:
            window_payload["spec"] = window_spec

        cli_args_map: Dict[str, object] = {
            key: getattr(args, key) for key in sorted(vars(args))
        }

        metrics_provenance: Dict[str, object] = {
            "synthetic": synthetic_used,
            "window": window_payload,
            "timezone": window_payload.get("tz", tz_name),
        }
        if seeds:
            metrics_provenance["seeds"] = seeds

        provenance_payload: Dict[str, object] = {
            "run_id": run_ctx.run_id,
            "git_sha": resolve_git_sha() or "unknown",
            "generated_at": datetime.now(ZoneInfo("UTC")).isoformat(),
            "data_source": "synthetic" if synthetic_used else "real",
            "data_details": data_details,
            "window": window_payload,
            "seeds": seeds,
            "cli_args": cli_args_map,
            "env_flags": validation.env_sources,
            "adapter": {"entrypoint": "logos.cli", "mode": "backtest"},
            "allow_synthetic": allow_synthetic,
        }

        write_config(run_ctx, config_payload, env=env_payload)
        write_metrics(run_ctx, res["metrics"], provenance=metrics_provenance)
        write_trades(run_ctx, res["trades"])
        write_provenance(run_ctx, provenance_payload, window=window)

        session_lines = [
            "# SYNTHETIC RUN" if synthetic_used else "# Session Summary",
            "",
            f"- Symbol: `{symbol}`",
            f"- Strategy: `{args.strategy}`",
            f"- Window: {start} → {end} ({tz_name})",
            f"- Data Source: {'SYNTHETIC' if synthetic_used else 'REAL'} ({data_source_label})",
        ]
        if synthetic_used and isinstance(synthetic_reason, str) and synthetic_reason:
            session_lines.append(f"- Synthetic reason: {synthetic_reason}")
        if isinstance(generator, str) and generator:
            session_lines.append(f"- Generator: {generator}")
        if fixture_paths:
            session_lines.append(f"- Fixtures: {', '.join(fixture_paths)}")
        if cache_paths and not synthetic_used:
            session_lines.append(f"- Cache: {', '.join(cache_paths)}")
        write_session_markdown(run_ctx, session_lines)

        print(f"Saved trades -> {run_ctx.trades_file}")

        fig = _plot_equity(res["equity_curve"])
        png_path = save_equity_plot(run_ctx, fig)
        plt.close(fig)
        print(f"Saved equity plot -> {png_path}")
        print(f"Run artifacts -> {run_ctx.run_dir}")

    finally:
        close_run_context(run_ctx)


# -----------------------------------------------------------------------------
# CLI entrypoint
# -----------------------------------------------------------------------------
def build_parser(settings: Settings) -> argparse.ArgumentParser:
    """Construct the CLI parser so shim modules can reuse it."""
    parser = argparse.ArgumentParser(
        prog="Logos-Q1", description="Quant backtesting CLI"
    )
    sub = parser.add_subparsers(dest="command")

    # backtest: main user entry
    p = sub.add_parser("backtest", help="Run a single-symbol backtest")
    p.add_argument(
        "--symbol", required=True, help="Ticker (e.g., MSFT, BTC-USD, EURUSD=X)"
    )
    strategies_help = ", ".join(_sorted_strategy_names())
    p.add_argument(
        "--strategy",
        required=True,
        help=f"Strategy name (valid: {strategies_help})",
    )
    p.add_argument(
        "--start",
        default=None,
        help=(
            "Start date YYYY-MM-DD. Required unless --window is supplied. "
            "Pairs with --end."
        ),
    )
    p.add_argument(
        "--end",
        default=None,
        help=(
            "End date YYYY-MM-DD. Required unless --window is supplied. "
            "Pairs with --start."
        ),
    )
    p.add_argument(
        "--window",
        default=None,
        help=("ISO-8601 duration (e.g., P90D). Mutually exclusive with --start/--end."),
    )
    p.add_argument(
        "--tz",
        default="UTC",
        help="Time zone for window parsing. Accepts IANA names; default UTC.",
    )
    p.add_argument(
        "--allow-env-dates",
        action="store_true",
        help=(
            "Permit fallback to .env START_DATE/END_DATE. Future runs will log when used."
        ),
    )
    p.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="Permit synthetic data generation when fixtures/downloads are unavailable.",
    )

    # NEW: asset class and interval
    p.add_argument(
        "--asset-class",
        choices=["equity", "crypto", "forex"],
        default=settings.asset_class,
        help="Affects costs and metric annualization",
    )
    p.add_argument(
        "--interval", default="1d", help="Bar size: 1d, 1h/60m, 30m, 15m, 10m, 5m"
    )

    # Costs & engine knobs
    p.add_argument(
        "--dollar-per-trade", type=float, default=10_000.0, help="Sizing per trade"
    )
    p.add_argument(
        "--slip-bps",
        type=float,
        default=settings.slippage_bps,
        help="Slippage in basis points per order",
    )
    p.add_argument(
        "--commission",
        type=float,
        default=settings.commission_per_share,
        help="Equity commission $/share",
    )
    p.add_argument(
        "--fee-bps",
        type=float,
        default=5.0,
        help="Crypto maker/taker fee in bps (0.01%% = 1 bps)",
    )
    p.add_argument(
        "--fx-pip-size",
        type=float,
        default=0.0001,
        help="FX pip size (0.0001 for EURUSD, 0.01 for USDJPY)",
    )
    p.add_argument(
        "--params", default=None, help="Comma list 'k=v,k=v' for strategy params"
    )
    p.add_argument(
        "--paper", action="store_true", help="Enable paper trading simulation mode"
    )

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Parse arguments and dispatch to subcommands."""
    settings = load_settings()
    parser = build_parser(settings)
    args = parser.parse_args(argv)

    if args.command == "backtest":
        if getattr(args, "strategy", None) not in STRATEGIES:
            _usage_error(f"valid strategies: {_format_strategy_list()}")
        cmd_backtest(args, settings=settings)
    elif args.command is None and argv is None:
        # User invoked bare CLI with no subcommand; show help
        parser.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

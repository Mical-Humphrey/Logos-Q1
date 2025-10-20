"""Command-line entry point for live trading."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from logos.config import Settings, load_settings
from logos.logging_setup import detach_handler, setup_app_logging
from logos.paths import live_cache_path
from logos.utils import parse_params as parse_param_string

from .broker_base import BrokerAdapter
from .broker_paper import PaperBrokerAdapter
from .broker_ccxt import CCXTBrokerAdapter
from .broker_alpaca import AlpacaBrokerAdapter
from .broker_ib import IBBrokerAdapter
from .data_feed import CsvBarFeed
from .order_sizing import SizingConfig
from .risk import RiskLimits
from .runner import LiveRunner, LoopConfig
from .session_manager import create_session
from .state import load_state, save_state
from .time import SystemTimeProvider
from .strategy_engine import StrategyOrderGenerator, StrategySpec

logger = logging.getLogger(__name__)


def _parse_params(raw: str | None) -> dict:
    if not raw:
        return {}
    raw = raw.strip()
    if raw.startswith("{"):
        return json.loads(raw)
    return parse_param_string(raw)


def _build_broker(args: argparse.Namespace, settings: Settings) -> BrokerAdapter:
    broker_key = (args.broker or settings.default_broker).lower()
    if broker_key == "paper":
        return PaperBrokerAdapter()
    if broker_key == "ccxt":
        if not settings.ccxt_exchange:
            raise SystemExit("CCXT_EXCHANGE must be configured for ccxt broker")
        return CCXTBrokerAdapter(
            exchange=settings.ccxt_exchange,
            api_key=settings.ccxt_api_key,
            api_secret=settings.ccxt_api_secret,
        )
    if broker_key == "alpaca":
        key = settings.alpaca_key_id
        secret = settings.alpaca_secret_key
        base_url = settings.alpaca_base_url or "https://paper-api.alpaca.markets"
        if not key or not secret:
            raise SystemExit("Alpaca credentials missing (ALPACA_KEY_ID / ALPACA_SECRET_KEY)")
        return AlpacaBrokerAdapter(base_url=base_url, key_id=key, secret_key=secret)
    if broker_key in {"ib", "ibkr", "interactive_brokers"}:
        if not settings.ib_host or settings.ib_port is None:
            raise SystemExit("IB_HOST and IB_PORT must be set for Interactive Brokers")
        return IBBrokerAdapter(host=settings.ib_host, port=settings.ib_port)
    raise SystemExit(f"Unknown broker '{broker_key}'")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Logos live trading CLI")
    sub = parser.add_subparsers(dest="command")

    trade = sub.add_parser("trade", help="Run a live/paper trading session")
    trade.add_argument("--symbol", required=True)
    trade.add_argument("--strategy", required=True)
    trade.add_argument("--interval", default="1m")
    trade.add_argument("--asset-class", default=None)
    trade.add_argument("--params", help="Strategy parameters as JSON or key=value pairs")
    trade.add_argument("--live", action="store_true", help="Enable real order submission")
    trade.add_argument("--i-acknowledge-risk", action="store_true", dest="ack")
    trade.add_argument("--broker", default="paper")
    trade.add_argument("--dollar-per-trade", type=float)
    trade.add_argument("--max-notional", type=float)
    trade.add_argument("--kill-switch-file", type=Path)
    trade.add_argument("--risk.max-dd-bps", dest="risk_max_dd", type=float)
    trade.add_argument("--risk.max-position", dest="risk_max_pos", type=float)
    trade.add_argument("--risk.max-rejects", dest="risk_max_rejects", type=int, default=5)
    trade.add_argument("--feed-file", type=Path, help="Optional CSV to tail for live bars")
    trade.add_argument("--max-loops", type=int, help="Stop after N loops (useful for dry runs)")
    trade.add_argument("--log-level", default=None)
    return parser


def _validate_live_flags(args: argparse.Namespace, settings: Settings) -> None:
    if args.live:
        if not args.ack:
            raise SystemExit("--live requires --i-acknowledge-risk")
        if settings.mode != "live":
            raise SystemExit("MODE must be set to 'live' in the environment for live trading")
    if settings.mode == "live" and not args.ack:
        logger.warning("Environment MODE=live but --i-acknowledge-risk not provided; running in paper mode")


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command != "trade":
        parser.print_help()
        return

    settings = load_settings()
    setup_app_logging(args.log_level or settings.log_level)
    _validate_live_flags(args, settings)
    params = _parse_params(args.params)
    if params:
        logger.info("Strategy params: %s", params)

    broker = _build_broker(args, settings)
    asset_class = (args.asset_class or settings.asset_class).lower()
    feed_path = args.feed_file or live_cache_path(asset_class, args.symbol, args.interval)
    time_provider = SystemTimeProvider()
    feed = CsvBarFeed(path=feed_path, time_provider=time_provider)
    session_paths, session_handler = create_session(args.symbol, args.strategy)
    try:
        state = load_state(session_paths.state_file, session_paths.session_id)
        save_state(state, session_paths.state_file)
        dollar_per_trade = args.dollar_per_trade
        if dollar_per_trade is None:
            dollar_per_trade = settings.risk_max_notional or 10_000.0
        sizing = SizingConfig(
            max_notional=args.max_notional if args.max_notional is not None else settings.risk_max_notional,
            max_position=args.risk_max_pos if args.risk_max_pos is not None else settings.risk_max_position,
        )
        strategy_spec = StrategySpec(
            symbol=args.symbol,
            strategy=args.strategy,
            params=params,
            dollar_per_trade=dollar_per_trade,
            sizing=sizing,
        )
        order_generator = StrategyOrderGenerator(broker, strategy_spec)
        risk_limits = RiskLimits(
            max_notional=args.max_notional if args.max_notional is not None else settings.risk_max_notional,
            max_position=args.risk_max_pos if args.risk_max_pos is not None else settings.risk_max_position,
            max_drawdown_bps=args.risk_max_dd if args.risk_max_dd is not None else settings.risk_max_dd_bps,
            max_consecutive_rejects=args.risk_max_rejects,
            kill_switch_file=args.kill_switch_file,
        )
        runner = LiveRunner(
            broker=broker,
            feed=feed,
            order_generator=order_generator.process,
            session=session_paths,
            risk_limits=risk_limits,
            time_provider=time_provider,
            loop_config=LoopConfig(
                symbol=args.symbol,
                strategy=args.strategy,
                interval=args.interval,
                kill_switch_file=str(args.kill_switch_file) if args.kill_switch_file else None,
                max_loops=args.max_loops,
            ),
        )
        runner.run()
    finally:
        detach_handler(session_handler)


if __name__ == "__main__":  # pragma: no cover
    main()

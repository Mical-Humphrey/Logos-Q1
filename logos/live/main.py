"""Command-line entry point for live trading."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict

from logos.config import Settings, load_settings
from logos.logging_setup import detach_handler, setup_app_logging
from logos.paths import live_cache_path
from logos.utils import parse_params as parse_param_string
from logos.utils.paths import safe_resolve
from logos.window import Window, UTC

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

REQUIRED_ACK_PHRASE = "place-live-orders"
_CRITICAL_LIMIT_LABELS = {
    "max_notional": "risk.max_notional",
    "max_position": "risk.max_position",
    "max_drawdown_bps": "risk.max_dd_bps",
    "portfolio_drawdown_cap": "portfolio.drawdown_cap",
    "daily_portfolio_loss_cap": "portfolio.daily_loss_cap",
}


def _parse_params(raw: str | None) -> dict:
    if not raw:
        return {}
    raw = raw.strip()
    if raw.startswith("{"):
        return json.loads(raw)
    return parse_param_string(raw)


def _parse_class_caps_arg(raw: str | None) -> Dict[str, float] | None:
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return {}
    try:
        params = parse_param_string(text)
    except Exception as exc:  # pragma: no cover - defensive
        raise SystemExit(
            "--portfolio-class-caps must be comma-delimited key=value pairs"
        ) from exc
    caps: Dict[str, float] = {}
    for key, value in params.items():
        try:
            caps[str(key).lower()] = float(value)
        except (TypeError, ValueError) as exc:
            raise SystemExit(
                "--portfolio-class-caps values must be numeric (e.g. equity=0.3)"
            ) from exc
    return caps


def _resolve_risk_limits(
    args: argparse.Namespace, settings: Settings
) -> Dict[str, float]:
    def _pick(value: float | None, fallback: float) -> float:
        return float(value) if value is not None else float(fallback)

    return {
        "max_notional": _pick(args.max_notional, settings.risk_max_notional),
        "max_position": _pick(args.risk_max_pos, settings.risk_max_position),
        "max_drawdown_bps": _pick(args.risk_max_dd, settings.risk_max_dd_bps),
        "portfolio_gross_cap": _pick(
            args.portfolio_gross_cap, settings.portfolio_gross_cap
        ),
        "portfolio_per_asset_cap": _pick(
            args.portfolio_asset_cap, settings.portfolio_per_asset_cap
        ),
        "portfolio_per_trade_cap": _pick(
            args.portfolio_per_trade_cap, settings.portfolio_per_trade_cap
        ),
        "portfolio_drawdown_cap": _pick(
            args.portfolio_drawdown_cap, settings.portfolio_drawdown_cap
        ),
        "portfolio_cooldown_days": float(
            args.portfolio_cooldown_days
            if args.portfolio_cooldown_days is not None
            else settings.portfolio_cooldown_days
        ),
        "daily_portfolio_loss_cap": _pick(
            args.portfolio_daily_loss_cap, settings.portfolio_daily_loss_cap
        ),
        "portfolio_strategy_loss_cap": _pick(
            args.portfolio_strategy_loss_cap, settings.portfolio_strategy_loss_cap
        ),
        "portfolio_capacity_warn": _pick(
            args.portfolio_capacity_warn, settings.portfolio_capacity_warn
        ),
        "portfolio_capacity_block": _pick(
            args.portfolio_capacity_block, settings.portfolio_capacity_block
        ),
        "portfolio_turnover_warn": _pick(
            args.portfolio_turnover_warn, settings.portfolio_turnover_warn
        ),
        "portfolio_turnover_block": _pick(
            args.portfolio_turnover_block, settings.portfolio_turnover_block
        ),
        "portfolio_adv_lookback": float(
            args.portfolio_adv_lookback
            if args.portfolio_adv_lookback is not None
            else settings.portfolio_adv_lookback
        ),
    }


def _missing_critical_limits(limits: Dict[str, float]) -> list[str]:
    missing: list[str] = []
    for key, label in _CRITICAL_LIMIT_LABELS.items():
        value = limits.get(key)
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = 0.0
        if numeric <= 0.0:
            missing.append(label)
    return missing


def _format_safety_summary(
    missing_requirements: list[str], missing_limits: list[str]
) -> str:
    lines = ["Safety Summary: live execution blocked"]
    if missing_requirements:
        lines.append("Missing prerequisites:")
        for item in missing_requirements:
            lines.append(f" - {item}")
    if missing_limits:
        lines.append("Missing risk limits:")
        for item in missing_limits:
            lines.append(f" - {item}")
    lines.append("Set the missing values via CLI flags or environment before retrying.")
    return "\n".join(lines)


def _evaluate_live_request(
    args: argparse.Namespace, settings: Settings, limits: Dict[str, float]
) -> tuple[str, bool]:
    env_live = settings.mode.lower() == "live"
    requested_live = bool(args.live)
    ack_phrase = (args.ack_phrase or "").strip()
    if not requested_live:
        if env_live:
            logger.warning(
                "Environment MODE=live but --live flag not provided; defaulting to paper mode"
            )
        if ack_phrase:
            logger.warning(
                "--i-understand provided without --live; ignoring acknowledgement"
            )
        return "paper", False

    missing_prereqs: list[str] = []
    if not env_live:
        missing_prereqs.append("MODE=live environment variable")
    if ack_phrase != REQUIRED_ACK_PHRASE:
        missing_prereqs.append(f'--i-understand "{REQUIRED_ACK_PHRASE}"')

    missing_limits = _missing_critical_limits(limits)
    if missing_prereqs or missing_limits:
        raise SystemExit(_format_safety_summary(missing_prereqs, missing_limits))

    if not args.send_orders:
        logger.warning(
            "Live gating satisfied but --send-orders not provided; running in dry-run mode"
        )
    return "live", bool(args.send_orders)


def _fmt_currency(value: float | None) -> str:
    if value is None or value <= 0:
        return "unset"
    return f"${value:,.0f}"


def _fmt_quantity(value: float | None) -> str:
    if value is None or value <= 0:
        return "unset"
    return f"{value:,.0f}"


def _fmt_bps(value: float | None) -> str:
    if value is None or value <= 0:
        return "unset"
    return f"{value:.0f}bps"


def _fmt_percent(value: float | None) -> str:
    if value is None or value <= 0:
        return "unset"
    return f"{value:.1%}"


def _emit_effective_config_banner(
    settings: Settings,
    *,
    broker: str,
    mode: str,
    send_orders: bool,
    kill_switch_enabled: bool,
    limits: Dict[str, float],
) -> None:
    banner = (
        "Effective Config | "
        f"mode={mode} | "
        f"broker={broker} | "
        f"live_flag={'yes' if mode == 'live' else 'no'} | "
        f"send_orders={'yes' if send_orders else 'no'} | "
        f"kill_switch={'yes' if kill_switch_enabled else 'no'} | "
        f"window={settings.start}->{settings.end} | "
        f"notional_cap={_fmt_currency(limits.get('max_notional'))} | "
        f"position_cap={_fmt_quantity(limits.get('max_position'))} | "
        f"drawdown={_fmt_bps(limits.get('max_drawdown_bps'))} | "
        f"portfolio_dd={_fmt_percent(limits.get('portfolio_drawdown_cap'))} | "
        f"daily_loss={_fmt_percent(limits.get('daily_portfolio_loss_cap'))}"
    )
    logger.info(banner)


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
            raise SystemExit(
                "Alpaca credentials missing (ALPACA_KEY_ID / ALPACA_SECRET_KEY)"
            )
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
    trade.add_argument(
        "--params", help="Strategy parameters as JSON or key=value pairs"
    )
    trade.add_argument("--live", action="store_true", help="Request live trading mode")
    trade.add_argument(
        "--i-understand",
        metavar="PHRASE",
        dest="ack_phrase",
        help='Required phrase "place-live-orders" when using --live',
    )
    trade.add_argument(
        "--send-orders",
        action="store_true",
        help="Dispatch real orders to the configured broker once gating passes",
    )
    trade.add_argument("--broker", default="paper")
    trade.add_argument("--dollar-per-trade", type=float)
    trade.add_argument("--max-notional", type=float)
    trade.add_argument("--kill-switch-file", type=Path)
    trade.add_argument("--risk.max-dd-bps", dest="risk_max_dd", type=float)
    trade.add_argument("--risk.max-position", dest="risk_max_pos", type=float)
    trade.add_argument(
        "--risk.max-rejects", dest="risk_max_rejects", type=int, default=5
    )
    trade.add_argument("--portfolio-gross-cap", type=float)
    trade.add_argument("--portfolio-asset-cap", type=float)
    trade.add_argument(
        "--portfolio-class-caps",
        help="Comma list of asset-class caps (e.g. equity=0.4,crypto=0.2)",
    )
    trade.add_argument("--portfolio-per-trade-cap", type=float)
    trade.add_argument("--portfolio-drawdown-cap", type=float)
    trade.add_argument("--portfolio-cooldown-days", type=int)
    trade.add_argument("--portfolio-daily-loss-cap", type=float)
    trade.add_argument("--portfolio-strategy-loss-cap", type=float)
    trade.add_argument("--portfolio-capacity-warn", type=float)
    trade.add_argument("--portfolio-capacity-block", type=float)
    trade.add_argument("--portfolio-turnover-warn", type=float)
    trade.add_argument("--portfolio-turnover-block", type=float)
    trade.add_argument("--portfolio-adv-lookback", type=int)
    trade.add_argument(
        "--feed-file", type=Path, help="Optional CSV to tail for live bars"
    )
    trade.add_argument(
        "--max-loops", type=int, help="Stop after N loops (useful for dry runs)"
    )
    trade.add_argument("--log-level", default=None)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command != "trade":
        parser.print_help()
        return

    settings = load_settings()
    setup_app_logging(args.log_level or settings.log_level)

    limits = _resolve_risk_limits(args, settings)
    execution_mode, send_orders = _evaluate_live_request(args, settings, limits)

    params = _parse_params(args.params)
    if params:
        logger.info("Strategy params: %s", params)

    asset_class = (args.asset_class or settings.asset_class).lower()
    class_caps_override = _parse_class_caps_arg(args.portfolio_class_caps)
    class_caps = (
        class_caps_override
        if class_caps_override is not None
        else {
            str(k).lower(): float(v) for k, v in settings.portfolio_class_caps.items()
        }
    )
    feed_path = (
        safe_resolve(args.feed_file, description="feed file")
        if args.feed_file
        else live_cache_path(asset_class, args.symbol, args.interval)
    )
    kill_switch_path = (
        safe_resolve(args.kill_switch_file, description="kill switch file")
        if args.kill_switch_file
        else None
    )
    requested_broker = (args.broker or settings.default_broker).lower()
    if execution_mode == "live" and send_orders:
        broker = _build_broker(args, settings)
        effective_broker = requested_broker
    else:
        if requested_broker != "paper":
            logger.info(
                "Broker '%s' requested but running in dry-run mode; using paper adapter",
                requested_broker,
            )
        broker = PaperBrokerAdapter()
        effective_broker = "paper"
        send_orders = False

    _emit_effective_config_banner(
        settings,
        broker=effective_broker,
        mode=execution_mode,
        send_orders=send_orders,
        kill_switch_enabled=kill_switch_path is not None,
        limits=limits,
    )
    time_provider = SystemTimeProvider()
    feed = CsvBarFeed(path=feed_path, time_provider=time_provider)
    session_paths, session_handler = create_session(args.symbol, args.strategy)
    try:
        loop_window = Window.from_bounds(
            start=settings.start,
            end=settings.end,
            zone=UTC,
        )
        state = load_state(session_paths.state_file, session_paths.session_id)
        save_state(state, session_paths.state_file)
        dollar_per_trade = args.dollar_per_trade
        if dollar_per_trade is None:
            base_notional = limits.get("max_notional", 0.0)
            dollar_per_trade = base_notional if base_notional > 0 else 10_000.0
        sizing = SizingConfig(
            max_notional=limits.get("max_notional", 0.0),
            max_position=limits.get("max_position", 0.0),
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
            max_notional=limits.get("max_notional", 0.0),
            max_position=limits.get("max_position", 0.0),
            max_drawdown_bps=limits.get("max_drawdown_bps", 0.0),
            max_consecutive_rejects=args.risk_max_rejects,
            kill_switch_file=kill_switch_path,
            portfolio_gross_cap=limits.get("portfolio_gross_cap", 0.0),
            per_asset_cap=limits.get("portfolio_per_asset_cap", 0.0),
            asset_class_caps=class_caps,
            per_trade_risk_cap=limits.get("portfolio_per_trade_cap", 0.0),
            portfolio_drawdown_cap=limits.get("portfolio_drawdown_cap", 0.0),
            cooldown_days=int(limits.get("portfolio_cooldown_days", 0)),
            daily_portfolio_loss_cap=limits.get("daily_portfolio_loss_cap", 0.0),
            daily_strategy_loss_cap=limits.get("portfolio_strategy_loss_cap", 0.0),
            capacity_warn_participation=limits.get("portfolio_capacity_warn", 0.0),
            capacity_max_participation=limits.get("portfolio_capacity_block", 0.0),
            turnover_warn=limits.get("portfolio_turnover_warn", 0.0),
            turnover_block=limits.get("portfolio_turnover_block", 0.0),
            adv_lookback_days=int(limits.get("portfolio_adv_lookback", 0)),
            symbol_asset_class={args.symbol: asset_class},
            default_asset_class=asset_class,
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
                window=loop_window,
                kill_switch_file=(str(kill_switch_path) if kill_switch_path else None),
                max_loops=args.max_loops,
                orchestrator_time_budget_fraction=settings.orchestrator_time_budget_fraction,
                orchestrator_jitter_seconds=settings.orchestrator_jitter_seconds,
                orchestrator_router_rate_limit=settings.orchestrator_router_rate_limit,
                orchestrator_router_max_inflight=settings.orchestrator_router_max_inflight,
                orchestrator_metrics_window=settings.orchestrator_metrics_window,
                orchestrator_snapshot_interval_s=settings.orchestrator_snapshot_interval_s,
                orchestrator_scheduler_seed=settings.orchestrator_scheduler_seed,
            ),
        )
        runner.run()
    finally:
        detach_handler(session_handler)


if __name__ == "__main__":  # pragma: no cover
    main()

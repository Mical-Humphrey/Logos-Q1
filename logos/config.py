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

import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, Mapping, Tuple, Literal, overload

from dotenv import load_dotenv

_LOGGER = logging.getLogger("logos.config")


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
    portfolio_nav: float = 100_000.0
    portfolio_gross_cap: float = 0.3
    portfolio_per_asset_cap: float = 0.2
    portfolio_class_caps: Dict[str, float] = field(default_factory=dict)
    portfolio_per_trade_cap: float = 0.1
    portfolio_drawdown_cap: float = 0.1
    portfolio_cooldown_days: int = 2
    portfolio_daily_loss_cap: float = 0.05
    portfolio_strategy_loss_cap: float = 0.07
    portfolio_capacity_warn: float = 0.02
    portfolio_capacity_block: float = 0.05
    portfolio_turnover_warn: float = 1.0
    portfolio_turnover_block: float = 1.5
    portfolio_adv_lookback: int = 20
    orchestrator_time_budget_fraction: float = 0.25
    orchestrator_router_rate_limit: int = 5
    orchestrator_router_max_inflight: int = 256
    orchestrator_metrics_window: int = 512
    orchestrator_snapshot_interval_s: int = 30
    orchestrator_jitter_seconds: float = 0.0
    orchestrator_scheduler_seed: int | None = None


@dataclass(frozen=True)
class _FieldSpec:
    env: str
    default: Any
    coerce: Callable[[Any, Any], Tuple[Any, bool]]
    redact: bool = False


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _pick_precedence(
    cli_value: Any, env_value: Any, default_value: Any
) -> Tuple[Any, str]:
    if not _is_missing(cli_value):
        return cli_value, "cli"
    if not _is_missing(env_value):
        return env_value, "env"
    return default_value, "default"


def _str_coercer(
    *, lower: bool = False, upper: bool = False, optional: bool = False
) -> Callable[[Any, Any], Tuple[str | None, bool]]:
    def _inner(value: Any, default: Any) -> Tuple[str | None, bool]:
        if value is None:
            if optional:
                return (default if default is not None else None, True)
            return default, False
        text = str(value).strip()
        if text == "":
            if optional:
                return (
                    None if default is None else default,
                    True if default is None else False,
                )
            return default, False
        if lower:
            text = text.lower()
        if upper:
            text = text.upper()
        return text, True

    return _inner


def _float_coercer(value: Any, default: Any) -> Tuple[float, bool]:
    if value is None:
        return float(default), False
    token = value
    if isinstance(token, str):
        token = token.strip()
        if token == "":
            return float(default), False
    try:
        return float(token), True
    except (TypeError, ValueError):
        return float(default), False


def _optional_int_coercer(value: Any, default: Any) -> Tuple[int | None, bool]:
    if value is None:
        return (default if default is not None else None), True
    token = value
    if isinstance(token, str):
        token = token.strip()
        if token == "":
            return (None if default is None else default), (
                True if default is None else False
            )
    try:
        return int(token), True
    except (TypeError, ValueError):
        return default, False


def _mapping_float_coercer(value: Any, default: Any) -> Tuple[Dict[str, float], bool]:
    base: Dict[str, float] = dict(default or {})
    if value is None:
        return base, False
    if isinstance(value, Mapping):
        try:
            return ({str(k).lower(): float(v) for k, v in value.items()}, True)
        except (TypeError, ValueError):
            return base, False
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}, True
        mapping: Dict[str, float] = {}
        parts = [segment.strip() for segment in text.split(",") if segment.strip()]
        for part in parts:
            key, _, raw_val = part.partition("=")
            key = key.strip().lower()
            if not key or not raw_val:
                return base, False
            try:
                mapping[key] = float(raw_val)
            except ValueError:
                return base, False
        return mapping, True
    return base, False


def _int_coercer(value: Any, default: Any) -> Tuple[int, bool]:
    if value is None:
        return int(default), False
    token = value
    if isinstance(token, str):
        token = token.strip()
        if token == "":
            return int(default), False
    try:
        return int(token), True
    except (TypeError, ValueError):
        return int(default), False


_FIELD_SPECS: Dict[str, _FieldSpec] = {
    "start": _FieldSpec("START_DATE", "2023-01-01", _str_coercer()),
    "end": _FieldSpec("END_DATE", "2025-01-01", _str_coercer()),
    "symbol": _FieldSpec("SYMBOL", "MSFT", _str_coercer()),
    "log_level": _FieldSpec("LOG_LEVEL", "INFO", _str_coercer(upper=True)),
    "asset_class": _FieldSpec(
        "DEFAULT_ASSET_CLASS", "equity", _str_coercer(lower=True)
    ),
    "commission_per_share": _FieldSpec(
        "DEFAULT_COMMISSION_PER_SHARE", 0.0035, _float_coercer
    ),
    "slippage_bps": _FieldSpec("DEFAULT_SLIPPAGE_BPS", 1.0, _float_coercer),
    "mode": _FieldSpec("MODE", "paper", _str_coercer(lower=True)),
    "default_broker": _FieldSpec("BROKER", "paper", _str_coercer(lower=True)),
    "default_interval": _FieldSpec("INTERVAL", "1m", _str_coercer()),
    "risk_max_dd_bps": _FieldSpec("RISK_MAX_DD_BPS", 500.0, _float_coercer),
    "risk_max_notional": _FieldSpec("RISK_MAX_NOTIONAL", 0.0, _float_coercer),
    "risk_max_position": _FieldSpec("RISK_MAX_POSITION", 0.0, _float_coercer),
    "ccxt_exchange": _FieldSpec("CCXT_EXCHANGE", None, _str_coercer(optional=True)),
    "ccxt_api_key": _FieldSpec(
        "CCXT_API_KEY", None, _str_coercer(optional=True), redact=True
    ),
    "ccxt_api_secret": _FieldSpec(
        "CCXT_API_SECRET", None, _str_coercer(optional=True), redact=True
    ),
    "alpaca_key_id": _FieldSpec(
        "ALPACA_KEY_ID", None, _str_coercer(optional=True), redact=True
    ),
    "alpaca_secret_key": _FieldSpec(
        "ALPACA_SECRET_KEY", None, _str_coercer(optional=True), redact=True
    ),
    "alpaca_base_url": _FieldSpec("ALPACA_BASE_URL", None, _str_coercer(optional=True)),
    "ib_host": _FieldSpec("IB_HOST", None, _str_coercer(optional=True)),
    "ib_port": _FieldSpec("IB_PORT", None, _optional_int_coercer),
    "portfolio_nav": _FieldSpec("PORTFOLIO_NAV", 100_000.0, _float_coercer),
    "portfolio_gross_cap": _FieldSpec("PORTFOLIO_GROSS_CAP", 0.3, _float_coercer),
    "portfolio_per_asset_cap": _FieldSpec(
        "PORTFOLIO_PER_ASSET_CAP", 0.2, _float_coercer
    ),
    "portfolio_class_caps": _FieldSpec(
        "PORTFOLIO_CLASS_CAPS", {}, _mapping_float_coercer
    ),
    "portfolio_per_trade_cap": _FieldSpec(
        "PORTFOLIO_PER_TRADE_CAP", 0.1, _float_coercer
    ),
    "portfolio_drawdown_cap": _FieldSpec("PORTFOLIO_DRAWDOWN_CAP", 0.1, _float_coercer),
    "portfolio_cooldown_days": _FieldSpec(
        "PORTFOLIO_COOLDOWN_DAYS", 2, _optional_int_coercer
    ),
    "portfolio_daily_loss_cap": _FieldSpec(
        "PORTFOLIO_DAILY_LOSS_CAP", 0.05, _float_coercer
    ),
    "portfolio_strategy_loss_cap": _FieldSpec(
        "PORTFOLIO_STRATEGY_LOSS_CAP", 0.07, _float_coercer
    ),
    "portfolio_capacity_warn": _FieldSpec(
        "PORTFOLIO_CAPACITY_WARN", 0.02, _float_coercer
    ),
    "portfolio_capacity_block": _FieldSpec(
        "PORTFOLIO_CAPACITY_BLOCK", 0.05, _float_coercer
    ),
    "portfolio_turnover_warn": _FieldSpec(
        "PORTFOLIO_TURNOVER_WARN", 1.0, _float_coercer
    ),
    "portfolio_turnover_block": _FieldSpec(
        "PORTFOLIO_TURNOVER_BLOCK", 1.5, _float_coercer
    ),
    "portfolio_adv_lookback": _FieldSpec(
        "PORTFOLIO_ADV_LOOKBACK", 20, _optional_int_coercer
    ),
    "orchestrator_time_budget_fraction": _FieldSpec(
        "ORCH_TIME_BUDGET_FRACTION", 0.25, _float_coercer
    ),
    "orchestrator_router_rate_limit": _FieldSpec(
        "ORCH_ROUTER_RATE_LIMIT", 5, _int_coercer
    ),
    "orchestrator_router_max_inflight": _FieldSpec(
        "ORCH_ROUTER_MAX_INFLIGHT", 256, _int_coercer
    ),
    "orchestrator_metrics_window": _FieldSpec("ORCH_METRICS_WINDOW", 512, _int_coercer),
    "orchestrator_snapshot_interval_s": _FieldSpec(
        "ORCH_SNAPSHOT_INTERVAL_S", 30, _int_coercer
    ),
    "orchestrator_jitter_seconds": _FieldSpec(
        "ORCH_JITTER_SECONDS", 0.0, _float_coercer
    ),
    "orchestrator_scheduler_seed": _FieldSpec(
        "ORCH_SCHEDULER_SEED", None, _optional_int_coercer
    ),
}


@overload
def load_settings(
    *,
    cli_overrides: Mapping[str, Any] | None = None,
    env_policy: Mapping[str, bool] | None = None,
    include_sources: Literal[True],
    logger: logging.Logger | None = None,
    base_settings: Settings | None = None,
) -> Tuple[Settings, Dict[str, str]]: ...


@overload
def load_settings(
    *,
    cli_overrides: Mapping[str, Any] | None = None,
    env_policy: Mapping[str, bool] | None = None,
    include_sources: Literal[False] = False,
    logger: logging.Logger | None = None,
    base_settings: Settings | None = None,
) -> Settings: ...


def load_settings(
    *,
    cli_overrides: Mapping[str, Any] | None = None,
    env_policy: Mapping[str, bool] | None = None,
    include_sources: bool = False,
    logger: logging.Logger | None = None,
    base_settings: Settings | None = None,
) -> Settings | Tuple[Settings, Dict[str, str]]:
    """Resolve settings with deterministic precedence and logging.

    The precedence order is CLI overrides > environment (when permitted) > defaults.
    When ``include_sources`` is true, the function returns a tuple of
    ``(Settings, sources)`` where *sources* maps field names to
    ``{"cli" | "env" | "default"}`` to aid diagnostics.
    """

    load_dotenv()

    overrides = {
        key: value for key, value in (cli_overrides or {}).items() if value is not None
    }
    env_policy_map = {key: bool(value) for key, value in (env_policy or {}).items()}
    base_defaults: Dict[str, Any] = (
        asdict(base_settings) if base_settings is not None else {}
    )

    log = logger or _LOGGER
    resolved: Dict[str, Any] = {}
    sources: Dict[str, str] = {}

    for field_name, spec in _FIELD_SPECS.items():
        default_value = base_defaults.get(field_name, spec.default)
        cli_value = overrides.get(field_name)
        allow_env = env_policy_map.get(field_name, True)
        env_value = os.getenv(spec.env) if allow_env else None

        raw_value, source = _pick_precedence(cli_value, env_value, default_value)
        coerced, ok = spec.coerce(raw_value, default_value)
        if not ok:
            if source != "default":
                log.warning(
                    "config_invalid_value key=%s source=%s fallback=%s",
                    field_name,
                    source,
                    default_value,
                )
            coerced = default_value
            source = "default"

        display = "***" if spec.redact and coerced not in (None, "") else coerced
        log.info(
            "config_resolved key=%s value=%s source=%s", field_name, display, source
        )

        resolved[field_name] = coerced
        sources[field_name] = source

    settings = Settings(**resolved)
    if include_sources:
        return settings, sources
    return settings

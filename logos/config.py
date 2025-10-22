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
from dataclasses import asdict, dataclass
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

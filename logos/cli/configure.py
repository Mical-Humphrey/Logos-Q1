from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict

from ..config import Settings

from .common import (
    DEFAULT_ENV_PATH,
    load_env,
    resolve_offline_flag,
    write_env,
)

PROMPTS = (
    ("symbol", "Trading symbol or pair", "BTC-USD"),
    ("asset_class", "Asset class (equity/crypto/forex)", "crypto"),
    ("interval", "Default interval", "1m"),
    ("exchange", "Default exchange/venue", "demo"),
    ("risk_notional", "Max per-trade notional (USD)", "5000"),
    ("risk_drawdown", "Max drawdown (bps)", "1000"),
)

CLI_DEFAULTS = {
    "symbol": None,
    "asset_class": None,
    "interval": None,
    "exchange": None,
    "risk_notional": None,
    "risk_drawdown": None,
}


def register(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    settings: Settings | None = None,
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "configure",
        help="Interactive wizard to populate .env with sensible defaults",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Also set LOGOS_OFFLINE_ONLY=1",
    )
    parser.add_argument(
        "--env-path",
        type=Path,
        default=DEFAULT_ENV_PATH,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    for key in CLI_DEFAULTS:
        parser.add_argument(f"--{key.replace('_', '-')}", default=None, help=argparse.SUPPRESS)
    return parser


def _prompt(prompt: str, default: str) -> str:
    response = input(f"{prompt} [{default}]: ").strip()
    return response or default


def _select_values(
    args: argparse.Namespace,
    *,
    defaults: Dict[str, str],
) -> Dict[str, str]:
    answers: Dict[str, str] = {}
    for key, label, fallback in PROMPTS:
        cli_value = getattr(args, key, None)
        base_default = defaults.get(key, fallback)
        if args.non_interactive:
            answers[key] = str(cli_value or base_default)
            continue
        answers[key] = _prompt(label, str(base_default))
    return answers


def _merge_defaults(env_values: Dict[str, str]) -> Dict[str, str]:
    defaults = {
        "symbol": env_values.get("SYMBOL", "BTC-USD"),
        "asset_class": env_values.get("DEFAULT_ASSET_CLASS", "crypto"),
        "interval": env_values.get("INTERVAL", "1m"),
        "exchange": env_values.get("CCXT_EXCHANGE", "demo"),
        "risk_notional": env_values.get("RISK_MAX_NOTIONAL", "5000"),
        "risk_drawdown": env_values.get("RISK_MAX_DD_BPS", "1000"),
    }
    return defaults


def run(args: argparse.Namespace, *, settings: Settings | None = None) -> int:
    env_path = Path(getattr(args, "env_path", DEFAULT_ENV_PATH)).resolve()
    env_values = load_env(env_path)
    defaults = _merge_defaults(env_values)
    answers = _select_values(args, defaults=defaults)

    updated = dict(env_values)
    updated["SYMBOL"] = answers["symbol"].strip()
    updated["DEFAULT_ASSET_CLASS"] = answers["asset_class"].strip().lower()
    updated["INTERVAL"] = answers["interval"].strip()
    updated["CCXT_EXCHANGE"] = answers["exchange"].strip()
    updated["RISK_MAX_NOTIONAL"] = str(answers["risk_notional"]).strip()
    updated["RISK_MAX_DD_BPS"] = str(answers["risk_drawdown"]).strip()

    if resolve_offline_flag(getattr(args, "offline", False)):
        updated["LOGOS_OFFLINE_ONLY"] = "1"

    write_env(updated, path=env_path)

    print("Configuration saved to", env_path)
    print(f"  SYMBOL               = {updated['SYMBOL']}")
    print(f"  DEFAULT_ASSET_CLASS  = {updated['DEFAULT_ASSET_CLASS']}")
    print(f"  INTERVAL             = {updated['INTERVAL']}")
    print(f"  CCXT_EXCHANGE        = {updated['CCXT_EXCHANGE']}")
    print(f"  RISK_MAX_NOTIONAL    = {updated['RISK_MAX_NOTIONAL']}")
    print(f"  RISK_MAX_DD_BPS      = {updated['RISK_MAX_DD_BPS']}")
    if "LOGOS_OFFLINE_ONLY" in updated:
        print(f"  LOGOS_OFFLINE_ONLY   = {updated['LOGOS_OFFLINE_ONLY']}")

    return 0

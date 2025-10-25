from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import pandas as pd

from core.io.atomic_write import atomic_write_text
from core.io.dirs import ensure_dir

from ..paths import (
    RUNS_LIVE_LATEST_LINK,
    RUNS_LIVE_SESSIONS_DIR,
    env_seed,
)
from ..strategies.mean_reversion import generate_signals
from ..strategies.mean_reversion import explain as explain_mean_reversion
from ..config import Settings
from ..window import Window
from ..utils.data_hygiene import ensure_no_object_dtype, require_datetime_index

from ..live.data_feed import FixtureReplayFeed
from ..live.time import MockTimeProvider
from ..live.persistence import (
    prepare_seeded_run_paths,
    write_equity_and_metrics,
    write_snapshot,
)

from .common import (
    DEFAULT_ENV_PATH,
    PROJECT_ROOT,
    load_env,
    resolve_offline_flag,
    update_symlink,
    write_env,
)

DEFAULT_SYMBOL = "BTC-USD"
DEFAULT_ASSET_CLASS = "crypto"
DEFAULT_INTERVAL = "1m"
DEFAULT_LOOKBACK = 5
DEFAULT_Z_ENTRY = 1.5
DEFAULT_NOTIONAL = 1_000.0
DEFAULT_FEE_BPS = 5.0
DEFAULT_STARTING_CASH = 100_000.0
DEFAULT_LABEL_PREFIX = "quickstart"
DEFAULT_MAX_AGE_SECONDS = 86400.0

DEFAULT_FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "live" / "quickstart_btc"
BARS_FILENAME = "bars.csv"
ACCOUNT_FILENAME = "account.json"


def _relative_to_project(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path.resolve())


def register(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    settings: Settings | None = None,
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "quickstart",
        help="Run the deterministic quickstart paper session (offline)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Force offline mode (overrides LOGOS_OFFLINE_ONLY).",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=DEFAULT_LOOKBACK,
        help="Rolling window for mean reversion (default: 5).",
    )
    parser.add_argument(
        "--z-entry",
        type=float,
        default=DEFAULT_Z_ENTRY,
        help="Z-score threshold for entries (default: 1.5).",
    )
    parser.add_argument(
        "--notional",
        type=float,
        default=DEFAULT_NOTIONAL,
        help="Dollar notional per trade (default: 1000).",
    )
    parser.add_argument(
        "--fee-bps",
        type=float,
        default=DEFAULT_FEE_BPS,
        help="Fee in basis points applied per trade (default: 5 bps).",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--env-path",
        type=Path,
        default=DEFAULT_ENV_PATH,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--skip-env",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help=argparse.SUPPRESS,
    )
    return parser


def _load_fixture_dir(path: Path | None) -> Path:
    directory = (path or DEFAULT_FIXTURE_DIR).resolve()
    if not directory.exists():
        raise SystemExit(f"quickstart fixture directory missing at {directory}")
    bars = directory / BARS_FILENAME
    if not bars.exists():
        raise SystemExit(f"bars.csv missing in {directory}")
    account = directory / ACCOUNT_FILENAME
    if not account.exists():
        raise SystemExit(f"account.json missing in {directory}")
    return directory


def _default_symbol(
    settings: Settings | None, env_values: Dict[str, str]
) -> Tuple[str, str, str]:
    symbol = DEFAULT_SYMBOL
    asset_class = DEFAULT_ASSET_CLASS
    interval = DEFAULT_INTERVAL
    if "SYMBOL" in env_values:
        symbol = env_values["SYMBOL"].strip() or symbol
    if "DEFAULT_ASSET_CLASS" in env_values:
        asset_class = env_values["DEFAULT_ASSET_CLASS"].strip().lower() or asset_class
    if "INTERVAL" in env_values:
        interval = env_values["INTERVAL"].strip() or interval
    if settings is not None:
        if getattr(settings, "symbol", "") and settings.symbol != "MSFT":
            symbol = settings.symbol
        if getattr(settings, "asset_class", "") and settings.asset_class != "equity":
            asset_class = settings.asset_class
        if getattr(settings, "default_interval", ""):
            interval = settings.default_interval
    return symbol, asset_class, interval


def _resolve_seed(cli_seed: int | None) -> int:
    if cli_seed is not None:
        return cli_seed
    return env_seed(default=7)


def _infer_window(index: pd.DatetimeIndex) -> Window:
    start_dt = index[0].to_pydatetime()
    end_dt = index[-1].to_pydatetime() + timedelta(days=1)
    return Window.from_bounds(start=start_dt, end=end_dt, zone=timezone.utc)


def _bars_dataframe(
    bars: Sequence[Tuple[datetime, float, float, float, float, float]],
) -> pd.DataFrame:
    df = pd.DataFrame(
        bars,
        columns=["dt", "Open", "High", "Low", "Close", "Volume"],
    ).set_index("dt")
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    else:
        idx = idx.tz_convert("UTC")
    df.index = idx
    require_datetime_index(df, context="quickstart.bars_df")
    ensure_no_object_dtype(df, context="quickstart.bars_df")
    return df


def _fetch_bars(
    symbol: str, fixture_dir: Path
) -> Tuple[pd.DataFrame, List[Dict[str, object]]]:
    bars_path = fixture_dir / BARS_FILENAME
    raw = pd.read_csv(bars_path, parse_dates=["dt"])  # type: ignore[arg-type]
    raw = raw[raw["symbol"] == symbol]
    if raw.empty:
        available = sorted(
            set(str(token) for token in pd.read_csv(bars_path)["symbol"].unique())
        )
        raise SystemExit(
            f"fixture {bars_path} has no rows for symbol {symbol}. Available: {', '.join(available)}"
        )
    raw["dt"] = pd.to_datetime(raw["dt"], utc=True)
    raw = raw.sort_values("dt")
    last_dt = raw["dt"].iloc[-1].to_pydatetime()
    clock = MockTimeProvider(current=last_dt + timedelta(minutes=1))
    feed = FixtureReplayFeed(
        dataset=bars_path,
        time_provider=clock,
        max_age_seconds=DEFAULT_MAX_AGE_SECONDS,
    )
    fetched = feed.fetch_bars(symbol, "1m", since=None)
    rows = [
        (
            bar.dt,
            bar.open,
            bar.high,
            bar.low,
            bar.close,
            bar.volume,
        )
        for bar in fetched
    ]
    df = _bars_dataframe(rows)
    metadata = [
        {
            "ts": bar.dt.isoformat(),
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        for bar in fetched
    ]
    return df, metadata


def _load_account(fixture_dir: Path) -> Dict[str, float]:
    account_path = fixture_dir / ACCOUNT_FILENAME
    payload = json.loads(account_path.read_text(encoding="utf-8"))
    return {
        "cash": float(payload.get("cash", DEFAULT_STARTING_CASH)),
        "equity": float(payload.get("equity", DEFAULT_STARTING_CASH)),
    }


def _simulate_session(
    df: pd.DataFrame,
    signals: pd.Series,
    *,
    symbol: str,
    notional: float,
    fee_bps: float,
    starting_cash: float,
) -> Tuple[
    List[Dict[str, object]],
    List[float],
    List[Dict[str, object]],
    List[Dict[str, object]],
    Dict[str, float],
    Dict[str, Dict[str, float]],
]:
    require_datetime_index(df, context="quickstart.simulation")
    ensure_no_object_dtype(df, context="quickstart.simulation")
    signals = signals.reindex(df.index).fillna(0).astype(int)

    cash = float(starting_cash)
    position_qty = 0.0
    avg_price = 0.0
    cost_basis = 0.0
    realized_pnl = 0.0

    equity_rows: List[Dict[str, object]] = []
    exposures: List[float] = []
    fills: List[Dict[str, object]] = []
    trades: List[Dict[str, object]] = []

    fee_rate = fee_bps / 10_000.0
    fill_id = 1

    for ts, row in df.iterrows():
        price = float(row["Close"])
        signal = int(signals.loc[ts])
        target_quantity = (notional / price) * signal
        delta = target_quantity - position_qty
        if abs(delta) > 1e-6:
            side = "buy" if delta > 0 else "sell"
            qty = abs(delta)
            fee = price * qty * fee_rate
            notional_value = price * qty
            signed_qty = qty if side == "buy" else -qty
            if side == "buy":
                cash -= notional_value + fee
                position_qty += qty
                cost_basis += notional_value + fee
            else:
                cash += notional_value - fee
                position_qty -= qty
                realized_component = (price - avg_price) * qty
                realized_pnl += realized_component - fee
                cost_basis -= avg_price * qty
                if cost_basis < 0 and abs(cost_basis) < 1e-6:
                    cost_basis = 0.0
            if position_qty > 0:
                avg_price = cost_basis / position_qty if position_qty else 0.0
            else:
                avg_price = 0.0
                cost_basis = 0.0

            fill = {
                "fill_id": f"QS-FILL-{fill_id:06d}",
                "order_id": f"QS-{fill_id:06d}",
                "side": side,
                "price": round(price, 6),
                "quantity": round(qty, 6),
                "fees": round(fee, 6),
                "ts": ts.isoformat(),
            }
            fills.append(fill)
            trades.append(
                {
                    "order_id": fill["order_id"],
                    "qty": round(signed_qty, 6),
                    "price": round(price, 6),
                    "notional": round(notional_value, 6),
                    "pnl": 0.0,
                }
            )
            fill_id += 1

        market_value = position_qty * price
        equity = cash + market_value
        equity_rows.append({"ts": ts.to_pydatetime(), "equity": equity, "cash": cash})
        exposures.append(abs(market_value) / equity if equity else 0.0)

    last_price = float(df["Close"].iloc[-1])
    unrealized = position_qty * (last_price - avg_price)
    account = {
        "cash": cash,
        "equity": cash + position_qty * last_price,
        "buying_power": cash,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized,
    }
    positions: Dict[str, Dict[str, float]] = {}
    if abs(position_qty) > 1e-6:
        positions[symbol] = {
            "quantity": round(position_qty, 6),
            "average_price": round(avg_price, 6),
            "unrealized_pnl": round(unrealized, 6),
        }

    return equity_rows, exposures, fills, trades, account, positions


def _format_explanation(payload: Dict[str, float | str]) -> str:
    direction = str(payload.get("direction", "flat"))
    z_score = payload.get("z_score")
    threshold = payload.get("threshold")
    price = payload.get("price")
    mean = payload.get("mean")
    std = payload.get("std")
    if not isinstance(z_score, (int, float)) or not isinstance(threshold, (int, float)):
        return payload.get("reason", "Mean reversion context unavailable.")  # type: ignore[return-value]
    comparison = "below" if z_score <= threshold else "above"
    if direction == "short":
        comparison = "above" if z_score >= threshold else "below"
    price_token = f" @ ${price:.2f}" if isinstance(price, (int, float)) else ""
    mean_token = (
        f" (mean ${mean:.2f}, std {std:.3f})"
        if isinstance(mean, (int, float)) and isinstance(std, (int, float))
        else ""
    )
    return f"Mean reversion signalled a {direction} entry: z={z_score:.2f} {comparison} threshold {threshold:.2f}{price_token}{mean_token}."


def _ensure_env_defaults(
    env_path: Path,
    *,
    symbol: str,
    asset_class: str,
    interval: str,
    offline: bool,
    skip: bool,
) -> None:
    if skip:
        return
    values = load_env(env_path)
    updated = False
    if "SYMBOL" not in values:
        values["SYMBOL"] = symbol
        updated = True
    if "DEFAULT_ASSET_CLASS" not in values:
        values["DEFAULT_ASSET_CLASS"] = asset_class
        updated = True
    if "INTERVAL" not in values:
        values["INTERVAL"] = interval
        updated = True
    if offline and values.get("LOGOS_OFFLINE_ONLY", "").strip() == "":
        values["LOGOS_OFFLINE_ONLY"] = "1"
        updated = True
    if updated:
        write_env(values, path=env_path)


def run(args: argparse.Namespace, *, settings: Settings | None = None) -> int:
    offline = resolve_offline_flag(getattr(args, "offline", False))
    fixture_dir = _load_fixture_dir(getattr(args, "fixture", None))
    env_values = load_env(getattr(args, "env_path", DEFAULT_ENV_PATH))
    symbol, asset_class, interval = _default_symbol(settings, env_values)

    _ensure_env_defaults(
        getattr(args, "env_path", DEFAULT_ENV_PATH),
        symbol=symbol,
        asset_class=asset_class,
        interval=interval,
        offline=offline,
        skip=bool(getattr(args, "skip_env", False)),
    )

    df, bar_metadata = _fetch_bars(symbol, fixture_dir)
    account_defaults = _load_account(fixture_dir)

    lookback = max(int(getattr(args, "lookback", DEFAULT_LOOKBACK)), 2)
    z_entry = max(float(getattr(args, "z_entry", DEFAULT_Z_ENTRY)), 0.5)
    notional = max(float(getattr(args, "notional", DEFAULT_NOTIONAL)), 1.0)
    fee_bps = max(float(getattr(args, "fee_bps", DEFAULT_FEE_BPS)), 0.0)

    signals = generate_signals(df, lookback=lookback, z_entry=z_entry)
    if (signals != 0).sum() == 0:
        raise SystemExit(
            "quickstart fixture did not trigger a trade; adjust parameters"
        )

    equity_rows, exposures, fills, trades, account_payload, positions_payload = (
        _simulate_session(
            df,
            signals,
            symbol=symbol,
            notional=notional,
            fee_bps=fee_bps,
            starting_cash=account_defaults["cash"],
        )
    )

    fill_ts = None
    direction = "flat"
    if fills:
        fill_ts = datetime.fromisoformat(str(fills[0]["ts"]))
        direction = "long" if fills[0]["side"] == "buy" else "short"
    explanation_payload = explain_mean_reversion(
        df,
        timestamp=fill_ts or df.index[-1],
        lookback=lookback,
        z_entry=z_entry,
        direction=direction,
    )
    explanation_text = _format_explanation(explanation_payload)

    seed = _resolve_seed(getattr(args, "seed", None))
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    label = f"{DEFAULT_LABEL_PREFIX}-{timestamp}"
    output_dir = (getattr(args, "output_dir", None) or RUNS_LIVE_SESSIONS_DIR).resolve()
    ensure_dir(output_dir)
    paths = prepare_seeded_run_paths(seed, label, base_dir=output_dir)

    equity_path, metrics_path = write_equity_and_metrics(
        paths,
        equity_curve=equity_rows,
        trades=trades,
        exposures=exposures,
        metrics_provenance={
            "source": "fixture",
            "dataset": _relative_to_project(fixture_dir),
            "strategy": "mean_reversion",
            "offline": True,
        },
    )

    window = _infer_window(df.index)
    config_payload = {
        "symbol": symbol,
        "seed": seed,
        "label": label,
        "dataset": _relative_to_project(fixture_dir),
        "strategy": "mean_reversion",
        "lookback": lookback,
        "z_entry": z_entry,
        "notional": notional,
        "fee_bps": fee_bps,
        "interval": interval,
        "asset_class": asset_class,
        "window": window.to_dict(),
        "offline": offline,
    }

    write_snapshot(
        paths,
        account=account_payload,
        positions=positions_payload,
        open_orders=[],
        fills=fills,
        config=config_payload,
        clock=df.index[-1].to_pydatetime(),
    )

    provenance_payload = {
        "run_id": paths.run_id,
        "label": label,
        "seed": seed,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_source": "fixture",
        "data_details": {
            "dataset": _relative_to_project(fixture_dir),
            "symbol": symbol,
            "bars": len(df),
            "first_timestamp": df.index[0].isoformat(),
            "last_timestamp": df.index[-1].isoformat(),
        },
        "adapter": {"entrypoint": "logos.cli.quickstart", "mode": "paper"},
        "offline": offline,
        "window": window.to_dict(),
        "strategy": {
            "name": "mean_reversion",
            "lookback": lookback,
            "z_entry": z_entry,
        },
    }
    atomic_write_text(
        paths.run_dir / "provenance.json",
        json.dumps(provenance_payload, indent=2),
        encoding="utf-8",
    )

    session_lines = [
        "# Quickstart Session",
        "",
        f"- Run ID: `{paths.run_id}`",
        f"- Symbol: `{symbol}`",
        f"- Bars: {len(df)}",
        f"- Interval: {interval}",
        f"- Strategy: mean_reversion (lookback={lookback}, z_entry={z_entry})",
        f"- Dataset: `{_relative_to_project(fixture_dir)}`",
        f"- Offline: {'yes' if offline else 'no'}",
        f"- Why we traded: {explanation_text}",
    ]
    atomic_write_text(
        paths.session_file,
        "\n".join(session_lines) + "\n",
        encoding="utf-8",
    )

    if output_dir == RUNS_LIVE_SESSIONS_DIR:
        update_symlink(paths.run_dir, RUNS_LIVE_LATEST_LINK)
    else:
        fallback_link = output_dir / "latest"
        update_symlink(paths.run_dir, fallback_link)

    print("Quickstart session complete.\n")
    print(f"Run ID      : {paths.run_id}")
    print(f"Session Dir : {paths.run_dir}")
    print(f"Snapshot    : {paths.snapshot_file}")
    print(f"Metrics     : {metrics_path}")
    print(f"Explanation : {explanation_text}")

    return 0

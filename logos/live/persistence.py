"""Deterministic persistence helpers for live paper sessions."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import IO, Iterable, Mapping, MutableMapping, Sequence, TypedDict

import pandas as pd

from core.io.atomic_write import atomic_write, atomic_write_text
from core.io.dirs import ensure_dir

from logos.metrics import exposure as exposure_ratio
from logos.metrics import hit_rate, max_drawdown, sharpe
from logos.paths import RUNS_LIVE_DIR, safe_slug

# We treat the equity curve as daily closes when annualising Sharpe.
# Minute-level curves can adjust the frequency in a future milestone.
_SHARPE_PERIODS_PER_YEAR = 252


@dataclass(slots=True)
class SeededRunPaths:
    """Directory layout for a deterministic paper run."""

    seed: int
    label: str
    run_id: str
    run_dir: Path
    artifacts_dir: Path
    snapshot_file: Path
    config_file: Path
    equity_curve_csv: Path
    metrics_file: Path
    provenance_file: Path
    session_file: Path
    orchestrator_metrics_file: Path
    router_state_file: Path


def run_id_from_seed(seed: int, label: str) -> str:
    slug = safe_slug(label)
    return f"{int(seed):04d}-{slug}" if slug else f"{int(seed):04d}"


def prepare_seeded_run_paths(
    seed: int,
    label: str,
    *,
    base_dir: Path | None = None,
) -> SeededRunPaths:
    base = base_dir or RUNS_LIVE_DIR
    run_id = run_id_from_seed(seed, label)
    run_dir = base / run_id
    artifacts_dir = run_dir / "artifacts"
    ensure_dir(run_dir)
    ensure_dir(artifacts_dir)

    snapshot_file = run_dir / "snapshot.json"
    config_file = run_dir / "config.yaml"
    equity_curve_csv = artifacts_dir / "equity_curve.csv"
    metrics_file = artifacts_dir / "metrics.json"
    provenance_file = run_dir / "provenance.json"
    session_file = run_dir / "session.md"
    orchestrator_metrics_file = run_dir / "orchestrator_metrics.jsonl"
    router_state_file = run_dir / "router_state.json"

    return SeededRunPaths(
        seed=seed,
        label=label,
        run_id=run_id,
        run_dir=run_dir,
        artifacts_dir=artifacts_dir,
        snapshot_file=snapshot_file,
        config_file=config_file,
        equity_curve_csv=equity_curve_csv,
        metrics_file=metrics_file,
        provenance_file=provenance_file,
        session_file=session_file,
        orchestrator_metrics_file=orchestrator_metrics_file,
        router_state_file=router_state_file,
    )


class EquityRow(TypedDict):
    ts: datetime
    equity: float
    cash: float


def _to_primitive(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {k: _to_primitive(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_primitive(v) for v in value]
    return value


def _to_float(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, str):
        return float(value)
    raise TypeError(f"Unsupported numeric type: {type(value)!r}")


def write_snapshot(
    paths: SeededRunPaths,
    *,
    account: Mapping[str, object],
    positions: Mapping[str, Mapping[str, object]] | Sequence[Mapping[str, object]],
    open_orders: Sequence[Mapping[str, object]],
    fills: Sequence[Mapping[str, object]],
    config: Mapping[str, object],
    clock: datetime | str,
) -> Path:
    payload: MutableMapping[str, object] = {
        "run_id": paths.run_id,
        "seed": paths.seed,
        "clock": clock.isoformat() if isinstance(clock, datetime) else str(clock),
        "account": _to_primitive(dict(account)),
        "positions": _to_primitive(
            {**positions} if isinstance(positions, Mapping) else list(positions)
        ),
        "open_orders": _to_primitive(list(open_orders)),
        "fills": _to_primitive(list(fills)),
        "config": _to_primitive(dict(config)),
    }
    ensure_dir(paths.snapshot_file.parent)
    atomic_write_text(
        paths.snapshot_file,
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return paths.snapshot_file


def write_equity_and_metrics(
    paths: SeededRunPaths,
    *,
    equity_curve: Sequence[Mapping[str, object]],
    trades: Sequence[Mapping[str, object]],
    exposures: Iterable[float],
    metrics_provenance: Mapping[str, object] | None = None,
) -> tuple[Path, Path]:
    rows: list[EquityRow] = [
        {
            "ts": _to_timestamp(row["ts"]),
            "equity": _to_float(row.get("equity", 0.0)),
            "cash": _to_float(row.get("cash", 0.0)),
        }
        for row in equity_curve
    ]
    rows.sort(key=lambda row: row["ts"])

    ensure_dir(paths.artifacts_dir)

    def _write_equity(fh: IO[str]) -> None:
        writer = csv.writer(fh)
        writer.writerow(["ts", "equity", "cash"])
        for row in rows:
            writer.writerow(
                [row["ts"].isoformat(), f"{row['equity']:.6f}", f"{row['cash']:.6f}"]
            )

    atomic_write(paths.equity_curve_csv, _write_equity, newline="")

    equity_index = [pd.Timestamp(row["ts"]) for row in rows]
    equity_series = pd.Series(
        [row["equity"] for row in rows], index=equity_index, dtype=float
    )
    returns = equity_series.pct_change().dropna()

    initial_equity = float(equity_series.iloc[0]) if not equity_series.empty else 0.0
    final_equity = float(equity_series.iloc[-1]) if not equity_series.empty else 0.0
    pnl = final_equity - initial_equity

    sharpe_ratio = (
        float(sharpe(returns, periods_per_year=_SHARPE_PERIODS_PER_YEAR))
        if not returns.empty
        else 0.0
    )
    drawdown = float(max_drawdown(equity_series)) if not equity_series.empty else 0.0

    trade_returns = pd.Series(
        [_to_float(trade.get("pnl", 0.0)) for trade in trades], dtype=float
    )
    hit = float(hit_rate(trade_returns)) if not trade_returns.empty else 0.0

    turnover_notional = 0.0
    for trade in trades:
        notional_value = trade.get("notional")
        if notional_value is not None:
            turnover_notional += abs(_to_float(notional_value))
        else:
            qty = _to_float(trade.get("qty", 0.0))
            price = _to_float(trade.get("price", 0.0))
            turnover_notional += abs(qty * price)
    turnover = turnover_notional / initial_equity if initial_equity else 0.0

    exposure_values = list(exposures)
    if not exposure_values:
        exposure_values = [0.0] * max(len(equity_index), 1)

    exposure_index: list[pd.Timestamp] = []
    if len(equity_index) > 0:
        exposure_index = list(equity_index[: len(exposure_values)])
        last_ts = equity_index[-1]
    else:
        last_ts = pd.Timestamp.now(tz="UTC")

    if len(exposure_values) > len(exposure_index):
        step = pd.Timedelta(seconds=1)
        for i in range(len(exposure_values) - len(exposure_index)):
            exposure_index.append(last_ts + step * (i + 1))
    elif len(exposure_values) < len(exposure_index):
        exposure_index = exposure_index[: len(exposure_values)]

    exposure_series = pd.Series(exposure_values, index=exposure_index, dtype=float)
    exposure_value = (
        float(exposure_ratio(exposure_series)) if not exposure_series.empty else 0.0
    )

    metrics_payload = {
        "run_id": paths.run_id,
        "seed": paths.seed,
        "pnl": pnl,
        "start_equity": initial_equity,
        "end_equity": final_equity,
        "sharpe": sharpe_ratio,
        "max_drawdown": drawdown,
        "hit_rate": hit,
        "turnover": turnover,
        "exposure": exposure_value,
    }
    if metrics_provenance:
        metrics_payload["provenance"] = dict(metrics_provenance)

    atomic_write_text(
        paths.metrics_file,
        json.dumps(metrics_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return paths.equity_curve_csv, paths.metrics_file


def _to_timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise TypeError("equity curve entries must include datetime or ISO timestamp")

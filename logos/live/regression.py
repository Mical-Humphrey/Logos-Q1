"""Deterministic regression harness for live trading components.

This harness enforces the Phase 2 contract freeze for regression outputs.
Metadata-only drift is tolerated for a constrained set of volatile fields –
see :data:`VOLATILE_JSON_PATHS` – while window bounds, modes, seeds, and
artifact payloads remain strict. Baselines are versioned via
``BASELINE_VERSION``; runs fail fast when the on-disk version diverges from
the expected tag.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import difflib
import hashlib
import json
import copy
import textwrap
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Protocol, Sequence, Tuple, cast

from core.io.atomic_write import atomic_write_text
from core.io.dirs import ensure_dir
from logos.window import Window, UTC

from .broker_alpaca import AlpacaBrokerAdapter
from .broker_base import (
    OrderIntent as BrokerOrderIntent,
    Position as BrokerPosition,
    SymbolMeta,
)
from .broker_ccxt import CCXTBrokerAdapter
from .broker_paper import PaperBrokerAdapter
from .data_feed import Bar, FixtureReplayFeed
from .persistence import (
    SeededRunPaths,
    prepare_seeded_run_paths,
    write_equity_and_metrics,
    write_snapshot,
)
from .risk import RiskContext, RiskDecision, RiskLimits, enforce_guards
from .time import MockTimeProvider
from .translator import SymbolMetadataRegistry, Translator
from .types import (
    Account,
    OrderIntent as StrategyOrderIntent,
    OrderSide,
    Position,
    SizingInstruction,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE_DIR = (
    PROJECT_ROOT / "tests" / "fixtures" / "live" / "regression_default"
)
BASELINE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "regression" / "smoke"

DEFAULT_SEED = 7
DEFAULT_LABEL = "regression-smoke"
DEFAULT_SYMBOL = "AAPL"

BASELINE_VERSION = "phase2-v1"
BASELINE_VERSION_FILENAME = "BASELINE_VERSION"

# Dot-paths ("."-joined keys) removed from JSON payloads before comparison.
# These surface run metadata that may legitimately change between baseline
# refreshes without signalling behavioural drift.
VOLATILE_JSON_PATHS: Tuple[Tuple[str, ...], ...] = (
    ("run_id",),
    ("generated_at",),
    ("provenance", "generated_at"),
    ("provenance", "git", "commit"),
    ("provenance", "git", "branch"),
    ("tool_version",),
    ("hostname",),
    ("pid",),
)

BARS_FILENAME = "bars.csv"
ACCOUNT_FILENAME = "account.json"
SYMBOLS_FILENAME = "symbols.yaml"
ADAPTER_LOG_FILENAME = "adapter_logs.jsonl"

AdapterMode = str

METRIC_ABS_TOLERANCE = 1e-9


def _relative_to_project(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return resolved.as_posix()


@dataclass(frozen=True)
class RegressionArtifacts:
    snapshot: Path
    equity_curve: Path
    metrics: Path
    provenance: Path
    session: Path
    adapter_logs: Path | None = None


@dataclass(frozen=True)
class RegressionResult:
    run_id: str
    artifacts: RegressionArtifacts
    matches_baseline: bool
    diffs: Dict[str, str]


@dataclass
class RegressionConfig:
    dataset_dir: Path
    symbol: str
    seed: int
    label: str
    window: Window
    adapter_mode: AdapterMode = "paper"
    adapter_name: str | None = None


def _load_account(path: Path) -> Account:
    payload = json.loads(path.read_text(encoding="utf-8"))
    positions: Dict[str, Position] = {}
    for symbol, raw in (payload.get("positions") or {}).items():
        positions[symbol] = Position(
            symbol=symbol,
            quantity=Decimal(str(raw.get("quantity", 0))),
            average_price=Decimal(str(raw.get("average_price", 0))),
        )
    return Account(
        equity=Decimal(str(payload["equity"])),
        cash=Decimal(str(payload["cash"])),
        positions=positions,
        realized_pnl=Decimal(str(payload.get("realized_pnl", 0))),
        unrealized_pnl=Decimal(str(payload.get("unrealized_pnl", 0))),
    )


def _load_metadata(path: Path) -> SymbolMetadataRegistry:
    return SymbolMetadataRegistry.from_yaml(path)


def _build_feed(dataset_path: Path, clock: MockTimeProvider) -> FixtureReplayFeed:
    return FixtureReplayFeed(
        dataset=dataset_path, time_provider=clock, max_age_seconds=600, max_retries=0
    )


def _infer_window_from_dataset(dataset_dir: Path) -> Window:
    bars_path = dataset_dir / BARS_FILENAME
    if not bars_path.exists():
        raise FileNotFoundError(f"bars fixture missing at {bars_path}")
    first_dt: dt.datetime | None = None
    last_dt: dt.datetime | None = None
    with bars_path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            dt_str = row.get("dt")
            if not dt_str:
                continue
            try:
                bar_dt = dt.datetime.fromisoformat(dt_str)
            except ValueError as exc:
                raise RuntimeError(f"invalid dt '{dt_str}' in {bars_path}") from exc
            if first_dt is None:
                first_dt = bar_dt
            last_dt = bar_dt
    if first_dt is None or last_dt is None:
        raise RuntimeError(f"dataset {bars_path} contains no rows")
    window_end = (last_dt + dt.timedelta(days=1)).date()
    return Window.from_bounds(start=first_dt.date(), end=window_end, zone=UTC)


def _configure_paper_broker(
    metadata: SymbolMetadataRegistry,
    account: Account,
    symbol: str,
    clock: MockTimeProvider,
) -> PaperBrokerAdapter:
    broker = PaperBrokerAdapter(
        time_provider=clock,
        starting_cash=float(account.cash),
        slippage_bps=0.0,
        fee_bps=0.0,
    )
    symbol_meta = metadata.resolve(symbol)
    broker.set_symbol_meta(
        SymbolMeta(
            symbol=symbol_meta.symbol,
            price_precision=symbol_meta.price_precision,
            quantity_precision=symbol_meta.quantity_precision,
            min_notional=float(symbol_meta.min_notional),
            min_qty=float(symbol_meta.lot_size),
            step_size=float(symbol_meta.lot_size),
        )
    )
    if account.positions:
        broker.bootstrap_positions(
            {
                key: {
                    "qty": float(pos.quantity),
                    "avg_price": float(pos.average_price),
                    "realized": 0.0,
                }
                for key, pos in account.positions.items()
            }
        )
    return broker


class AdapterLike(Protocol):
    """Subset of adapter behaviour required for regression dry runs."""

    def place_order(self, intent: BrokerOrderIntent) -> object: ...

    def on_market_data(self, symbol: str, price: float, ts: float) -> None: ...


def _to_broker_intent(intent: StrategyOrderIntent) -> BrokerOrderIntent:
    limit_price = intent.price.limit if intent.price else None
    return BrokerOrderIntent(
        symbol=intent.metadata.symbol,
        side=intent.side.value,
        quantity=float(intent.quantity),
        order_type="limit" if limit_price is not None else "market",
        limit_price=float(limit_price) if limit_price is not None else None,
    )


def _account_payload(
    cash: float,
    equity: float,
    broker: PaperBrokerAdapter,
    positions: Sequence[BrokerPosition],
) -> Dict[str, float]:
    unrealized = sum(float(getattr(pos, "unrealized_pnl", 0.0)) for pos in positions)
    return {
        "cash": cash,
        "equity": equity,
        "buying_power": cash,
        "realized_pnl": broker.get_realized_pnl(),
        "unrealized_pnl": unrealized,
    }


def _positions_payload(
    positions: Iterable[BrokerPosition],
) -> Dict[str, Dict[str, float]]:
    payload: Dict[str, Dict[str, float]] = {}
    for position in positions:
        payload[position.symbol] = {
            "quantity": float(position.quantity),
            "average_price": float(position.avg_price),
            "unrealized_pnl": float(position.unrealized_pnl),
        }
    return payload


def _write_adapter_logs(
    paths: SeededRunPaths, entries: List[Dict[str, object]]
) -> Path:
    log_path = paths.artifacts_dir / ADAPTER_LOG_FILENAME
    if not entries:
        atomic_write_text(log_path, "[]\n", encoding="utf-8")
        return log_path
    serialized = "\n".join(json.dumps(dict(item), sort_keys=True) for item in entries)
    atomic_write_text(log_path, serialized + "\n", encoding="utf-8")
    return log_path


def _drain_adapter_logs(adapter: object) -> List[Dict[str, object]]:
    drain = getattr(adapter, "drain_logs", None)
    if callable(drain):
        return [dict(entry) for entry in cast(Iterable[Mapping[str, object]], drain())]
    logs_attr = getattr(adapter, "logs", None)
    if logs_attr is None:
        return []
    if callable(logs_attr):
        raw_logs = cast(Iterable[Mapping[str, object]], logs_attr())
    else:
        raw_logs = cast(Iterable[Mapping[str, object]], logs_attr)
    logs = [dict(entry) for entry in raw_logs]
    reset = getattr(adapter, "reset_logs", None)
    if callable(reset):
        reset()
    return logs


def _select_adapter(
    config: RegressionConfig, clock: MockTimeProvider
) -> Tuple[str, str | None, AdapterLike | None]:
    if config.adapter_mode == "paper":
        return "paper", None, None
    if config.adapter_mode != "adapter":
        raise ValueError(f"Unknown adapter mode: {config.adapter_mode}")
    adapter_name = (config.adapter_name or "").lower()
    if adapter_name == "alpaca":
        return (
            "dry-run",
            "alpaca",
            AlpacaBrokerAdapter(
                base_url="alpaca-paper",
                key_id="dry-run",
                secret_key="dry-run",
                run_id=config.label,
                seed=config.seed,
                time_provider=clock,
            ),
        )
    if adapter_name == "ccxt":
        return (
            "dry-run",
            "ccxt",
            CCXTBrokerAdapter(
                exchange="ccxt-dry",
                run_id=config.label,
                seed=config.seed,
                time_provider=clock,
            ),
        )
    raise ValueError("Adapter mode requires --adapter of 'alpaca' or 'ccxt'")


def _run_pipeline(
    paths: SeededRunPaths, config: RegressionConfig
) -> RegressionArtifacts:
    clock = MockTimeProvider(
        current=dt.datetime(2024, 1, 1, 9, 33, tzinfo=dt.timezone.utc)
    )
    clock_origin = clock.current
    account_path = config.dataset_dir / ACCOUNT_FILENAME
    bars_path = config.dataset_dir / BARS_FILENAME
    symbols_path = config.dataset_dir / SYMBOLS_FILENAME

    account = _load_account(account_path)
    metadata = _load_metadata(symbols_path)
    feed = _build_feed(bars_path, clock)
    bars: List[Bar] = feed.fetch_bars(config.symbol, "1m", since=None)
    window_start = config.window.start.tz_convert("UTC").to_pydatetime()
    window_end = config.window.end.tz_convert("UTC").to_pydatetime()
    bars = [bar for bar in bars if window_start <= bar.dt < window_end]
    if not bars:
        raise RuntimeError("Fixture must contain at least one bar within the window")

    translator = Translator(metadata)
    signal_price = Decimal(str(bars[0].close))
    sizing = SizingInstruction.fixed_notional(Decimal("1000"))
    intent = translator.build_order_intent(
        signal_symbol=config.symbol,
        side=OrderSide.BUY,
        signal_price=signal_price,
        sizing=sizing,
        account=account,
    )
    broker_intent = _to_broker_intent(intent)

    limits = RiskLimits(
        max_notional=5_000.0,
        symbol_position_limits={config.symbol: 100.0},
        max_drawdown_bps=10_000.0,
    )
    ctx = RiskContext(
        equity=float(account.equity),
        position_quantity=0.0,
        realized_drawdown_bps=0.0,
        consecutive_rejects=0,
        last_bar_ts=bars[0].dt.timestamp(),
        now_ts=bars[0].dt.timestamp(),
    )
    decision: RiskDecision = enforce_guards(
        config.symbol, broker_intent.quantity, float(signal_price), limits, ctx
    )
    if not decision.allowed:
        raise RuntimeError(f"Regression guard rejected order: {decision.reason}")

    adapter_mode_label, adapter_name, adapter = _select_adapter(config, clock)
    adapter_logs: List[Dict[str, object]] = []
    equity_curve: List[Dict[str, object]]
    exposures: List[float]
    fills_payload: List[Dict[str, object]]
    trade_payloads: List[Dict[str, object]]
    account_payload: Mapping[str, float]
    positions_payload: Mapping[str, Mapping[str, float]]

    if adapter_mode_label == "paper":
        broker = _configure_paper_broker(metadata, account, config.symbol, clock)
        order = broker.place_order(broker_intent)

        equity_curve = [
            {
                "ts": bars[0].dt - dt.timedelta(minutes=1),
                "equity": broker.get_account().equity,
                "cash": broker.get_account().cash,
            }
        ]
        exposures = [0.0]
        fills_payload = []
        trade_payloads = []

        for bar in bars:
            clock.current = bar.dt
            broker.on_market_data(bar.symbol, bar.close, bar.dt.timestamp())
            snapshot = broker.get_account()
            positions = broker.get_positions()
            exposures.append(sum(abs(pos.quantity) for pos in positions))
            equity_curve.append(
                {"ts": bar.dt, "equity": snapshot.equity, "cash": snapshot.cash}
            )
            for fill in broker.poll_fills():
                fill_dt = dt.datetime.fromtimestamp(fill.ts, tz=dt.timezone.utc)
                fills_payload.append(
                    {
                        "order_id": fill.order_id,
                        "fill_id": fill.fill_id,
                        "side": order.intent.side,
                        "price": round(fill.price, 6),
                        "quantity": round(fill.quantity, 6),
                        "fees": round(fill.fees, 6),
                        "ts": fill_dt.isoformat(),
                    }
                )
                trade_payloads.append(
                    {
                        "order_id": fill.order_id,
                        "pnl": 0.0,
                        "notional": round(fill.price * fill.quantity, 6),
                        "qty": round(fill.quantity, 6),
                        "price": round(fill.price, 6),
                    }
                )

        final_snapshot = broker.get_account()
        final_positions = broker.get_positions()
        account_payload = _account_payload(
            final_snapshot.cash, final_snapshot.equity, broker, final_positions
        )
        positions_payload = _positions_payload(final_positions)
    else:
        assert adapter is not None and adapter_name is not None
        adapter.place_order(broker_intent)
        adapter_logs.extend(_drain_adapter_logs(adapter))

        equity_curve = [
            {
                "ts": bars[0].dt - dt.timedelta(minutes=1),
                "equity": float(account.equity),
                "cash": float(account.cash),
            }
        ]
        exposures = [0.0]
        fills_payload = []
        trade_payloads = []
        for bar in bars:
            clock.current = bar.dt
            adapter.on_market_data(bar.symbol, bar.close, bar.dt.timestamp())
            adapter_logs.extend(_drain_adapter_logs(adapter))
            equity_curve.append(
                {
                    "ts": bar.dt,
                    "equity": float(account.equity),
                    "cash": float(account.cash),
                }
            )
            exposures.append(0.0)

        account_payload = {
            "cash": float(account.cash),
            "equity": float(account.equity),
            "buying_power": float(account.cash),
            "realized_pnl": float(account.realized_pnl),
            "unrealized_pnl": float(account.unrealized_pnl),
        }
        positions_payload = {
            symbol: {
                "quantity": float(pos.quantity),
                "average_price": float(pos.average_price),
                "unrealized_pnl": float(account.unrealized_pnl),
            }
            for symbol, pos in account.positions.items()
        }
        adapter_logs.extend(_drain_adapter_logs(adapter))

    config_payload = {
        "symbol": config.symbol,
        "seed": config.seed,
        "label": config.label,
        "adapter_mode": adapter_mode_label,
        "adapter_name": adapter_name,
        "dataset": str(config.dataset_dir),
        "clock_start": clock_origin.isoformat(),
        "clock_timezone": "UTC",
        "window": config.window.to_dict(),
    }

    dataset_reference = _relative_to_project(config.dataset_dir)
    metrics_provenance: Dict[str, object] = {
        "source": "fixture",
        "dataset": dataset_reference,
        "adapter_mode": adapter_mode_label,
        "synthetic": False,
        "window": config.window.to_dict(),
    }
    if adapter_name:
        metrics_provenance["adapter_name"] = adapter_name

    write_snapshot(
        paths,
        account=account_payload,
        positions=positions_payload,
        open_orders=[],
        fills=fills_payload,
        config=config_payload,
        clock=bars[-1].dt,
    )
    equity_path, metrics_path = write_equity_and_metrics(
        paths,
        equity_curve=equity_curve,
        trades=trade_payloads,
        exposures=exposures,
        metrics_provenance=metrics_provenance,
    )

    dataset_details = {
        "dataset": dataset_reference,
        "symbol": config.symbol,
        "bars": len(bars),
        "first_timestamp": bars[0].dt.isoformat(),
        "last_timestamp": bars[-1].dt.isoformat(),
        "account_fixture": ACCOUNT_FILENAME,
        "bars_fixture": BARS_FILENAME,
        "metadata_fixture": SYMBOLS_FILENAME,
        "window": config.window.to_dict(),
    }
    adapter_payload: Dict[str, object] = {
        "entrypoint": "logos.live.regression",
        "mode": adapter_mode_label,
    }
    if adapter_name:
        adapter_payload["name"] = adapter_name

    provenance_payload: Dict[str, object] = {
        "run_id": paths.run_id,
        "label": config.label,
        "seed": config.seed,
        "generated_at": clock_origin.isoformat(),
        "git_sha": "deterministic-fixture",
        "data_source": "fixture",
        "data_details": dataset_details,
        "adapter": adapter_payload,
        "allow_synthetic": False,
        "window": config.window.to_dict(),
    }

    atomic_write_text(
        paths.provenance_file,
        json.dumps(provenance_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    session_lines = [
        "# Regression Session",
        "",
        f"- Run ID: `{paths.run_id}`",
        f"- Label: `{config.label}`",
        f"- Seed: {config.seed}",
        f"- Dataset: `{dataset_reference}`",
        f"- Symbol: `{config.symbol}`",
        f"- Bars: {len(bars)}",
        f"- Adapter Mode: {adapter_mode_label}",
        "- Data Source: fixture",
        f"- Generated: {clock_origin.isoformat()}",
        f"- Window: {config.window.start.isoformat()} → {config.window.end.isoformat()}",
    ]
    if adapter_name:
        session_lines.insert(-2, f"- Adapter Name: {adapter_name}")
    atomic_write_text(
        paths.session_file, "\n".join(session_lines) + "\n", encoding="utf-8"
    )

    adapter_log_path: Path | None = None
    if adapter_mode_label != "paper":
        adapter_log_path = _write_adapter_logs(paths, adapter_logs)

    return RegressionArtifacts(
        snapshot=paths.snapshot_file,
        equity_curve=equity_path,
        metrics=metrics_path,
        provenance=paths.provenance_file,
        session=paths.session_file,
        adapter_logs=adapter_log_path,
    )


def _delete_path(target: object, segments: Sequence[str]) -> None:
    if not segments:
        return
    head, *tail = segments
    if isinstance(target, dict):
        if head not in target:
            return
        if tail:
            _delete_path(target[head], tail)
        else:
            target.pop(head, None)
    elif isinstance(target, list):
        for item in target:
            _delete_path(item, segments)


def _prune_paths(payload: object, paths: Sequence[Tuple[str, ...]]) -> object:
    clone = copy.deepcopy(payload)
    for path in paths:
        _delete_path(clone, path)
    return clone


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, indent=2)


def _compare_json(baseline: Path, output: Path) -> str | None:
    try:
        baseline_data = json.loads(baseline.read_text(encoding="utf-8"))
        output_data = json.loads(output.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _text_diff(baseline, output)

    baseline_clean = _prune_paths(baseline_data, VOLATILE_JSON_PATHS)
    output_clean = _prune_paths(output_data, VOLATILE_JSON_PATHS)
    if baseline_clean == output_clean:
        return None
    return _diff_strings(
        _canonical_json(baseline_clean),
        _canonical_json(output_clean),
        baseline,
        output,
    )


def _compare_jsonl(baseline: Path, output: Path) -> str | None:
    try:
        baseline_lines = [
            json.loads(line)
            for line in baseline.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        output_lines = [
            json.loads(line)
            for line in output.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except json.JSONDecodeError:
        return _text_diff(baseline, output)

    baseline_clean = [
        _prune_paths(entry, VOLATILE_JSON_PATHS) for entry in baseline_lines
    ]
    output_clean = [
        _prune_paths(entry, VOLATILE_JSON_PATHS) for entry in output_lines
    ]
    if baseline_clean == output_clean:
        return None
    baseline_dump = [
        json.dumps(entry, sort_keys=True, separators=(",", ":"))
        for entry in baseline_clean
    ]
    output_dump = [
        json.dumps(entry, sort_keys=True, separators=(",", ":"))
        for entry in output_clean
    ]
    diff = difflib.unified_diff(
        baseline_dump,
        output_dump,
        fromfile=str(baseline),
        tofile=str(output),
        lineterm="",
    )
    rendered = "\n".join(diff)
    return rendered or None


def _diff_strings(baseline_str: str, output_str: str, baseline: Path, output: Path) -> str:
    diff = difflib.unified_diff(
        baseline_str.splitlines(),
        output_str.splitlines(),
        fromfile=str(baseline),
        tofile=str(output),
        lineterm="",
    )
    return "\n".join(diff)


def _text_diff(baseline: Path, output: Path) -> str:
    return _diff_strings(
        baseline.read_text(encoding="utf-8"),
        output.read_text(encoding="utf-8"),
        baseline,
        output,
    )


def _locate_version_file(baseline_dir: Path) -> Path | None:
    current = baseline_dir
    for _ in range(5):
        candidate = current / BASELINE_VERSION_FILENAME
        if candidate.exists():
            return candidate
        if current == current.parent:
            break
        current = current.parent
    return None


def _ensure_baseline_version(baseline_dir: Path, *, allow_write: bool) -> None:
    version_path = _locate_version_file(baseline_dir)
    if version_path is None:
        if allow_write:
            target = baseline_dir / BASELINE_VERSION_FILENAME
            ensure_dir(target.parent)
            target.write_text(BASELINE_VERSION + "\n", encoding="utf-8")
            return
        raise RuntimeError(
            f"Baseline at {baseline_dir} does not declare a version; expected {BASELINE_VERSION}"
        )
    version = version_path.read_text(encoding="utf-8").strip()
    if version != BASELINE_VERSION:
        raise RuntimeError(
            f"Baseline version mismatch ({version_path} has '{version}', expected '{BASELINE_VERSION}')"
        )


def _compare(baseline: Path, output: Path) -> str | None:
    if not baseline.exists():
        return f"Baseline missing: {baseline}"
    if output.name == "metrics.json":
        return _compare_metrics(baseline, output, METRIC_ABS_TOLERANCE)
    if baseline.suffix == ".json" and output.suffix == ".json":
        return _compare_json(baseline, output)
    if baseline.suffix == ".jsonl" and output.suffix == ".jsonl":
        return _compare_jsonl(baseline, output)
    if output.read_bytes() == baseline.read_bytes():
        return None
    return _text_diff(baseline, output)


def _compare_metrics(baseline: Path, output: Path, tolerance: float) -> str | None:
    baseline_data = json.loads(baseline.read_text(encoding="utf-8"))
    output_data = json.loads(output.read_text(encoding="utf-8"))

    baseline_clean = _prune_paths(baseline_data, VOLATILE_JSON_PATHS)
    output_clean = _prune_paths(output_data, VOLATILE_JSON_PATHS)

    mismatches: List[str] = []
    keys = sorted(set(baseline_clean) | set(output_clean))
    for key in keys:
        if key not in baseline_clean:
            mismatches.append(f"missing-in-baseline:{key}")
            continue
        if key not in output_clean:
            mismatches.append(f"missing-in-output:{key}")
            continue
        baseline_value = baseline_clean[key]
        output_value = output_clean[key]
        if isinstance(baseline_value, (int, float)) and isinstance(
            output_value, (int, float)
        ):
            if abs(float(baseline_value) - float(output_value)) > tolerance:
                mismatches.append(
                    f"{key} baseline={baseline_value} output={output_value} tol={tolerance}"
                )
        else:
            if baseline_value != output_value:
                mismatches.append(
                    f"{key} baseline={baseline_value} output={output_value}"
                )
    if mismatches:
        return "metrics mismatch: " + "; ".join(mismatches)
    return None


def run_regression(
    output_root: Path,
    *,
    baseline_dir: Path = BASELINE_DIR,
    update_baseline: bool = False,
    allow_refresh: bool = False,
    dataset_dir: Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    seed: int = DEFAULT_SEED,
    label: str = DEFAULT_LABEL,
    adapter_mode: AdapterMode = "paper",
    adapter_name: str | None = None,
    window: Window | None = None,
) -> RegressionResult:
    dataset = dataset_dir or DEFAULT_FIXTURE_DIR
    ensure_dir(output_root)
    if update_baseline:
        ensure_dir(baseline_dir)
    _ensure_baseline_version(baseline_dir, allow_write=update_baseline)
    paths = prepare_seeded_run_paths(seed, label, base_dir=output_root)
    window_obj = window or _infer_window_from_dataset(dataset)
    config = RegressionConfig(
        dataset_dir=dataset,
        symbol=symbol,
        seed=seed,
        label=label,
        window=window_obj,
        adapter_mode=adapter_mode,
        adapter_name=adapter_name,
    )
    artifacts = _run_pipeline(paths, config)

    tracked = {
        "snapshot": artifacts.snapshot,
        "equity_curve": artifacts.equity_curve,
        "metrics": artifacts.metrics,
        "provenance": artifacts.provenance,
        "session": artifacts.session,
    }
    if artifacts.adapter_logs is not None:
        tracked["adapter_logs"] = artifacts.adapter_logs

    diff_map: Dict[str, str] = {}
    for name, artifact in tracked.items():
        baseline_path = baseline_dir / artifact.name
        if update_baseline:
            if not allow_refresh:
                raise RuntimeError(
                    "Baseline refresh requested without confirmation flag"
                )
            ensure_dir(baseline_path.parent)
            baseline_path.write_bytes(artifact.read_bytes())
            continue
        diff = _compare(baseline_path, artifact)
        if diff:
            diff_map[name] = diff
    matches = not diff_map and not update_baseline
    return RegressionResult(
        run_id=paths.run_id,
        artifacts=artifacts,
        matches_baseline=matches,
        diffs=diff_map,
    )


def _checksum(path: Path | None) -> str:
    if path is None:
        raise ValueError("checksum requires a file path")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Logos live regression smoke test"
    )
    parser.add_argument("--output-dir", type=Path, default=Path("runs/live/regression"))
    parser.add_argument("--baseline", type=Path, default=BASELINE_DIR)
    parser.add_argument("--refresh-baseline", action="store_true")
    parser.add_argument("--confirm-refresh", action="store_true")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_FIXTURE_DIR)
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--label", default=DEFAULT_LABEL)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--adapter-mode", choices=["paper", "adapter"], default="paper")
    parser.add_argument("--adapter", choices=["alpaca", "ccxt"], default=None)
    return parser


def main(argv: List[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.refresh_baseline and not args.confirm_refresh:
        parser.error(
            "--refresh-baseline also requires --confirm-refresh to avoid accidental updates"
        )
    result = run_regression(
        output_root=args.output_dir,
        baseline_dir=args.baseline,
        update_baseline=args.refresh_baseline,
        allow_refresh=args.confirm_refresh,
        dataset_dir=args.dataset,
        symbol=args.symbol,
        seed=args.seed,
        label=args.label,
        adapter_mode=args.adapter_mode,
        adapter_name=args.adapter,
    )
    tracked = [
        ("snapshot", result.artifacts.snapshot),
        ("equity_curve", result.artifacts.equity_curve),
        ("metrics", result.artifacts.metrics),
        ("provenance", result.artifacts.provenance),
        ("session", result.artifacts.session),
    ]
    if result.artifacts.adapter_logs is not None:
        tracked.append(("adapter_logs", result.artifacts.adapter_logs))
    for name, artifact in tracked:
        digest = _checksum(artifact)
        print(f"{name}: {artifact}")
        print(textwrap.indent(f"sha256={digest}", prefix="  "))
    if not result.matches_baseline and not args.refresh_baseline:
        print("Regression deviated from baseline", flush=True)
        for name, diff in result.diffs.items():
            print(f"\n[name={name}]\n{diff}")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

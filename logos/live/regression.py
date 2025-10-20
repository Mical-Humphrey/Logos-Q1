"""Deterministic regression harness for live trading components."""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import textwrap
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from .broker_alpaca import AlpacaBrokerAdapter
from .broker_base import OrderIntent as BrokerOrderIntent, SymbolMeta
from .broker_ccxt import CCXTBrokerAdapter
from .broker_paper import PaperBrokerAdapter
from .data_feed import Bar, FixtureReplayFeed
from .persistence import SeededRunPaths, prepare_seeded_run_paths, write_equity_and_metrics, write_snapshot
from .risk import RiskContext, RiskDecision, RiskLimits, enforce_guards
from .time import MockTimeProvider
from .translator import SymbolMetadataRegistry, Translator
from .types import Account, OrderSide, Position, SizingInstruction

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "live" / "regression_default"
BASELINE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "regression" / "smoke"

DEFAULT_SEED = 7
DEFAULT_LABEL = "regression-smoke"
DEFAULT_SYMBOL = "AAPL"

BARS_FILENAME = "bars.csv"
ACCOUNT_FILENAME = "account.json"
SYMBOLS_FILENAME = "symbols.yaml"
ADAPTER_LOG_FILENAME = "adapter_logs.jsonl"

AdapterMode = str


@dataclass(frozen=True)
class RegressionArtifacts:
    snapshot: Path
    equity_curve: Path
    metrics: Path
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
    return FixtureReplayFeed(dataset=dataset_path, time_provider=clock, max_age_seconds=600, max_retries=0)


def _configure_paper_broker(metadata: SymbolMetadataRegistry, account: Account, symbol: str, clock: MockTimeProvider) -> PaperBrokerAdapter:
    broker = PaperBrokerAdapter(time_provider=clock, starting_cash=float(account.cash), slippage_bps=0.0, fee_bps=0.0)
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


def _to_broker_intent(intent) -> BrokerOrderIntent:  # type: ignore[no-untyped-def]
    limit_price = intent.price.limit if intent.price else None
    return BrokerOrderIntent(
        symbol=intent.metadata.symbol,
        side=intent.side.value,
        quantity=float(intent.quantity),
        order_type="limit" if limit_price is not None else "market",
        limit_price=float(limit_price) if limit_price is not None else None,
    )


def _account_payload(cash: float, equity: float, broker: PaperBrokerAdapter, positions: Sequence) -> Mapping[str, float]:  # type: ignore[no-untyped-def]
    unrealized = sum(getattr(pos, "unrealized_pnl", 0.0) for pos in positions)
    return {
        "cash": cash,
        "equity": equity,
        "buying_power": cash,
        "realized_pnl": broker.get_realized_pnl(),
        "unrealized_pnl": unrealized,
    }


def _positions_payload(positions: Iterable) -> Mapping[str, Mapping[str, float]]:  # type: ignore[no-untyped-def]
    payload: Dict[str, Dict[str, float]] = {}
    for position in positions:
        payload[position.symbol] = {
            "quantity": position.quantity,
            "average_price": position.avg_price,
            "unrealized_pnl": position.unrealized_pnl,
        }
    return payload


def _write_adapter_logs(paths: SeededRunPaths, entries: List[dict], mode: str) -> Path:
    log_path = paths.artifacts_dir / ADAPTER_LOG_FILENAME
    if not entries:
        log_path.write_text("[]\n", encoding="utf-8")
        return log_path
    enriched = []
    for entry in entries:
        payload = dict(entry)
        payload.setdefault("adapter_mode", mode)
        enriched.append(payload)
    serialized = "\n".join(json.dumps(item, sort_keys=True) for item in enriched)
    log_path.write_text(serialized + "\n", encoding="utf-8")
    return log_path


def _select_adapter(config: RegressionConfig, clock: MockTimeProvider) -> Tuple[str, object | None]:
    if config.adapter_mode == "paper":
        return "paper", None
    if config.adapter_mode != "adapter":
        raise ValueError(f"Unknown adapter mode: {config.adapter_mode}")
    adapter = (config.adapter_name or "").lower()
    if adapter == "alpaca":
        return "alpaca", AlpacaBrokerAdapter(
            base_url="alpaca-paper",
            key_id="dry-run",
            secret_key="dry-run",
            run_id=config.label,
            seed=config.seed,
            time_provider=clock,
        )
    if adapter == "ccxt":
        return "ccxt", CCXTBrokerAdapter(
            exchange="ccxt-dry",
            run_id=config.label,
            seed=config.seed,
            time_provider=clock,
        )
    raise ValueError("Adapter mode requires --adapter of 'alpaca' or 'ccxt'")


def _run_pipeline(paths: SeededRunPaths, config: RegressionConfig) -> RegressionArtifacts:
    clock = MockTimeProvider(current=dt.datetime(2024, 1, 1, 9, 33, tzinfo=dt.timezone.utc))
    account_path = config.dataset_dir / ACCOUNT_FILENAME
    bars_path = config.dataset_dir / BARS_FILENAME
    symbols_path = config.dataset_dir / SYMBOLS_FILENAME

    account = _load_account(account_path)
    metadata = _load_metadata(symbols_path)
    feed = _build_feed(bars_path, clock)
    bars: List[Bar] = feed.fetch_bars(config.symbol, "1m", since=None)
    if not bars:
        raise RuntimeError("Fixture must contain at least one bar")

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

    limits = RiskLimits(max_notional=5_000.0, symbol_position_limits={config.symbol: 100.0}, max_drawdown_bps=10_000.0)
    ctx = RiskContext(
        equity=float(account.equity),
        position_quantity=0.0,
        realized_drawdown_bps=0.0,
        consecutive_rejects=0,
        last_bar_ts=bars[0].dt.timestamp(),
        now_ts=bars[0].dt.timestamp(),
    )
    decision: RiskDecision = enforce_guards(config.symbol, broker_intent.quantity, float(signal_price), limits, ctx)
    if not decision.allowed:
        raise RuntimeError(f"Regression guard rejected order: {decision.reason}")

    adapter_key, adapter = _select_adapter(config, clock)
    adapter_logs: List[dict] = []

    if adapter_key == "paper":
        broker = _configure_paper_broker(metadata, account, config.symbol, clock)
        order = broker.place_order(broker_intent)

        equity_curve = [
            {
                "ts": bars[0].dt - dt.timedelta(minutes=1),
                "equity": broker.get_account().equity,
                "cash": broker.get_account().cash,
            }
        ]
        exposures: List[float] = [0.0]
        fills_payload: List[Dict[str, object]] = []
        trade_payloads: List[Dict[str, float]] = []

        for bar in bars:
            clock.current = bar.dt
            broker.on_market_data(bar.symbol, bar.close, bar.dt.timestamp())
            snapshot = broker.get_account()
            positions = broker.get_positions()
            exposures.append(sum(abs(pos.quantity) for pos in positions))
            equity_curve.append({"ts": bar.dt, "equity": snapshot.equity, "cash": snapshot.cash})
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
        account_payload = _account_payload(final_snapshot.cash, final_snapshot.equity, broker, final_positions)
        positions_payload = _positions_payload(final_positions)
    else:
        assert adapter is not None
        adapter.place_order(broker_intent)
        if hasattr(adapter, "logs"):
            adapter_logs.extend(list(getattr(adapter, "logs")))
        logged = len(adapter_logs)

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
            if hasattr(adapter, "logs"):
                current_logs = list(getattr(adapter, "logs"))
                if len(current_logs) > logged:
                    adapter_logs.extend(current_logs[logged:])
                    logged = len(current_logs)
            equity_curve.append({"ts": bar.dt, "equity": float(account.equity), "cash": float(account.cash)})
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

    config_payload = {
        "symbol": config.symbol,
        "seed": config.seed,
        "label": config.label,
        "adapter_mode": adapter_key,
        "adapter_name": config.adapter_name,
        "dataset": str(config.dataset_dir),
    }

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
    )

    adapter_log_path: Path | None = None
    if adapter_key != "paper":
        adapter_log_path = _write_adapter_logs(paths, adapter_logs, adapter_key)

    return RegressionArtifacts(snapshot=paths.snapshot_file, equity_curve=equity_path, metrics=metrics_path, adapter_logs=adapter_log_path)


def _compare(baseline: Path, output: Path) -> str | None:
    if not baseline.exists():
        return f"Baseline missing: {baseline}"
    if output.read_bytes() == baseline.read_bytes():
        return None
    diff = difflib.unified_diff(
        baseline.read_text(encoding="utf-8").splitlines(),
        output.read_text(encoding="utf-8").splitlines(),
        fromfile=str(baseline),
        tofile=str(output),
        lineterm="",
    )
    return "\n".join(diff)


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
) -> RegressionResult:
    dataset = dataset_dir or DEFAULT_FIXTURE_DIR
    output_root.mkdir(parents=True, exist_ok=True)
    paths = prepare_seeded_run_paths(seed, label, base_dir=output_root)
    config = RegressionConfig(dataset_dir=dataset, symbol=symbol, seed=seed, label=label, adapter_mode=adapter_mode, adapter_name=adapter_name)
    artifacts = _run_pipeline(paths, config)

    tracked = {
        "snapshot": artifacts.snapshot,
        "equity_curve": artifacts.equity_curve,
        "metrics": artifacts.metrics,
    }
    if artifacts.adapter_logs is not None:
        tracked["adapter_logs"] = artifacts.adapter_logs

    diff_map: Dict[str, str] = {}
    for name, artifact in tracked.items():
        baseline_path = baseline_dir / artifact.name
        if update_baseline:
            if not allow_refresh:
                raise RuntimeError("Baseline refresh requested without confirmation flag")
            baseline_path.parent.mkdir(parents=True, exist_ok=True)
            baseline_path.write_bytes(artifact.read_bytes())
            continue
        diff = _compare(baseline_path, artifact)
        if diff:
            diff_map[name] = diff
    matches = not diff_map and not update_baseline
    return RegressionResult(run_id=paths.run_id, artifacts=artifacts, matches_baseline=matches, diffs=diff_map)


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Logos live regression smoke test")
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
        parser.error("--refresh-baseline also requires --confirm-refresh to avoid accidental updates")
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

"""Deterministic dry-run regression harness for live components."""

from __future__ import annotations

import argparse
import difflib
import json
import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterable, List, Mapping

from .broker_base import OrderIntent as BrokerOrderIntent, SymbolMeta
from .broker_paper import PaperBrokerAdapter
from .data_feed import Bar, FixtureReplayFeed
from .persistence import prepare_seeded_run_paths, write_equity_and_metrics, write_snapshot
from .risk import RiskContext, RiskDecision, RiskLimits, enforce_guards
from .time import MockTimeProvider
from .translator import SymbolMetadataRegistry, Translator
from .types import Account, OrderSide, Position, SizingInstruction

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"
LIVE_FIXTURES_DIR = FIXTURES_DIR / "live"
BASELINE_DIR = FIXTURES_DIR / "regression" / "smoke"
DATASET_PATH = LIVE_FIXTURES_DIR / "aapl_1m_fixture.csv"
SYMBOLS_PATH = LIVE_FIXTURES_DIR / "symbols.yaml"
ACCOUNT_PATH = LIVE_FIXTURES_DIR / "account_start.json"

DEFAULT_SEED = 7
DEFAULT_LABEL = "regression-smoke"
TARGET_SYMBOL = "AAPL"


@dataclass(frozen=True)
class RegressionArtifacts:
    snapshot: Path
    equity_curve: Path
    metrics: Path


@dataclass(frozen=True)
class RegressionResult:
    run_id: str
    artifacts: RegressionArtifacts
    matches_baseline: bool
    diffs: Dict[str, str]


def _load_account() -> Account:
    payload = json.loads(ACCOUNT_PATH.read_text(encoding="utf-8"))
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


def _build_feed(clock: MockTimeProvider) -> FixtureReplayFeed:
    return FixtureReplayFeed(
        dataset=DATASET_PATH,
        time_provider=clock,
        max_age_seconds=600,
        max_retries=0,
    )


def _configure_broker(metadata, account: Account, clock: MockTimeProvider) -> PaperBrokerAdapter:
    broker = PaperBrokerAdapter(
        time_provider=clock,
        starting_cash=float(account.cash),
        slippage_bps=0.0,
        fee_bps=0.0,
    )
    symbol_meta = metadata.resolve(TARGET_SYMBOL)
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
        bootstrap_payload = {
            symbol: {
                "qty": float(pos.quantity),
                "avg_price": float(pos.average_price),
                "realized": 0.0,
            }
            for symbol, pos in account.positions.items()
        }
        broker.bootstrap_positions(bootstrap_payload)
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


def _account_payload(cash: float, equity: float, broker: PaperBrokerAdapter, positions: List) -> Mapping[str, float]:  # type: ignore[no-untyped-def]
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


def _run_pipeline(paths) -> RegressionArtifacts:  # type: ignore[no-untyped-def]
    clock = MockTimeProvider(current=dt.datetime(2024, 1, 1, 9, 33, tzinfo=dt.timezone.utc))
    account = _load_account()
    feed = _build_feed(clock)
    bars: List[Bar] = feed.fetch_bars(TARGET_SYMBOL, "1m", since=None)
    if len(bars) < 2:
        raise RuntimeError("Regression feed_fixture requires at least two bars")

    metadata = SymbolMetadataRegistry.from_yaml(SYMBOLS_PATH)
    translator = Translator(metadata)
    broker = _configure_broker(metadata, account, clock)

    signal_price = Decimal(str(bars[0].close))
    sizing = SizingInstruction.fixed_notional(Decimal("1000"))
    intent = translator.build_order_intent(
        signal_symbol=TARGET_SYMBOL,
        side=OrderSide.BUY,
        signal_price=signal_price,
        sizing=sizing,
        account=account,
    )
    broker_intent = _to_broker_intent(intent)

    limits = RiskLimits(
        max_notional=5_000.0,
        symbol_position_limits={TARGET_SYMBOL: 100.0},
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
        TARGET_SYMBOL,
        broker_intent.quantity,
        float(signal_price),
        limits,
        ctx,
    )
    if not decision.allowed:
        raise RuntimeError(f"Regression guard rejected order: {decision.reason}")

    order = broker.place_order(broker_intent)

    initial_account = broker.get_account()
    equity_curve = [
        {
            "ts": bars[0].dt - dt.timedelta(minutes=1),
            "equity": initial_account.equity,
            "cash": initial_account.cash,
        }
    ]
    exposures: List[float] = [0.0]
    fills_payload: List[Dict[str, object]] = []
    trade_payloads: List[Dict[str, float]] = []

    for bar in bars:
        clock.current = bar.dt
        broker.on_market_data(bar.symbol, bar.close, bar.dt.timestamp())
        account_snapshot = broker.get_account()
        positions = broker.get_positions()
        exposures.append(sum(abs(pos.quantity) for pos in positions))
        equity_curve.append(
            {
                "ts": bar.dt,
                "equity": account_snapshot.equity,
                "cash": account_snapshot.cash,
            }
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

    final_account = broker.get_account()
    final_positions = broker.get_positions()

    account_payload = _account_payload(final_account.cash, final_account.equity, broker, final_positions)
    positions_payload = _positions_payload(final_positions)
    config_payload = {
        "symbol": TARGET_SYMBOL,
        "seed": DEFAULT_SEED,
        "label": DEFAULT_LABEL,
        "notional": float(sizing.value),
        "dataset": DATASET_PATH.name,
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

    return RegressionArtifacts(snapshot=paths.snapshot_file, equity_curve=equity_path, metrics=metrics_path)


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
) -> RegressionResult:
    output_root.mkdir(parents=True, exist_ok=True)
    paths = prepare_seeded_run_paths(DEFAULT_SEED, DEFAULT_LABEL, base_dir=output_root)
    artifacts = _run_pipeline(paths)

    diff_map: Dict[str, str] = {}
    for name, artifact in {
        "snapshot": artifacts.snapshot,
        "equity_curve": artifacts.equity_curve,
        "metrics": artifacts.metrics,
    }.items():
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
    return RegressionResult(
        run_id=paths.run_id,
        artifacts=artifacts,
        matches_baseline=matches,
        diffs=diff_map,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Logos live regression smoke test")
    parser.add_argument("--output-dir", type=Path, default=Path("runs/live/regression"))
    parser.add_argument("--baseline", type=Path, default=BASELINE_DIR)
    parser.add_argument("--refresh-baseline", action="store_true")
    parser.add_argument("--confirm-refresh", action="store_true")
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
    )
    for name, artifact in {
        "snapshot": result.artifacts.snapshot,
        "equity_curve": result.artifacts.equity_curve,
        "metrics": result.artifacts.metrics,
    }.items():
        print(f"{name}: {artifact}")
    if not result.matches_baseline and not args.refresh_baseline:
        print("Regression deviated from baseline", flush=True)
        for name, diff in result.diffs.items():
            print(f"\n[name={name}]\n{diff}")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

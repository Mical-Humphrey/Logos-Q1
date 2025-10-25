from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Mapping, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

from core.io import dirs as core_dirs

from logos.backtest.engine import run_backtest
from logos.cli import periods_per_year
from logos.data_loader import get_prices
from logos.metrics import (
    deflated_sharpe_ratio,
    probabilistic_sharpe_ratio,
)
from logos.paths import RUNS_DIR, safe_slug
from logos.strategies import STRATEGIES
from logos.window import Window

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class WalkForwardConfig:
    strategy: str
    symbol: str
    asset_class: str = "equity"
    interval: str = "1d"
    window_size: int = 252
    train_fraction: float = 0.6
    step: int | None = None
    params: Mapping[str, object] = field(default_factory=dict)
    dollar_per_trade: float = 10_000.0
    slip_bps: float = 1.0
    commission_per_share: float = 0.0035
    fee_bps: float = 5.0
    fx_pip_size: float = 0.0001
    min_oos_sharpe: float = 0.0
    max_oos_drawdown: float = -0.5
    stress_slip_multiplier: float = 2.0
    stress_fee_multiplier: float = 1.5
    missing_data_stride: int = 5

    def __post_init__(self) -> None:
        if self.train_fraction <= 0 or self.train_fraction >= 1:
            raise ValueError("train_fraction must be in (0,1)")
        if self.window_size <= 10:
            raise ValueError("window_size must be > 10")
        if self.step is not None and self.step <= 0:
            raise ValueError("step must be positive when provided")
        if self.missing_data_stride < 1:
            raise ValueError("missing_data_stride must be >= 1")


@dataclass(slots=True)
class WalkForwardWindowSummary:
    index: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    oos_start: pd.Timestamp
    oos_end: pd.Timestamp
    train_metrics: Dict[str, float]
    oos_metrics: Dict[str, float]
    guard_metrics: Dict[str, float]
    stress_metrics: Dict[str, float]
    passed_oos: bool
    passed_stress: bool

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "index": self.index,
            "train_start": self.train_start.isoformat(),
            "train_end": self.train_end.isoformat(),
            "oos_start": self.oos_start.isoformat(),
            "oos_end": self.oos_end.isoformat(),
            "passed_oos": self.passed_oos,
            "passed_stress": self.passed_stress,
        }
        payload.update({f"train_{k}": v for k, v in self.train_metrics.items()})
        payload.update({f"oos_{k}": v for k, v in self.oos_metrics.items()})
        payload.update({f"guard_{k}": v for k, v in self.guard_metrics.items()})
        payload.update({f"stress_{k}": v for k, v in self.stress_metrics.items()})
        return payload


@dataclass(slots=True)
class WalkForwardReport:
    config: WalkForwardConfig
    windows: List[WalkForwardWindowSummary]

    def aggregate_metrics(self) -> Dict[str, float]:
        if not self.windows:
            return {}
        keys = {key for window in self.windows for key in window.oos_metrics.keys()}
        aggregate: Dict[str, float] = {}
        for key in sorted(keys):
            values = [window.oos_metrics.get(key, 0.0) for window in self.windows]
            if values:
                aggregate[f"oos_avg_{key}"] = sum(values) / len(values)
        return aggregate

    def guard_failures(self) -> Dict[str, int]:
        return {
            "oos_failures": sum(
                0 if window.passed_oos else 1 for window in self.windows
            ),
            "stress_failures": sum(
                0 if window.passed_stress else 1 for window in self.windows
            ),
        }

    def to_frame(self) -> pd.DataFrame:
        records = [window.to_dict() for window in self.windows]
        if not records:
            return pd.DataFrame()
        return pd.DataFrame.from_records(records)

    def write_outputs(self, output_dir: Path) -> None:
        core_dirs.ensure_dir(output_dir)
        frame = self.to_frame()
        if not frame.empty:
            frame.to_csv(output_dir / "windows.csv", index=False)
        payload = {
            "config": asdict(self.config),
            "windows": [window.to_dict() for window in self.windows],
            "aggregate": self.aggregate_metrics(),
            "guards": self.guard_failures(),
        }
        (output_dir / "summary.json").write_text(json.dumps(payload, indent=2))
        guards = self.guard_failures()
        aggregate = self.aggregate_metrics()
        (output_dir / "overview.md").write_text(
            _render_markdown(self, aggregate, guards)
        )
        (output_dir / "overview.html").write_text(
            _render_html(self, frame, aggregate, guards)
        )


def _default_step(window_size: int, train_fraction: float) -> int:
    train_len = int(window_size * train_fraction)
    return max(train_len // 2, 1)


def _strategy_callable(strategy: str):
    if strategy not in STRATEGIES:
        raise KeyError(f"Unknown strategy '{strategy}'")
    return STRATEGIES[strategy]


def _stress_signals(signals: pd.Series, stride: int) -> pd.Series:
    if stride <= 1:
        return signals.copy()
    stressed = signals.copy()
    stressed.iloc[::stride] = 0
    return stressed


def _stress_metrics(
    prices: pd.DataFrame,
    signals: pd.Series,
    *,
    config: WalkForwardConfig,
    periods_per_year_val: int,
) -> Dict[str, float]:
    stressed_signals = _stress_signals(signals, config.missing_data_stride)
    result = run_backtest(
        prices=prices,
        signals=stressed_signals,
        dollar_per_trade=config.dollar_per_trade,
        slip_bps=config.slip_bps * config.stress_slip_multiplier,
        commission_per_share_rate=config.commission_per_share,
        fee_bps=config.fee_bps * config.stress_fee_multiplier,
        fx_pip_size=config.fx_pip_size,
        asset_class=config.asset_class,
        periods_per_year=periods_per_year_val,
    )
    return result["metrics"]


def run_walk_forward(
    prices: pd.DataFrame,
    config: WalkForwardConfig,
    *,
    output_dir: Path | None = None,
) -> WalkForwardReport:
    if prices.empty:
        raise ValueError("prices dataframe is empty")
    if "Close" not in prices.columns:
        raise ValueError("prices must include a 'Close' column")

    df = prices.sort_index()
    step = config.step or _default_step(config.window_size, config.train_fraction)
    ppy = periods_per_year(config.asset_class, config.interval)
    strat_fn = _strategy_callable(config.strategy)

    window_summaries: List[WalkForwardWindowSummary] = []
    total = len(df)
    train_len = int(config.window_size * config.train_fraction)
    oos_len = config.window_size - train_len
    if train_len <= 0 or oos_len <= 0:
        raise ValueError("window split produces empty train or OOS slice")

    for idx, start in enumerate(range(0, total - config.window_size + 1, step)):
        end = start + config.window_size
        window = df.iloc[start:end]
        train = window.iloc[:train_len]
        oos = window.iloc[train_len:]
        if train.empty or oos.empty:
            continue

        train_signals = strat_fn(train, **config.params)
        oos_signals = strat_fn(oos, **config.params)

        train_result = run_backtest(
            prices=train,
            signals=train_signals,
            dollar_per_trade=config.dollar_per_trade,
            slip_bps=config.slip_bps,
            commission_per_share_rate=config.commission_per_share,
            fee_bps=config.fee_bps,
            fx_pip_size=config.fx_pip_size,
            asset_class=config.asset_class,
            periods_per_year=ppy,
        )

        oos_result = run_backtest(
            prices=oos,
            signals=oos_signals,
            dollar_per_trade=config.dollar_per_trade,
            slip_bps=config.slip_bps,
            commission_per_share_rate=config.commission_per_share,
            fee_bps=config.fee_bps,
            fx_pip_size=config.fx_pip_size,
            asset_class=config.asset_class,
            periods_per_year=ppy,
        )

        returns = oos_result["returns"]
        guard_metrics = {
            "psr": probabilistic_sharpe_ratio(returns, periods_per_year=ppy),
            "dsr": deflated_sharpe_ratio(returns, periods_per_year=ppy),
        }

        stress_metrics = _stress_metrics(
            oos,
            oos_signals,
            config=config,
            periods_per_year_val=ppy,
        )

        passed_oos = (
            oos_result["metrics"].get("Sharpe", 0.0) >= config.min_oos_sharpe
            and oos_result["metrics"].get("MaxDD", 0.0) >= config.max_oos_drawdown
        )
        passed_stress = stress_metrics.get("CAGR", 0.0) >= 0.0

        summary = WalkForwardWindowSummary(
            index=idx,
            train_start=train.index[0],
            train_end=train.index[-1],
            oos_start=oos.index[0],
            oos_end=oos.index[-1],
            train_metrics=train_result["metrics"],
            oos_metrics=oos_result["metrics"],
            guard_metrics=guard_metrics,
            stress_metrics=stress_metrics,
            passed_oos=passed_oos,
            passed_stress=passed_stress,
        )
        window_summaries.append(summary)

    report = WalkForwardReport(config=config, windows=window_summaries)

    if output_dir is None:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        slug = f"{ts}_{safe_slug(config.symbol)}_{safe_slug(config.strategy)}_wf"
        output_dir = RUNS_DIR / "research" / "walk_forward" / slug
    report.write_outputs(output_dir)
    return report


def _render_markdown(
    report: WalkForwardReport,
    aggregate: Dict[str, float],
    guards: Dict[str, int],
) -> str:
    config_payload = json.dumps(asdict(report.config), indent=2)
    lines = ["# Walk-Forward Report", ""]
    lines.append("## Configuration")
    lines.append("```json")
    lines.extend(config_payload.splitlines())
    lines.append("```")
    lines.append("")
    lines.append("## Aggregate OOS Metrics")
    if aggregate:
        for key, value in aggregate.items():
            lines.append(f"- **{key}**: {value:.4f}")
    else:
        lines.append("- No windows evaluated")
    lines.append("")
    lines.append("## Guard Failures")
    lines.append(f"- OOS windows failing gates: {guards['oos_failures']}")
    lines.append(f"- Stress windows failing gates: {guards['stress_failures']}")
    return "\n".join(lines)


def _render_html(
    report: WalkForwardReport,
    frame: pd.DataFrame,
    aggregate: Dict[str, float],
    guards: Dict[str, int],
) -> str:
    config_rows = "".join(
        f"<tr><th>{key}</th><td>{_format_cell(value)}</td></tr>"
        for key, value in sorted(asdict(report.config).items())
    )
    if aggregate:
        aggregate_rows = "".join(
            f"<tr><th>{key}</th><td>{_format_numeric(value)}</td></tr>"
            for key, value in aggregate.items()
        )
    else:
        aggregate_rows = "<tr><td colspan=2>No windows evaluated</td></tr>"
    guard_rows = "".join(
        f"<tr><th>{key}</th><td>{value}</td></tr>" for key, value in guards.items()
    )
    table_html = (
        frame.to_html(index=False, float_format=lambda x: f"{x:.4f}")
        if not frame.empty
        else "<p>No evaluated windows.</p>"
    )
    template = """<html>
<head>
  <meta charset=\"utf-8\" />
  <title>Walk-Forward Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem; color: #1f2933; }}
    h1, h2 {{ color: #102a43; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 1.5rem; }}
    th, td {{ border: 1px solid #d9e2ec; padding: 0.5rem; text-align: left; }}
    th {{ background-color: #f0f4f8; }}
    code {{ font-size: 0.9rem; }}
  </style>
</head>
<body>
  <h1>Walk-Forward Report</h1>
  <h2>Configuration</h2>
  <table>
    <tbody>
      {config_rows}
    </tbody>
  </table>
  <h2>Aggregate OOS Metrics</h2>
  <table>
    <tbody>
      {aggregate_rows}
    </tbody>
  </table>
  <h2>Guard Failures</h2>
  <table>
    <tbody>
      {guard_rows}
    </tbody>
  </table>
  <h2>Window Details</h2>
  {table_html}
</body>
</html>
""".strip()
    return template.format(
        config_rows=config_rows,
        aggregate_rows=aggregate_rows,
        guard_rows=guard_rows,
        table_html=table_html,
    )


def _format_cell(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.4f}"
    if isinstance(value, Mapping):
        return json.dumps(value)
    if isinstance(value, (list, tuple, set)):
        return json.dumps(list(value))
    return str(value)


def _format_numeric(value: float) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.4f}"
    return str(value)


def _parse_params(pairs: Sequence[str]) -> Dict[str, object]:
    parsed: Dict[str, object] = {}
    for token in pairs:
        if "=" not in token:
            raise ValueError(f"Invalid parameter '{token}'; expected key=value")
        key, raw = token.split("=", 1)
        parsed[key] = _coerce_value(raw)
    return parsed


def _coerce_value(raw: str) -> object:
    lowered = raw.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    for cast in (int, float):
        try:
            return cast(raw)
        except ValueError:
            continue
    return raw


def _load_prices_from_args(args: argparse.Namespace) -> pd.DataFrame:
    window = Window.from_bounds(start=args.start, end=args.end, zone=ZoneInfo(args.tz))
    return get_prices(
        args.symbol,
        window,
        interval=args.interval,
        asset_class=args.asset_class,
        allow_synthetic=args.allow_synthetic,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run walk-forward validation")
    parser.add_argument("strategy", help="Strategy name registered with Logos")
    parser.add_argument("symbol", help="Symbol to load prices for")
    parser.add_argument("start", help="Inclusive start date (YYYY-MM-DD)")
    parser.add_argument("end", help="Exclusive end date (YYYY-MM-DD)")
    parser.add_argument(
        "--interval",
        default="1d",
        help="Bar interval for price data (default: 1d)",
    )
    parser.add_argument(
        "--asset-class",
        default="equity",
        help="Asset class for pricing model (equity, crypto, forex)",
    )
    parser.add_argument(
        "--params",
        nargs="*",
        default=(),
        metavar="KEY=VALUE",
        help="Override strategy parameters",
    )
    parser.add_argument(
        "--window-size",
        type=int,
        default=252,
        help="Total bars per walk-forward window",
    )
    parser.add_argument(
        "--train-fraction",
        type=float,
        default=0.6,
        help="Fraction of window reserved for training",
    )
    parser.add_argument(
        "--step",
        type=int,
        help="Override step forward between windows",
    )
    parser.add_argument(
        "--min-oos-sharpe",
        type=float,
        default=0.0,
        help="Minimum out-of-sample Sharpe to accept window",
    )
    parser.add_argument(
        "--max-oos-drawdown",
        type=float,
        default=-0.5,
        help="Maximum acceptable out-of-sample drawdown (negative)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Optional directory for outputs (defaults under runs/)",
    )
    parser.add_argument(
        "--tz",
        default="UTC",
        help="Timezone for window bounds (default: UTC)",
    )
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="Permit synthetic price generation when data missing",
    )

    args = parser.parse_args(argv)
    params = _parse_params(args.params)

    prices = _load_prices_from_args(args)
    config = WalkForwardConfig(
        strategy=args.strategy,
        symbol=args.symbol,
        asset_class=args.asset_class,
        interval=args.interval,
        window_size=args.window_size,
        train_fraction=args.train_fraction,
        step=args.step,
        params=params,
        min_oos_sharpe=args.min_oos_sharpe,
        max_oos_drawdown=args.max_oos_drawdown,
    )

    report = run_walk_forward(prices, config, output_dir=args.output_dir)
    guards = report.guard_failures()
    aggregate = report.aggregate_metrics()
    logger.info(
        "Completed walk-forward: windows=%d oos_failures=%d stress_failures=%d",
        len(report.windows),
        guards.get("oos_failures", 0),
        guards.get("stress_failures", 0),
    )
    if aggregate:
        top_key, top_value = max(aggregate.items(), key=lambda item: item[1])
        logger.info("Top aggregate metric: %s=%.4f", top_key, top_value)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())

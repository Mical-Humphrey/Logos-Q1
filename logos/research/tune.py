from __future__ import annotations

import argparse
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import itertools
from pathlib import Path
from typing import Dict, List, Mapping, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

from core.io import dirs as core_dirs

from logos.backtest.engine import run_backtest
from logos.cli import periods_per_year
from logos.data_loader import get_prices
from logos.metrics import deflated_sharpe_ratio, probabilistic_sharpe_ratio
from logos.paths import RUNS_DIR, safe_slug
from logos.research.registry import ModelRegistry
from logos.strategies import STRATEGIES
from logos.window import Window

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TuningConfig:
    strategy: str
    symbol: str
    asset_class: str = "equity"
    interval: str = "1d"
    param_grid: Mapping[str, Sequence[object]] = field(default_factory=dict)
    oos_fraction: float = 0.25
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
    top_n: int = 5

    def __post_init__(self) -> None:
        if not self.param_grid:
            raise ValueError("param_grid must contain at least one parameter")
        if self.oos_fraction <= 0 or self.oos_fraction >= 0.5:
            raise ValueError("oos_fraction must be in (0, 0.5)")
        if self.top_n <= 0:
            raise ValueError("top_n must be positive")


@dataclass(slots=True)
class TrialResult:
    params: Dict[str, object]
    train_metrics: Dict[str, float]
    oos_metrics: Dict[str, float]
    guard_metrics: Dict[str, float]
    stress_metrics: Dict[str, float]
    status: str

    def passed(self) -> bool:
        return self.status == "accepted"


@dataclass(slots=True)
class TuningResult:
    config: TuningConfig
    trials: List[TrialResult]

    def accepted(self) -> List[TrialResult]:
        return [trial for trial in self.trials if trial.passed()]

    def best_params(self) -> Dict[str, object] | None:
        accepted = self.accepted()
        if not accepted:
            return None
        sorted_trials = sorted(
            accepted,
            key=lambda t: t.oos_metrics.get("Sharpe", 0.0),
            reverse=True,
        )
        return sorted_trials[0].params

    def to_frame(self) -> pd.DataFrame:
        records = []
        for trial in self.trials:
            record = {
                "status": trial.status,
                **{f"param_{k}": v for k, v in trial.params.items()},
                **{f"train_{k}": v for k, v in trial.train_metrics.items()},
                **{f"oos_{k}": v for k, v in trial.oos_metrics.items()},
                **{f"guard_{k}": v for k, v in trial.guard_metrics.items()},
                **{f"stress_{k}": v for k, v in trial.stress_metrics.items()},
            }
            records.append(record)
        return pd.DataFrame.from_records(records)

    def write_outputs(self, output_dir: Path) -> None:
        core_dirs.ensure_dir(output_dir)
        frame = self.to_frame()
        if not frame.empty:
            frame.to_csv(output_dir / "trials.csv", index=False)
            sharpe_col = "oos_Sharpe"
            if sharpe_col in frame.columns and self.config.top_n > 0:
                top = frame.sort_values(sharpe_col, ascending=False).head(
                    self.config.top_n
                )
                top.to_csv(output_dir / "trials_top.csv", index=False)
        payload = {
            "config": asdict(self.config),
            "trials": [
                {
                    "status": trial.status,
                    "params": trial.params,
                    "train_metrics": trial.train_metrics,
                    "oos_metrics": trial.oos_metrics,
                    "guard_metrics": trial.guard_metrics,
                    "stress_metrics": trial.stress_metrics,
                }
                for trial in self.trials
            ],
            "best_params": self.best_params(),
        }
        (output_dir / "summary.json").write_text(json.dumps(payload, indent=2))
        markdown = _render_markdown_report(self)
        (output_dir / "overview.md").write_text(markdown)
        html = _render_html_report(self, frame)
        (output_dir / "overview.html").write_text(html)


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


def tune_parameters(
    prices: pd.DataFrame,
    config: TuningConfig,
    *,
    output_dir: Path | None = None,
) -> TuningResult:
    if prices.empty:
        raise ValueError("prices dataframe is empty")
    if "Close" not in prices.columns:
        raise ValueError("prices must include a 'Close' column")

    df = prices.sort_index()
    total = len(df)
    oos_len = max(int(total * config.oos_fraction), 1)
    if oos_len >= total:
        raise ValueError("oos_fraction too large for available data")
    train = df.iloc[:-oos_len]
    oos = df.iloc[-oos_len:]
    ppy = periods_per_year(config.asset_class, config.interval)
    strat_fn = _strategy_callable(config.strategy)

    param_names = list(config.param_grid.keys())
    param_values = [list(values) for values in config.param_grid.values()]
    combinations = list(itertools.product(*param_values))

    trials: List[TrialResult] = []
    for combo in combinations:
        params = dict(zip(param_names, combo))
        train_signals = strat_fn(train, **params)
        oos_signals = strat_fn(oos, **params)

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

        stress_signals = _stress_signals(oos_signals, config.missing_data_stride)
        stress_result = run_backtest(
            prices=oos,
            signals=stress_signals,
            dollar_per_trade=config.dollar_per_trade,
            slip_bps=config.slip_bps * config.stress_slip_multiplier,
            commission_per_share_rate=config.commission_per_share,
            fee_bps=config.fee_bps * config.stress_fee_multiplier,
            fx_pip_size=config.fx_pip_size,
            asset_class=config.asset_class,
            periods_per_year=ppy,
        )

        oos_sharpe = oos_result["metrics"].get("Sharpe", 0.0)
        oos_dd = oos_result["metrics"].get("MaxDD", 0.0)
        status = "accepted"
        if oos_sharpe < config.min_oos_sharpe or oos_dd < config.max_oos_drawdown:
            status = "rejected"
        elif stress_result["metrics"].get("CAGR", 0.0) < 0:
            status = "rejected"

        trial = TrialResult(
            params=params,
            train_metrics=train_result["metrics"],
            oos_metrics=oos_result["metrics"],
            guard_metrics=guard_metrics,
            stress_metrics=stress_result["metrics"],
            status=status,
        )
        trials.append(trial)

    trials.sort(key=lambda t: t.train_metrics.get("Sharpe", 0.0), reverse=True)
    result = TuningResult(config=config, trials=trials)

    if output_dir is None:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        slug = f"{ts}_{safe_slug(config.symbol)}_{safe_slug(config.strategy)}_tune"
        output_dir = RUNS_DIR / "research" / "tuning" / slug
    result.write_outputs(output_dir)
    return result


def _render_markdown_report(result: TuningResult) -> str:
    config_payload = json.dumps(asdict(result.config), indent=2)
    lines = ["# Tuning Report", ""]
    lines.append("## Configuration")
    lines.append("```json")
    lines.extend(config_payload.splitlines())
    lines.append("```")
    lines.append("")
    lines.append("## Accepted Trials")
    accepted = result.accepted()
    if not accepted:
        lines.append("- No trials met guard thresholds.")
    else:
        for trial in accepted[: result.config.top_n]:
            sharpe = trial.oos_metrics.get("Sharpe", 0.0)
            lines.append(
                f"- params={trial.params} | oos Sharpe={sharpe:.4f} | status={trial.status}"
            )
    return "\n".join(lines)


def _render_html_report(result: TuningResult, frame: pd.DataFrame) -> str:
    config_rows = "".join(
        f"<tr><th>{key}</th><td>{_format_cell(value)}</td></tr>"
        for key, value in sorted(asdict(result.config).items())
    )
    if frame.empty:
        table_html = "<p>No tuning trials evaluated.</p>"
    else:
        table_html = frame.to_html(index=False, float_format=lambda x: f"{x:.4f}")
    template = """<html>
<head>
  <meta charset=\"utf-8\" />
  <title>Tuning Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem; color: #1f2933; }}
    h1, h2 {{ color: #102a43; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 1.5rem; }}
    th, td {{ border: 1px solid #d9e2ec; padding: 0.5rem; text-align: left; }}
    th {{ background-color: #f0f4f8; }}
  </style>
</head>
<body>
  <h1>Tuning Report</h1>
  <h2>Configuration</h2>
  <table>
    <tbody>
      {config_rows}
    </tbody>
  </table>
  <h2>Trial Summary</h2>
  {table_html}
</body>
</html>
""".strip()
    return template.format(config_rows=config_rows, table_html=table_html)


def _format_cell(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.4f}"
    if isinstance(value, Mapping):
        return json.dumps(value)
    if isinstance(value, (list, tuple, set)):
        return json.dumps(list(value))
    return str(value)


def _parse_param_grid(entries: Sequence[str]) -> Mapping[str, Sequence[object]]:
    grid: Dict[str, List[object]] = {}
    for token in entries:
        if "=" not in token:
            raise ValueError(f"Invalid grid entry '{token}'; expected key=v1,v2")
        key, raw_values = token.split("=", 1)
        values = []
        for piece in raw_values.split(","):
            piece = piece.strip()
            if not piece:
                continue
            values.append(_coerce_value(piece))
        if not values:
            raise ValueError(f"Grid entry '{key}' has no values")
        grid[key] = values
    return grid


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


def _load_prices(args: argparse.Namespace) -> pd.DataFrame:
    window = Window.from_bounds(start=args.start, end=args.end, zone=ZoneInfo(args.tz))
    return get_prices(
        args.symbol,
        window,
        interval=args.interval,
        asset_class=args.asset_class,
        allow_synthetic=args.allow_synthetic,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grid-search parameter tuner")
    parser.add_argument("strategy", help="Strategy name registered with Logos")
    parser.add_argument("symbol", help="Symbol or ticker to load prices for")
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
        help="Asset class (equity, crypto, forex)",
    )
    parser.add_argument(
        "--grid",
        nargs="+",
        metavar="KEY=v1,v2",
        required=True,
        help="Parameter grid entries",
    )
    parser.add_argument(
        "--oos-fraction",
        type=float,
        default=0.25,
        help="Fraction of history reserved for out-of-sample evaluation",
    )
    parser.add_argument(
        "--min-oos-sharpe",
        type=float,
        default=0.0,
        help="Minimum out-of-sample Sharpe required to accept trial",
    )
    parser.add_argument(
        "--max-oos-drawdown",
        type=float,
        default=-0.5,
        help="Maximum acceptable out-of-sample drawdown (negative)",
    )
    parser.add_argument(
        "--missing-data-stride",
        type=int,
        default=5,
        help="Stride for zeroing signals during stress test",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=5,
        help="How many top trials to keep in CSV summary",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Optional output directory",
    )
    parser.add_argument(
        "--tz",
        default="UTC",
        help="Timezone for window bounds (default: UTC)",
    )
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="Permit synthetic price generation when remote data fails",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        help="Optional model registry JSON path",
    )
    parser.add_argument(
        "--register-note",
        default="",
        help="Note attached to registry entry",
    )
    parser.add_argument(
        "--data-hash",
        default="",
        help="Identifier describing the dataset snapshot used",
    )
    parser.add_argument(
        "--code-hash",
        default="",
        help="Identifier describing the code version used",
    )
    parser.add_argument(
        "--promote",
        action="store_true",
        help="Promote the best accepted trial to champion after registration",
    )
    parser.add_argument(
        "--promote-min-oos-sharpe",
        type=float,
        default=0.0,
        help="Minimum Sharpe required for promotion",
    )
    parser.add_argument(
        "--promote-max-oos-drawdown",
        type=float,
        default=-0.5,
        help="Maximum drawdown allowed for promotion",
    )

    args = parser.parse_args(argv)

    param_grid = _parse_param_grid(args.grid)
    prices = _load_prices(args)

    config = TuningConfig(
        strategy=args.strategy,
        symbol=args.symbol,
        asset_class=args.asset_class,
        interval=args.interval,
        param_grid=param_grid,
        oos_fraction=args.oos_fraction,
        min_oos_sharpe=args.min_oos_sharpe,
        max_oos_drawdown=args.max_oos_drawdown,
        missing_data_stride=args.missing_data_stride,
        top_n=args.top_n,
    )

    result = tune_parameters(prices, config, output_dir=args.output_dir)

    accepted = result.accepted()
    logger.info("Completed tuning with %d accepted trials", len(accepted))

    if args.registry:
        registry = ModelRegistry(args.registry)
        if not accepted:
            logger.warning("No accepted trials to register; skipping registry update")
        else:
            best = max(
                accepted,
                key=lambda trial: trial.oos_metrics.get("Sharpe", float("-inf")),
            )
            record = registry.add_candidate(
                strategy=args.strategy,
                symbol=args.symbol,
                params=best.params,
                metrics=best.oos_metrics,
                guard_metrics=best.guard_metrics,
                stress_metrics=best.stress_metrics,
                note=args.register_note,
                data_hash=args.data_hash or None,
                code_hash=args.code_hash or None,
            )
            logger.info("Registered candidate model %s", record.model_id)
            if args.promote:
                registry.promote(
                    record.model_id,
                    min_oos_sharpe=args.promote_min_oos_sharpe,
                    max_oos_drawdown=args.promote_max_oos_drawdown,
                )
                logger.info("Promoted model %s to champion", record.model_id)

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())

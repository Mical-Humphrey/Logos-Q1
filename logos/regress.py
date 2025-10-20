from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

from logos.live import regression


@dataclass(frozen=True)
class Scenario:
    name: str
    dataset: Path
    symbol: str


SCENARIOS: dict[str, Scenario] = {}

for _name, _symbol in (
    ("trending_up", "TRENDUP"),
    ("trending_down", "TRENDDN"),
    ("range_bound", "RANGE"),
):
    dataset_path = regression.PROJECT_ROOT / "tests" / "fixtures" / "live" / _name
    SCENARIOS[_name] = Scenario(name=_name, dataset=dataset_path, symbol=_symbol)

DEFAULT_SCENARIOS: Sequence[str] = tuple(SCENARIOS.keys())
DEFAULT_MODES: Sequence[str] = ("paper", "adapter:ccxt", "adapter:alpaca")
DEFAULT_BASELINE_ROOT = regression.PROJECT_ROOT / "tests" / "baselines" / "phase2"
DEFAULT_OUTPUT_ROOT = regression.PROJECT_ROOT / "runs" / "live" / "phase2"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Logos regression matrix against pinned baselines")
    parser.add_argument(
        "--scenarios",
        default=",".join(DEFAULT_SCENARIOS),
        help="Comma-separated scenarios to execute",
    )
    parser.add_argument(
        "--modes",
        default=",".join(DEFAULT_MODES),
        help="Comma-separated modes (paper, adapter:ccxt, adapter:alpaca)",
    )
    parser.add_argument("--seed", type=int, default=regression.DEFAULT_SEED, help="Seed used for deterministic runs")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_ROOT, help="Root directory for matrix outputs")
    parser.add_argument("--baseline-root", type=Path, default=DEFAULT_BASELINE_ROOT, help="Root directory containing pinned baselines")
    parser.add_argument("--refresh-baseline", action="store_true", help="Overwrite baselines with fresh outputs")
    parser.add_argument("--i-understand", action="store_true", help="Required confirmation when refreshing baselines")
    return parser


@dataclass
class _ModeSpec:
    raw: str
    adapter_mode: str
    adapter_name: str | None
    dir_name: str


def _parse_csv(value: str) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _resolve_modes(values: Iterable[str]) -> List[_ModeSpec]:
    resolved: List[_ModeSpec] = []
    for value in values:
        if value == "paper":
            resolved.append(_ModeSpec(raw=value, adapter_mode="paper", adapter_name=None, dir_name="paper"))
            continue
        if value.startswith("adapter:"):
            adapter = value.split(":", 1)[1]
            if adapter not in {"alpaca", "ccxt"}:
                raise ValueError(f"Unsupported adapter mode: {value}")
            dir_name = f"adapter_{adapter}"
            resolved.append(
                _ModeSpec(raw=value, adapter_mode="adapter", adapter_name=adapter, dir_name=dir_name)
            )
            continue
        raise ValueError(f"Unrecognised mode specification: {value}")
    return resolved


@dataclass
class _MatrixResult:
    scenario: Scenario
    mode: _ModeSpec
    baseline_dir: Path
    output_dir: Path
    matches: bool
    diffs: dict[str, str]


def _run_matrix(args: argparse.Namespace) -> List[_MatrixResult]:
    scenario_names = _parse_csv(args.scenarios)
    if not scenario_names:
        raise ValueError("No scenarios provided")
    unknown = [name for name in scenario_names if name not in SCENARIOS]
    if unknown:
        raise ValueError(f"Unknown scenarios requested: {', '.join(unknown)}")

    mode_specs = _resolve_modes(_parse_csv(args.modes))
    if not mode_specs:
        raise ValueError("No execution modes provided")

    if args.refresh_baseline and not args.i_understand:
        raise ValueError("Refreshing baselines requires --i-understand acknowledgement")

    results: List[_MatrixResult] = []
    for scenario_name in scenario_names:
        scenario = SCENARIOS[scenario_name]
        if not scenario.dataset.is_dir():
            raise FileNotFoundError(f"Scenario dataset missing: {scenario.dataset}")
        for mode in mode_specs:
            label = f"phase2-{scenario.name}-{mode.dir_name}"
            output_dir = args.output_dir / scenario.name / mode.dir_name
            baseline_dir = args.baseline_root / scenario.name / mode.dir_name
            baseline_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)
            result = regression.run_regression(
                output_root=output_dir,
                baseline_dir=baseline_dir,
                dataset_dir=scenario.dataset,
                symbol=scenario.symbol,
                seed=args.seed,
                label=label,
                adapter_mode=mode.adapter_mode,
                adapter_name=mode.adapter_name,
                update_baseline=args.refresh_baseline,
                allow_refresh=args.refresh_baseline and args.i_understand,
            )
            results.append(
                _MatrixResult(
                    scenario=scenario,
                    mode=mode,
                    baseline_dir=baseline_dir,
                    output_dir=output_dir,
                    matches=result.matches_baseline,
                    diffs=result.diffs,
                )
            )
    return results


def main(argv: List[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
        matrix_results = _run_matrix(args)
    except Exception as exc:  # pragma: no cover - defensive error formatting
        parser.error(str(exc))
        raise AssertionError

    print(f"metric_abs_tolerance={regression.METRIC_ABS_TOLERANCE}")
    print(f"scenarios={args.scenarios}")
    print(f"modes={args.modes}")

    exit_code = 0
    for record in matrix_results:
        status: str
        if args.refresh_baseline:
            status = "REFRESHED"
        else:
            status = "PASS" if record.matches and not record.diffs else "FAIL"
            if status == "FAIL":
                exit_code = 1
        print(
            " | ".join(
                [
                    f"scenario={record.scenario.name}",
                    f"mode={record.mode.raw}",
                    f"dataset={record.scenario.dataset}",
                    f"baseline={record.baseline_dir}",
                    f"status={status}",
                ]
            )
        )
        if record.diffs:
            for name, diff in record.diffs.items():
                print(f"  diff[{name}] {diff}")
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

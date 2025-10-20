from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Iterable, Tuple

from logos.live import regression


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute deterministic live regression runs")
    parser.add_argument("--dataset", type=Path, default=regression.DEFAULT_FIXTURE_DIR, help="Dataset directory containing bars.csv, symbols.yaml, account.json")
    parser.add_argument("--symbol", default=regression.DEFAULT_SYMBOL, help="Target symbol for the regression run")
    parser.add_argument("--mode", choices=["paper", "adapter"], default="paper", help="Execution mode: paper broker or dry-run adapter")
    parser.add_argument("--adapter", choices=["alpaca", "ccxt"], default=None, help="Dry-run adapter to use when --mode adapter")
    parser.add_argument("--run-label", dest="label", default="cli-regression", help="Label used for seeded output directories")
    parser.add_argument("--output-dir", type=Path, default=Path("runs/live/regression"), help="Root directory for regression artifacts")
    parser.add_argument("--baseline-dir", type=Path, default=Path("runs/live/regression_baseline"), help="Directory used for optional baseline comparisons")
    return parser


def _checksums(paths: Iterable[Path]) -> Iterable[Tuple[Path, str]]:
    import hashlib

    for path in paths:
        if path is None:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        yield path, digest


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    seed_env = os.getenv("LOGOS_SEED")
    try:
        seed = int(seed_env) if seed_env is not None else regression.DEFAULT_SEED
    except ValueError:
        parser.error("LOGOS_SEED must be an integer if provided")
        raise AssertionError  # unreachable, appease type checkers

    adapter_mode = "adapter" if args.mode == "adapter" else "paper"
    if adapter_mode == "adapter" and args.adapter is None:
        parser.error("--adapter is required when --mode adapter")

    result = regression.run_regression(
        output_root=args.output_dir,
        baseline_dir=args.baseline_dir,
        dataset_dir=args.dataset,
        symbol=args.symbol,
        seed=seed,
        label=args.label,
        adapter_mode=adapter_mode,
        adapter_name=args.adapter,
    )

    print(f"run_id={result.run_id}")
    print(f"mode={adapter_mode}")
    if args.adapter:
        print(f"adapter={args.adapter}")
    artifacts = [
        result.artifacts.snapshot,
        result.artifacts.equity_curve,
        result.artifacts.metrics,
        result.artifacts.adapter_logs,
    ]
    for path, digest in _checksums(artifacts):
        print(f"artifact={path} sha256={digest}")
    if result.diffs:
        for name, diff in result.diffs.items():
            print(f"diff:{name} -> {diff}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

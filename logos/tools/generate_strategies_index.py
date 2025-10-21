from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.contracts.generate_index import SIZE_LIMIT_BYTES, generate_strategies_index
from core.contracts.validate import validate_strategies_index


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the Logos strategies index contract file."
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output path for strategies/index.json",
    )
    parser.add_argument(
        "--version",
        default="v1",
        help="Contract version to generate (default: v1)",
    )
    parser.add_argument(
        "--size-limit-bytes",
        type=int,
        default=SIZE_LIMIT_BYTES,
        help="Maximum allowed size of the generated file in bytes.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = generate_strategies_index(
            out_path=args.out,
            version=args.version,
            size_limit_bytes=args.size_limit_bytes,
        )
        validate_strategies_index(payload, version=args.version)
    except Exception as exc:  # pragma: no cover - CLI error surface
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())

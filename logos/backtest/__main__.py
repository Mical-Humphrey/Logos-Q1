"""Entry point so `python -m logos.backtest` dispatches to the CLI backtest command."""
from __future__ import annotations
import sys

from ..cli import build_parser, cmd_backtest, load_settings


def main() -> None:
    """Forward module execution to the CLI backtest subcommand."""
    settings = load_settings()
    parser = build_parser(settings)
    args = parser.parse_args(["backtest", *sys.argv[1:]])
    cmd_backtest(args, settings=settings)


if __name__ == "__main__":
    main()

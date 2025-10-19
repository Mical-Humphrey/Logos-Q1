"""Entry point so `python -m logos.backtest` dispatches to the CLI backtest command."""
from __future__ import annotations
import sys

from ..cli import main as cli_main


def main() -> None:
    """Forward module execution to the CLI backtest subcommand."""
    cli_main(["backtest", *sys.argv[1:]])


if __name__ == "__main__":
    main()

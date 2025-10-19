"""Entry point so `python -m logos.backtest` dispatches to the CLI backtest command."""
# =============================================================================
# Purpose:
#   Provide a module-level shim that mirrors the `logos cli backtest` behavior.
#   Lets users run `python -m logos.backtest ...` without remembering the CLI name.
#
# Summary:
#   - Loads configuration defaults via logos.config
#   - Reuses cli.build_parser to ensure flag parity
#   - Injects the `backtest` subcommand before parsing and executing
# =============================================================================
from __future__ import annotations

import sys

from ..cli import build_parser, cmd_backtest, load_settings


def main() -> None:
    """Forward module execution to the CLI backtest subcommand."""
    settings = load_settings()

    # Rebuild the CLI parser so module invocation stays perfectly consistent
    # with calling `logos cli backtest` from the command line.
    parser = build_parser(settings)

    # Insert the subcommand name so argparse routes to the correct handler.
    args = parser.parse_args(["backtest", *sys.argv[1:]])
    cmd_backtest(args, settings=settings)


if __name__ == "__main__":
    main()

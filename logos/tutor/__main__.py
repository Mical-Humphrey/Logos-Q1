"""CLI shim so `python -m logos.tutor` launches the lesson engine."""
# =============================================================================
# Purpose:
#   Provide a friendly command-line entry point for Tutor Mode.
#   Users can discover available lessons or run one with optional plotting.
#
# Summary:
#   - Lists lessons when --lesson is omitted
#   - Passes the --lesson and --plot flags through to tutor.engine
#   - Keeps interface aligned with python -m module execution conventions
# =============================================================================
from __future__ import annotations

import argparse
from typing import Sequence

from .engine import available_lessons, lesson_catalog, run_lesson


def main(argv: Sequence[str] | None = None) -> None:
    """Parse arguments, list lessons, or launch the requested tutorial."""
    lessons = available_lessons()

    # Build the CLI parser with inline help so newcomers understand the knobs.
    parser = argparse.ArgumentParser(
        prog="logos.tutor",
        description="Interactive Logos-Q1 lessons that narrate quantitative trades",
    )
    parser.add_argument(
        "--lesson",
        choices=lessons,
        help="Which lesson to run (omit to list available options)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List tutor lessons with a short description and exit",
    )
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Render a price chart with entry/exit markers for visual learners",
    )
    parser.add_argument(
        "--explain-math",
        action="store_true",
        help="Print formula derivations and save explain.md alongside the transcript",
    )
    args = parser.parse_args(argv)

    if args.list or not args.lesson:
        # Present a short catalog table so learners can pick a lesson quickly.
        print("Available lessons:")
        for name, description in lesson_catalog():
            print(f"  - {name:<15} {description}")
        return

    # Otherwise, hand off to the tutor engine for the full narrated experience.
    run_lesson(args.lesson, plot=args.plot, explain_math=args.explain_math)


if __name__ == "__main__":
    main()

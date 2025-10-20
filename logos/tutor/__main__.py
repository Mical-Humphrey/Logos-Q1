import argparse
import logging
from datetime import datetime

from logos import paths
from logos.logging_setup import setup_app_logging
from .lessons import registry, run_lesson


def main(argv: list[str] | None = None) -> None:
    setup_app_logging(logging.INFO)
    parser = argparse.ArgumentParser(description="Logos Tutor Mode")
    parser.add_argument(
        "--lesson", type=str, help="Lesson name. Use --list to see options."
    )
    parser.add_argument(
        "--list", action="store_true", help="List available lessons and exit."
    )
    parser.add_argument("--plot", action="store_true", help="Generate annotated plots.")
    parser.add_argument(
        "--explain-math",
        action="store_true",
        help="Add math explanations to transcript and glossary.",
    )
    args = parser.parse_args(argv)

    if args.list or not args.lesson:
        print("Available lessons:", ", ".join(sorted(registry().keys())))
        if not args.lesson:
            return

    run_lesson(
        lesson_name=args.lesson,
        when=datetime.now(),
        do_plot=args.plot,
        explain_math=args.explain_math,
        base_dir=paths.RUNS_LESSONS_DIR,
    )


if __name__ == "__main__":
    main()

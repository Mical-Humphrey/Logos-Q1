from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
import logging

from logos.logging_setup import attach_run_file_handler, detach_handler
from logos.run_manager import TS_FMT
from logos.paths import ensure_dirs


@dataclass
class LessonContext:
    lesson: str
    run_dir: Path
    logs_dir: Path
    transcript_file: Path
    glossary_file: Path
    plots_dir: Path
    logger: logging.Logger
    log_handler: logging.Handler


def registry():
    # Register lessons here
    from .mean_reversion import (
        build_glossary as mr_gloss,
        generate_transcript as mr_transcript,
        generate_plots as mr_plots,
    )
    from .momentum import (
        build_glossary as mom_gloss,
        generate_transcript as mom_transcript,
        generate_plots as mom_plots,
    )
    from .pairs_trading import (
        build_glossary as pair_gloss,
        generate_transcript as pair_transcript,
        generate_plots as pair_plots,
    )

    return {
        "mean_reversion": {
            "build_glossary": mr_gloss,
            "generate_transcript": mr_transcript,
            "generate_plots": mr_plots,
        },
        "momentum": {
            "build_glossary": mom_gloss,
            "generate_transcript": mom_transcript,
            "generate_plots": mom_plots,
        },
        "pairs_trading": {
            "build_glossary": pair_gloss,
            "generate_transcript": pair_transcript,
            "generate_plots": pair_plots,
        },
    }


def _new_lesson_run(lesson: str, base_dir: Path, when: datetime) -> LessonContext:
    run_id = f"{when.strftime(TS_FMT)}_{lesson}"
    run_dir = base_dir / lesson / run_id
    logs_dir = run_dir / "logs"
    plots_dir = run_dir / "plots"
    ensure_dirs([run_dir, logs_dir, plots_dir])
    transcript_file = run_dir / "transcript.txt"
    glossary_file = run_dir / "glossary.json"

    logger = logging.getLogger(f"logos.tutor.{lesson}")
    handler = attach_run_file_handler(logs_dir / "run.log")
    return LessonContext(
        lesson,
        run_dir,
        logs_dir,
        transcript_file,
        glossary_file,
        plots_dir,
        logger,
        handler,
    )


def run_lesson(
    lesson_name: str, when: datetime, do_plot: bool, explain_math: bool, base_dir: Path
):
    lessons = registry()
    if lesson_name not in lessons:
        raise SystemExit(
            f"Unknown lesson: {lesson_name}. Available: {', '.join(sorted(lessons))}"
        )

    ctx = _new_lesson_run(lesson_name, base_dir, when)
    gloss = lessons[lesson_name]["build_glossary"](explain_math=explain_math)
    ctx.glossary_file.write_text(json.dumps(gloss, indent=2), encoding="utf-8")

    transcript = lessons[lesson_name]["generate_transcript"](
        glossary=gloss, explain_math=explain_math
    )
    ctx.transcript_file.write_text(transcript, encoding="utf-8")

    try:
        if do_plot:
            lessons[lesson_name]["generate_plots"](ctx)
        ctx.logger.info(
            "Lesson %s completed. Artifacts in %s", lesson_name, ctx.run_dir
        )
    finally:
        detach_handler(ctx.log_handler)

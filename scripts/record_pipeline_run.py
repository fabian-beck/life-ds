#!/usr/bin/env python3
"""Record a real generation run for the pipeline documentation.

This runs the actual generator — it calls the OpenAI API, costs money, and
overwrites that person's or story's data files exactly as a normal regeneration
would. Nothing is recorded without doing real work, which is the point: the
chart then shows the prompts as they are actually assembled, what came back,
how long each phase took and what it cost in tokens.

    python scripts/record_pipeline_run.py person "Ada Lovelace"
    python scripts/record_pipeline_run.py meta "Computing Pioneers" -- --skip-translate

Records land in `docs/pipeline/runs/` and are picked up by
`scripts/generate_pipeline_docs.py` on the next build.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, List, Sequence

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from config import enable_utf8_console  # noqa: E402
from pipeline_docs.capture import recording, write_record  # noqa: E402

RUNS_DIR = REPO_ROOT / "docs" / "pipeline" / "runs"

TARGETS = {
    "person": ("generate_person", "generate_person.py"),
    "meta": ("generate_meta_story", "generate_meta_story.py"),
}


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "target", choices=sorted(TARGETS), help="Which pipeline to run."
    )
    parser.add_argument("subject", help="Person name/id, or meta story topic title.")
    parser.add_argument(
        "--label",
        help="Name for this record (default: '<target>: <subject>').",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help=f"Output file (default: {RUNS_DIR}/<target>.json).",
    )
    parser.add_argument(
        "--truncate",
        type=int,
        default=4000,
        help=(
            "Characters kept per prompt/response before eliding the middle "
            "(default: 4000). Use 0 to keep everything — a Phase 1 prompt "
            "carries whole Wikipedia articles, so records get large."
        ),
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt (the run overwrites generated data).",
    )
    parser.add_argument(
        "rest",
        nargs=argparse.REMAINDER,
        help="Arguments passed through to the generator, after a '--'.",
    )
    return parser.parse_args(list(argv))


def _passthrough(rest: List[str]) -> List[str]:
    return rest[1:] if rest and rest[0] == "--" else rest


def main(argv: Sequence[str] | None = None) -> int:
    enable_utf8_console()
    args = parse_args(sys.argv[1:] if argv is None else argv)
    module_name, script_name = TARGETS[args.target]
    extra = _passthrough(args.rest)

    print(f"About to run: {script_name} {args.subject} {' '.join(extra)}".rstrip())
    print("This performs a REAL generation run: it calls the API and rewrites")
    print("the generated data files for this subject.")
    if not args.yes:
        answer = input("Continue? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Aborted.")
            return 1

    module: Any = __import__(module_name)
    argv_for_target = [script_name, args.subject, *extra]
    truncate = None if args.truncate <= 0 else args.truncate

    saved_argv = sys.argv
    exit_code = 0
    with recording(truncate=truncate) as recorder:
        try:
            sys.argv = argv_for_target
            result = module.main(
                argv_for_target[1:] if args.target == "person" else None
            )
            exit_code = int(result or 0)
        except SystemExit as stop:  # generate_meta_story exits directly
            exit_code = int(stop.code or 0)
        finally:
            sys.argv = saved_argv

    out = args.out or (RUNS_DIR / f"{args.target}.json")
    label = args.label or f"{args.target}: {args.subject}"
    write_record(recorder, label, out)
    total = sum(call["duration_s"] for call in recorder.records)
    print(
        f"\nRecorded {len(recorder.records)} model call(s), {total:.1f}s of API time."
    )
    print(f"Written to {out}")
    if exit_code:
        print(
            f"Note: the generator exited with code {exit_code}; the record is still usable."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

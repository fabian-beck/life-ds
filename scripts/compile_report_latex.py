#!/usr/bin/env python3
"""Compile the LaTeX rendering of the technical report to a PDF.

    python scripts/compile_report_latex.py                 # docs/report/latex/report.tex -> PDF
    python scripts/compile_report_latex.py --engine latexmk
    python scripts/compile_report_latex.py --out report.pdf

`generate_report.py` writes `docs/report/latex/report.tex` beside the page, and
`--figures` prints the drawn figures it includes. This script only runs a TeX
engine over what is there—after checking that every drawing the source
includes has been printed, since a LaTeX run that stops on a missing file says
less than a sentence naming the command that makes it.

The engine is whichever is installed: Tectonic, which fetches the packages it
needs on first use and is one binary to install, then `latexmk`, then a bare
`pdflatex` run twice for the page total in the running foot. Every one of them
produces the same document, because the source declares its faces per engine.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from config import enable_utf8_console  # noqa: E402
from pipeline_docs import latex, report, screenshots  # noqa: E402
from pipeline_docs import facts as facts_module  # noqa: E402
from pipeline_docs.introspect import scan_codebase  # noqa: E402
from pipeline_docs.model import build_payload  # noqa: E402
from pipeline_docs.summarize import cached_summaries  # noqa: E402

LATEX_DIR = latex.LATEX_DIR
DEFAULT_SOURCE = LATEX_DIR / "report.tex"
DEFAULT_OUT = LATEX_DIR / "report.pdf"
REPORT_SOURCE = REPO_ROOT / "docs" / "report" / "report.md"
SUMMARY_CACHE = REPO_ROOT / "docs" / "report" / "summaries.json"

ENGINES = ("tectonic", "latexmk", "pdflatex")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compile the LaTeX rendering of the technical report."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"LaTeX source to compile (default: {DEFAULT_SOURCE}).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"PDF to write (default: {DEFAULT_OUT}).",
    )
    parser.add_argument(
        "--engine",
        choices=ENGINES,
        help="TeX engine to use (default: the first of tectonic, latexmk, pdflatex found).",
    )
    parser.add_argument(
        "--skip-figure-check",
        action="store_true",
        help="Compile even when a drawn figure is missing or stale.",
    )
    return parser.parse_args(list(argv))


def find_engine(wanted: Optional[str]) -> Optional[str]:
    candidates = [wanted] if wanted else list(ENGINES)
    for name in candidates:
        if shutil.which(name):
            return name
    return None


def engine_command(engine: str, source: Path, out_dir: Path) -> List[List[str]]:
    """The runs one engine needs, each as an argument list."""
    if engine == "tectonic":
        return [["tectonic", "--outdir", str(out_dir), str(source)]]
    if engine == "latexmk":
        return [
            [
                "latexmk",
                "-pdf",
                "-interaction=nonstopmode",
                "-halt-on-error",
                f"-outdir={out_dir}",
                str(source),
            ]
        ]
    # `pdflatex` alone: twice, so the page total the running foot cites and
    # every cross-reference resolve.
    run = [
        "pdflatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-output-directory={out_dir}",
        str(source),
    ]
    return [run, run]


def page_count(path: Path) -> Optional[int]:
    """The page count from the PDF's page tree, or None if it cannot be read.

    A log line, not a contract: the `/Count` entry is uncompressed in the
    output of every engine used here, and a PDF that hides it still compiled.
    """
    counts = [
        int(match.group(1))
        for match in re.finditer(rb"/Count\s+(\d+)", path.read_bytes())
    ]
    return max(counts) if counts else None


def check_figures(source: Path) -> int:
    """Refuse to compile with a drawing missing; warn about a stale one."""
    codebase = scan_codebase()
    facts = facts_module.collect(codebase)
    try:
        document = report.compile_report(
            REPORT_SOURCE.read_text(encoding="utf-8"), facts
        )
    except report.ReportError as error:
        print(f"  ERROR in the authored report: {error}")
        return 1
    shots = screenshots.payload(screenshots.collect(document))
    payload = build_payload(
        codebase, cached_summaries(SUMMARY_CACHE), document, facts, shots
    )
    figures = latex.figures_of(document, payload)
    problems = latex.figure_problems(figures, source.parent / "figures")
    missing = 0
    for severity, where, message in problems:
        exported = "missing" if "has not been printed" in message else "stale"
        marker = "ERROR" if exported == "missing" else "warn "
        print(f"  [{marker}] {where}: {message}")
        if exported == "missing":
            missing += 1
    if not problems:
        print(f"  {len(figures)} drawn figure(s), every one printed and current.")
    return missing


def main(argv: Sequence[str] | None = None) -> int:
    enable_utf8_console()
    args = parse_args(sys.argv[1:] if argv is None else argv)

    if not args.source.is_file():
        print(f"No LaTeX source at {args.source}.")
        print("Write it first: python scripts/generate_report.py")
        return 1

    if not args.skip_figure_check:
        print("Checking the drawn figures ...")
        if check_figures(args.source):
            print(
                "\nPrint the missing drawings first: "
                "python scripts/generate_report.py --figures"
            )
            return 1

    engine = find_engine(args.engine)
    if engine is None:
        wanted = args.engine or " or ".join(ENGINES)
        print(f"No TeX engine found: {wanted} is not on PATH.")
        print(
            "Install Tectonic (https://tectonic-typesetting.github.io), which "
            "fetches the packages it needs on first use, or any TeX distribution "
            "with latexmk or pdflatex."
        )
        return 1

    out_dir = args.out.parent.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    print(
        f"Compiling {args.source.relative_to(REPO_ROOT).as_posix()} with {engine} ..."
    )
    for command in engine_command(engine, args.source.resolve(), out_dir):
        completed = subprocess.run(command, cwd=args.source.parent, check=False)
        if completed.returncode != 0:
            print(f"\n{engine} failed (exit {completed.returncode}).")
            return 1

    produced = out_dir / f"{args.source.stem}.pdf"
    if produced != args.out.resolve():
        if args.out.exists():
            args.out.unlink()
        produced.replace(args.out)
    pages = page_count(args.out)
    size_kb = args.out.stat().st_size / 1024
    print(
        f"\nWrote {args.out} ({size_kb:.0f} KB"
        + (f", {pages} pages)." if pages else ").")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

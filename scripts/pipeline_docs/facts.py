#!/usr/bin/env python3
"""What the report is allowed to cite, measured at build time.

The authored markdown never writes such a value down. It writes
`{{ app.languages }}` and this module supplies it, so a sentence about the
system cannot rot the way a hard-coded one would. Every fact carries the place
it was measured, which the page prints on hover—a claim in the report is
therefore always traceable to a file, a directory or a spec entry.

Facts are deliberately few: something is measured here because the prose argues
with it, not because it can be counted. Inventory is not argument. Corpus sizes
went first, then the pipeline's own tallies—how many steps, layers, dependency
edges, artifacts or schemas there happen to be today. Each was a number a reader
had to carry without ever being asked to use it, and each lent a measurement's
authority to a sentence that was only saying the system exists at some size. The
figures still show the shape those counts described, which is the form in which
a reader can actually use it. What is left names things rather than counting
them: which models the pipelines call, which languages the corpus is published
in. Anything that needs the AST lives in `introspect.py`
and reaches the report through `model.py` instead. A fact that cannot be
measured is omitted rather than guessed, and `validate.py` then fails the build
for the citation that referenced it—a missing number must never render as an
empty gap in a sentence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .introspect import Codebase

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Fact:
    """One citable measurement.

    `display` is what the sentence gets; `value` keeps the raw number so a
    component can chart it. `source` names where it was measured, in
    repo-relative terms, and is shown as the citation's tooltip.
    """

    key: str
    display: str
    source: str
    value: Optional[float] = None

    def to_json(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "display": self.display,
            "source": self.source,
            "value": self.value,
        }


def _files(directory: Path, pattern: str) -> List[Path]:
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob(pattern) if path.is_file())


# ---------------------------------------------------------------------------
# Measurements
# ---------------------------------------------------------------------------


def _pipeline_facts(codebase: Codebase) -> List[Fact]:
    # A resolved model reads like "gpt-5.6-terra (env OPENAI_MODEL)"; the report
    # cites the identifiers, and the drawer shows where each one came from.
    models = sorted(
        {
            (call.model_value or "").split(" (")[0].strip()
            for call in codebase.all_ai_calls()
            if call.model_value
        }
        - {""}
    )

    return [
        Fact(
            "pipeline.models",
            ", ".join(models) if models else "—",
            "resolved model arguments at each call site",
            len(models),
        ),
    ]


def _app_facts() -> List[Fact]:
    """What the application *is*, never how much of it there is."""
    src = REPO_ROOT / "src"
    locales = _files(src / "locales", "*.json")

    facts = [
        Fact(
            "app.languages",
            ", ".join(path.stem for path in locales) or "—",
            "src/locales/*.json filenames",
            len(locales),
        ),
    ]
    return facts


def collect(codebase: Codebase) -> Dict[str, Fact]:
    """Every citable fact, keyed by the name the markdown uses."""
    groups: List[List[Fact]] = [
        _pipeline_facts(codebase),
        _app_facts(),
    ]
    facts: Dict[str, Fact] = {}
    for group in groups:
        for fact in group:
            facts[fact.key] = fact
    return facts


def to_json(facts: Dict[str, Fact]) -> Dict[str, Any]:
    return {key: fact.to_json() for key, fact in sorted(facts.items())}

#!/usr/bin/env python3
"""Numbers the report is allowed to cite, measured at build time.

The authored markdown never writes a figure down. It writes `{{ app.locales }}`
and this module supplies the number, so a sentence about the system cannot rot
the way a hard-coded figure would. Every fact carries the place it was
measured, which the page prints on hover—a claim in the report is therefore
always traceable to a file, a directory or a spec entry.

Facts are deliberately few: a number is measured here because the prose argues
something with it, not because it can be counted. Corpus sizes were measured
here once and are not any more; how many biographies happen to exist today
carries no argument, and a report that recites it invites the reader to mistake
inventory for a finding. Anything that needs the AST lives in `introspect.py`
and reaches the report through `model.py` instead. A fact that cannot be
measured is omitted rather than guessed, and `validate.py` then fails the build
for the citation that referenced it—a missing number must never render as an
empty gap in a sentence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import spec
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
    person = [step for step in spec.STEPS if step.id.startswith("p_")]
    meta = [step for step in spec.STEPS if step.id.startswith("m_")]
    ai_steps = [step for step in spec.STEPS if step.kind == spec.AI]
    layers = _longest_paths()
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
    prompts = sum(len(facts.prompts) for facts in codebase.scripts.values())
    schemas = sum(len(facts.schemas) for facts in codebase.scripts.values())

    return [
        Fact(
            "pipeline.steps",
            str(len(spec.STEPS)),
            "pipeline_docs/spec.py",
            len(spec.STEPS),
        ),
        Fact(
            "pipeline.ai_steps",
            str(len(ai_steps)),
            "pipeline_docs/spec.py—steps of kind 'ai'",
            len(ai_steps),
        ),
        Fact(
            "pipeline.code_steps",
            str(len(spec.STEPS) - len(ai_steps)),
            "pipeline_docs/spec.py—steps of any non-AI kind",
            len(spec.STEPS) - len(ai_steps),
        ),
        Fact(
            "pipeline.person_steps",
            str(len(person)),
            "pipeline_docs/spec.py—steps drawn in the personal column",
            len(person),
        ),
        Fact(
            "pipeline.meta_steps",
            str(len(meta)),
            "pipeline_docs/spec.py—steps drawn in the meta column",
            len(meta),
        ),
        Fact(
            "pipeline.person_layers",
            str(_max_layer(person, layers)),
            "longest dependency path through the personal pipeline",
            _max_layer(person, layers),
        ),
        Fact(
            "pipeline.meta_layers",
            str(_max_layer(meta, layers)),
            "longest dependency path through the meta pipeline",
            _max_layer(meta, layers),
        ),
        Fact(
            "pipeline.edges",
            str(sum(len(step.depends_on) for step in spec.STEPS)),
            "pipeline_docs/spec.py—Step.depends_on entries",
            sum(len(step.depends_on) for step in spec.STEPS),
        ),
        Fact(
            "pipeline.groups",
            str(len(spec.GROUPS)),
            "pipeline_docs/spec.py—GROUPS",
            len(spec.GROUPS),
        ),
        Fact(
            "pipeline.artifacts",
            str(len(spec.ARTIFACTS)),
            "pipeline_docs/spec.py—ARTIFACTS",
            len(spec.ARTIFACTS),
        ),
        Fact(
            "pipeline.call_sites",
            str(len(codebase.all_ai_calls())),
            "AST scan of scripts/ for model calls",
            len(codebase.all_ai_calls()),
        ),
        Fact(
            "pipeline.prompt_builders",
            str(prompts),
            "AST scan of scripts/ for prompt-building functions",
            prompts,
        ),
        Fact(
            "pipeline.schemas",
            str(schemas),
            "AST scan of scripts/ for Pydantic output models",
            schemas,
        ),
        Fact(
            "pipeline.models",
            ", ".join(models) if models else "—",
            "resolved model arguments at each call site",
            len(models),
        ),
    ]


def _longest_paths() -> Dict[str, int]:
    """The same layer rule the chart applies, so prose and figure agree."""
    steps = {step.id: step for step in spec.STEPS}
    layers: Dict[str, int] = {}

    def layer(step_id: str) -> int:
        if step_id in layers:
            return layers[step_id]
        layers[step_id] = 0
        layers[step_id] = max(
            (layer(dep.on) + 1 for dep in steps[step_id].depends_on), default=0
        )
        return layers[step_id]

    for step_id in steps:
        layer(step_id)
    return layers


def _max_layer(steps: List[spec.Step], layers: Dict[str, int]) -> int:
    return max((layers[step.id] for step in steps), default=-1) + 1


def _app_facts() -> List[Fact]:
    """What the application *is*, never how much of it there is.

    Script, component and line counts used to be measured here and cited in the
    prose. They were dropped: they move with every refactor, support no claim
    the report makes, and lend a measurement's authority to a sentence that is
    really just saying the project exists. A count earns a place in this module
    by being the subject of an argument.
    """
    src = REPO_ROOT / "src"
    locales = _files(src / "locales", "*.json")

    facts = [
        Fact(
            "app.locales",
            str(len(locales)),
            "src/locales/*.json",
            len(locales),
        ),
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

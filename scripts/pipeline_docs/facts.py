#!/usr/bin/env python3
"""Numbers the report is allowed to cite, measured at build time.

The authored markdown never writes a figure down. It writes `{{ data.people }}`
and this module supplies the number, so a sentence about the size of the corpus
cannot rot the way a hard-coded "52 biographies" would. Every fact carries the
place it was measured, which the page prints on hover — a claim in the report is
therefore always traceable to a file, a directory or a spec entry.

Facts are deliberately cheap: directory listings, line counts, lengths of JSON
arrays. Anything that needs the AST lives in `introspect.py` and reaches the
report through `model.py` instead. A fact that cannot be measured is omitted
rather than guessed, and `validate.py` then fails the build for the citation
that referenced it — a missing number must never render as an empty gap in a
sentence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

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


def _thousands(number: float) -> str:
    return f"{int(number):,}".replace(",", " ")


def _safe(fn: Callable[[], Any], default: Any = None) -> Any:
    """Measurements run against a working tree, which may be incomplete."""
    try:
        return fn()
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return default


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _line_count(path: Path) -> int:
    return len(_read_text(path).splitlines())


def _files(directory: Path, pattern: str) -> List[Path]:
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob(pattern) if path.is_file())


def _lines_of(paths: Iterable[Path]) -> int:
    return sum(_line_count(path) for path in paths)


def _json_array_length(path: Path, *keys: str) -> Optional[int]:
    """Length of a nested array in a JSON file, or None if the path is absent."""
    if not path.is_file():
        return None
    data = _safe(lambda: json.loads(path.read_text(encoding="utf-8")))
    if data is None:
        return None
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    if isinstance(data, (list, dict)):
        return len(data)
    return None


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
            "pipeline_docs/spec.py — steps of kind 'ai'",
            len(ai_steps),
        ),
        Fact(
            "pipeline.code_steps",
            str(len(spec.STEPS) - len(ai_steps)),
            "pipeline_docs/spec.py — steps of any non-AI kind",
            len(spec.STEPS) - len(ai_steps),
        ),
        Fact(
            "pipeline.person_steps",
            str(len(person)),
            "pipeline_docs/spec.py — steps drawn in the personal column",
            len(person),
        ),
        Fact(
            "pipeline.meta_steps",
            str(len(meta)),
            "pipeline_docs/spec.py — steps drawn in the meta column",
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
            "pipeline_docs/spec.py — Step.depends_on entries",
            sum(len(step.depends_on) for step in spec.STEPS),
        ),
        Fact(
            "pipeline.groups",
            str(len(spec.GROUPS)),
            "pipeline_docs/spec.py — GROUPS",
            len(spec.GROUPS),
        ),
        Fact(
            "pipeline.artifacts",
            str(len(spec.ARTIFACTS)),
            "pipeline_docs/spec.py — ARTIFACTS",
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


def _script_facts(codebase: Codebase) -> List[Fact]:
    total_lines = sum(facts.line_count for facts in codebase.scripts.values())
    return [
        Fact(
            "scripts.count",
            str(len(codebase.scripts)),
            "scripts/*.py, excluding the docs builder itself",
            len(codebase.scripts),
        ),
        Fact(
            "scripts.lines",
            _thousands(total_lines),
            "scripts/*.py line counts",
            total_lines,
        ),
    ]


def _app_facts() -> List[Fact]:
    src = REPO_ROOT / "src"
    components = _files(src / "components", "*.svelte")
    stores = _files(src / "stores", "*.js")
    utils = _files(src / "utils", "*.js")
    locales = _files(src / "locales", "*.json")
    svelte_lines = _lines_of(components + _files(src, "*.svelte"))
    js_lines = _lines_of(stores + utils + _files(src, "*.js"))

    facts = [
        Fact(
            "app.components",
            str(len(components) + len(_files(src, "*.svelte"))),
            "src/components/*.svelte plus src/App.svelte",
            len(components) + len(_files(src, "*.svelte")),
        ),
        Fact("app.stores", str(len(stores)), "src/stores/*.js", len(stores)),
        Fact("app.utils", str(len(utils)), "src/utils/*.js", len(utils)),
        Fact(
            "app.svelte_lines",
            _thousands(svelte_lines),
            "line counts of the Svelte components",
            svelte_lines,
        ),
        Fact(
            "app.js_lines",
            _thousands(js_lines),
            "line counts of the plain-JavaScript modules",
            js_lines,
        ),
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


def _data_facts() -> List[Fact]:
    data = REPO_ROOT / "data"
    people_dirs = (
        sorted(path for path in (data / "people").iterdir() if path.is_dir())
        if (data / "people").is_dir()
        else []
    )
    meta_files = _files(data / "meta_stories", "*.json")

    events = 0
    networked = 0
    connections = 0
    for person in people_dirs:
        count = _json_array_length(person / "life_events.json", "events")
        if count:
            events += count
        links = _json_array_length(person / "ego_network.json", "connections")
        if links:
            networked += 1
            connections += links

    registry = _json_array_length(data / "persons.json", "people")

    facts = [
        Fact(
            "data.people",
            str(len(people_dirs)),
            "data/people/ subdirectories",
            len(people_dirs),
        ),
        Fact(
            "data.meta_stories",
            str(len(meta_files)),
            "data/meta_stories/*.json",
            len(meta_files),
        ),
        Fact(
            "data.events",
            _thousands(events),
            "sum of events[] across every data/people/*/life_events.json",
            events,
        ),
        Fact(
            "data.events_per_person",
            f"{events / len(people_dirs):.0f}" if people_dirs else "—",
            "mean events per biography",
            (events / len(people_dirs)) if people_dirs else None,
        ),
        Fact(
            "data.connections",
            _thousands(connections),
            "sum of connections[] across every data/people/*/ego_network.json",
            connections,
        ),
        Fact(
            "data.networked_people",
            str(networked),
            "biographies that have an ego network on disk",
            networked,
        ),
    ]
    if registry is not None:
        facts.append(
            Fact(
                "data.registry_entries",
                str(registry),
                "data/persons.json",
                registry,
            )
        )
    return facts


def _test_facts() -> List[Fact]:
    tests = REPO_ROOT / "tests"
    python_tests = _files(tests, "test_*.py")
    browser_tests = _files(tests, "*.spec.js")
    cases = 0
    for path in python_tests:
        cases += _read_text(path).count("    def test_")
    return [
        Fact(
            "tests.python_modules",
            str(len(python_tests)),
            "tests/test_*.py",
            len(python_tests),
        ),
        Fact(
            "tests.python_cases",
            str(cases),
            "`def test_` methods across tests/test_*.py",
            cases,
        ),
        Fact(
            "tests.browser_specs",
            str(len(browser_tests)),
            "tests/*.spec.js",
            len(browser_tests),
        ),
    ]


def _run_facts(runs: Dict[str, Any]) -> List[Fact]:
    records = runs.get("runs") or []
    calls = [call for run in records for call in (run.get("calls") or [])]
    seconds = sum(float(call.get("duration_s") or 0) for call in calls)
    tokens = 0
    for call in calls:
        usage = call.get("usage") or {}
        tokens += int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
        tokens += int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)

    return [
        Fact("runs.count", str(len(records)), "docs/report/runs/*.json", len(records)),
        Fact("runs.calls", str(len(calls)), "recorded model calls", len(calls)),
        # Zero is a real answer here — "no run has been recorded yet" is
        # something the report should be able to say in a sentence.
        Fact(
            "runs.minutes",
            f"{seconds / 60:.0f}",
            "wall-clock seconds spent inside recorded API calls",
            seconds / 60,
        ),
        Fact(
            "runs.tokens",
            _thousands(tokens),
            "input plus output tokens as reported by the API",
            tokens,
        ),
    ]


def collect(
    codebase: Codebase, runs: Optional[Dict[str, Any]] = None
) -> Dict[str, Fact]:
    """Every citable fact, keyed by the name the markdown uses."""
    groups: List[List[Fact]] = [
        _pipeline_facts(codebase),
        _script_facts(codebase),
        _app_facts(),
        _data_facts(),
        _test_facts(),
        _run_facts(runs or {}),
    ]
    facts: Dict[str, Fact] = {}
    for group in groups:
        for fact in group:
            facts[fact.key] = fact
    return facts


def to_json(facts: Dict[str, Fact]) -> Dict[str, Any]:
    return {key: fact.to_json() for key, fact in sorted(facts.items())}

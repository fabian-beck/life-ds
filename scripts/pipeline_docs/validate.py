#!/usr/bin/env python3
"""Drift checks between `spec.py` and the actual generation scripts.

The chart is only worth reading if it cannot quietly fall behind the code, so
every spec entry is resolved against the source and every AI call site in the
codebase has to be claimed by some step. A new phase that nobody documented is
an error, not a silent omission.

The dependency graph is checked too: an edge to an unknown step, or a cycle,
would make the layered layout meaningless rather than merely wrong, so both are
build errors.

`check_report` extends the same principle to the authored half of the document.
A component the page cannot hydrate, a lane or script that no longer exists, and
a citation to a measurement that was removed are all build errors: each would
render as a silent gap in a sentence the reader is meant to trust. Facts nobody
cites are a warning only—they cost a measurement, not a claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Set

from . import spec, teaser
from .facts import Fact
from .introspect import AiCall, Codebase
from .report import COMPONENTS, Document


@dataclass
class Problem:
    severity: str  # "error" | "warning"
    where: str
    message: str

    def __str__(self) -> str:
        marker = "ERROR" if self.severity == "error" else "warn "
        return f"  [{marker}] {self.where}: {self.message}"


def _function_exists(codebase: Codebase, script: str, function: str) -> bool:
    facts = codebase.scripts.get(script.rsplit("/", 1)[-1])
    if facts is None:
        return False
    if function in facts.functions:
        return True
    # Nested definitions are stored qualified (`outer.inner`).
    return any(name.split(".")[-1] == function for name in facts.functions)


def _check_graph() -> List[Problem]:
    """Dangling edges, self-loops, cycles and cross-pipeline edges."""
    problems: List[Problem] = []
    known = {step.id for step in spec.STEPS}
    edges: Dict[str, List[str]] = {}

    for step in spec.STEPS:
        targets: List[str] = []
        for dep in step.depends_on:
            where = f"step '{step.id}'"
            if dep.on not in known:
                problems.append(
                    Problem("error", where, f"depends on unknown step '{dep.on}'")
                )
                continue
            if dep.on == step.id:
                problems.append(Problem("error", where, "depends on itself"))
                continue
            if not dep.data:
                problems.append(
                    Problem("warning", where, f"edge from '{dep.on}' has no data label")
                )
            targets.append(dep.on)
        edges[step.id] = targets

    # Depth-first cycle detection: the layout assigns a layer by longest path,
    # which never terminates on a cycle.
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {step_id: WHITE for step_id in edges}

    def visit(node: str, trail: List[str]) -> None:
        color[node] = GRAY
        for parent in edges.get(node, []):
            if color[parent] == GRAY:
                loop = " -> ".join(trail[trail.index(parent) :] + [parent])
                problems.append(Problem("error", "spec", f"dependency cycle: {loop}"))
            elif color[parent] == WHITE:
                visit(parent, trail + [parent])
        color[node] = BLACK

    for step_id in edges:
        if color[step_id] == WHITE:
            visit(step_id, [step_id])

    return problems


def _check_groups() -> List[Problem]:
    """Groups must name real steps, claim each one once, and stay in one column.

    A group is drawn as one band across several layers, so a member from the
    other pipeline—or a step claimed twice—would have the layout reserving a
    column that cannot exist.
    """
    problems: List[Problem] = []
    known = {step.id for step in spec.STEPS}
    owner: Dict[str, str] = {}
    seen_ids: Set[str] = set()

    for group in spec.GROUPS:
        where = f"group '{group.id}'"
        if group.id in seen_ids:
            problems.append(
                Problem("error", "spec", f"duplicate group id '{group.id}'")
            )
        seen_ids.add(group.id)
        if len(group.steps) < 2:
            problems.append(
                Problem("warning", where, "has fewer than two steps to align")
            )
        columns = set()
        for step_id in group.steps:
            if step_id not in known:
                problems.append(
                    Problem("error", where, f"names unknown step '{step_id}'")
                )
                continue
            if step_id in owner:
                problems.append(
                    Problem(
                        "error",
                        where,
                        f"step '{step_id}' is already in group '{owner[step_id]}'",
                    )
                )
            owner[step_id] = group.id
            # The drawn column comes from the id prefix, as it does in model.py.
            columns.add(step_id[:2])
        if len(columns) > 1:
            problems.append(
                Problem(
                    "error",
                    where,
                    "spans both pipelines: " + ", ".join(sorted(columns)),
                )
            )
    return problems


def check(codebase: Codebase) -> List[Problem]:
    problems: List[Problem] = []
    known_scripts = set(codebase.scripts)

    claimed_prompts: Set[str] = set()
    claimed_functions: Set[str] = set()

    for step in spec.STEPS:
        where = f"step '{step.id}'"
        script_name = step.script.rsplit("/", 1)[-1]
        if script_name not in known_scripts:
            problems.append(Problem("error", where, f"unknown script {step.script}"))
            continue
        if not _function_exists(codebase, script_name, step.function):
            problems.append(
                Problem(
                    "error",
                    where,
                    f"{step.script} has no function '{step.function}'—it was "
                    "renamed or removed",
                )
            )
        claimed_functions.add(f"{script_name}:{step.function}")

        for prompt_symbol in step.prompts:
            found = any(
                prompt_symbol in facts.prompts for facts in codebase.scripts.values()
            )
            if not found:
                problems.append(
                    Problem(
                        "error",
                        where,
                        f"prompt source '{prompt_symbol}' no longer exists",
                    )
                )
            claimed_prompts.add(prompt_symbol)

        for artifact_id in list(step.inputs) + list(step.outputs):
            if spec.artifact_by_id(artifact_id) is None:
                problems.append(
                    Problem("error", where, f"unknown artifact '{artifact_id}'")
                )

        if step.lane not in spec.LANES:
            problems.append(Problem("error", where, f"unknown lane '{step.lane}'"))

    # Every model call in the repo should belong to a documented step.
    by_key: Dict[str, List[AiCall]] = {}
    for call in codebase.all_ai_calls():
        by_key.setdefault(f"{call.script}:{call.function.split('.')[-1]}", []).append(
            call
        )

    for key, calls in sorted(by_key.items()):
        if key in claimed_functions:
            continue
        script, function = key.split(":", 1)
        problems.append(
            Problem(
                "error",
                "coverage",
                f"{script}:{function} calls the model ({calls[0].method}, "
                f"line {calls[0].lineno}) but no step in spec.py claims it",
            )
        )

    ids = [step.id for step in spec.STEPS]
    for step_id in set(ids):
        if ids.count(step_id) > 1:
            problems.append(Problem("error", "spec", f"duplicate step id '{step_id}'"))

    problems.extend(_check_graph())
    problems.extend(_check_groups())

    used_artifacts = {
        artifact_id
        for step in spec.STEPS
        for artifact_id in list(step.inputs) + list(step.outputs)
    }
    for artifact in spec.ARTIFACTS:
        if artifact.id not in used_artifacts:
            problems.append(
                Problem(
                    "warning",
                    "spec",
                    f"artifact '{artifact.id}' is declared but no step touches it",
                )
            )

    return problems


def check_report(
    document: Document,
    facts: Dict[str, Fact],
    codebase: Codebase,
) -> List[Problem]:
    """Resolve every mount point and citation in the authored report.

    The markdown is allowed to name things it does not own—a lane, a script, a
    schema—so each of those names is resolved here rather than trusted. The
    coverage checks at the end are about the report as a document: a pipeline
    that no chart draws, or a section tree with no contents, means the base
    version lost something rather than merely rendering it differently.
    """
    problems: List[Problem] = []
    lanes_drawn: Set[str] = set()

    for mount in document.mounts:
        where = f"report.md line {mount.line} ('::: {mount.component}')"
        spec_entry = COMPONENTS[mount.component]

        lane = mount.params.get("lane")
        if lane is not None and lane not in (spec.PERSON, spec.META):
            problems.append(
                Problem(
                    "error",
                    where,
                    f"lane '{lane}' is not a drawn pipeline—use "
                    f"'{spec.PERSON}' or '{spec.META}'",
                )
            )
        if mount.component == "pipeline" and lane:
            lanes_drawn.add(lane)

        script = mount.params.get("script")
        if script is not None and script.rsplit("/", 1)[-1] not in codebase.scripts:
            problems.append(Problem("error", where, f"unknown script '{script}'"))

        for name in _split_list(mount.params.get("names")):
            if codebase.schema(name) is None:
                problems.append(
                    Problem("error", where, f"unknown output schema '{name}'")
                )

        for key in _split_list(mount.params.get("keys")):
            if key not in facts:
                problems.append(Problem("error", where, f"unknown fact '{key}'"))

        if spec_entry.figures or spec_entry.tables:
            if mount.figure_start < 1 or mount.table_start < 1:
                problems.append(
                    Problem("error", where, "caption numbering was not assigned")
                )

    for key in sorted(set(facts) - set(document.citations) - set(teaser.fact_keys())):
        problems.append(
            Problem(
                "warning",
                "report.md",
                f"fact '{key}' is measured but never cited",
            )
        )

    problems.extend(_check_teaser(document, facts))

    missing_lanes = {spec.PERSON, spec.META} - lanes_drawn
    if missing_lanes:
        problems.append(
            Problem(
                "error",
                "report.md",
                "no '::: pipeline' block draws " + ", ".join(sorted(missing_lanes)),
            )
        )

    if not document.sections:
        problems.append(
            Problem("error", "report.md", "the report has no '##' section headings")
        )
    if not document.front.get("title"):
        problems.append(Problem("error", "report.md", "front matter has no 'title'"))

    return problems


def _check_teaser(document: Document, facts: Dict[str, Fact]) -> List[Problem]:
    """The figure, and the prose's references into it, have to agree.

    Unknown part ids already fail in the compiler. What is left is the relation
    between the two: a reference with no figure to point at is a dead control,
    and a part nothing refers to is a region of the drawing the report never
    explains—the same warning a measured but uncited fact gets.
    """
    problems: List[Problem] = []
    mounted = any(mount.component == "teaser" for mount in document.mounts)

    if document.figrefs and not mounted:
        problems.append(
            Problem(
                "error",
                "report.md",
                "the prose references parts of the teaser figure, but no "
                "'::: teaser' block draws it",
            )
        )

    for problem in teaser.check_scene(list(facts)):
        problems.append(Problem(problem.severity, problem.where, problem.message))

    if mounted:
        for part_id in teaser.part_ids():
            if part_id not in document.figrefs:
                problems.append(
                    Problem(
                        "warning",
                        "report.md",
                        f"teaser part '{part_id}' is drawn but no phrase "
                        "references it",
                    )
                )
    return problems


def _split_list(value: object) -> List[str]:
    if not isinstance(value, str) or not value.strip():
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def report(problems: List[Problem], subject: str = "Pipeline spec") -> int:
    """Print problems; return the number of errors."""
    errors = [problem for problem in problems if problem.severity == "error"]
    warnings = [problem for problem in problems if problem.severity == "warning"]
    if not problems:
        print(f"  {subject} matches the source: no drift.")
        return 0
    for problem in problems:
        print(str(problem))
    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s).")
    return len(errors)

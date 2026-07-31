#!/usr/bin/env python3
"""Drift checks between `spec.py` and the actual generation scripts.

The chart is only worth reading if it cannot quietly fall behind the code, so
every spec entry is resolved against the source and every AI call site in the
codebase has to be claimed by some step. A new phase that nobody documented is
an error, not a silent omission.

The dependency graph is checked too: an edge to an unknown step, or a cycle,
would make the layered layout meaningless rather than merely wrong, so both are
build errors. An edge that a longer chain already implies is a warning instead—
it leaves every layer where it was and only crowds the figure with a line the
reader could have followed along the strand.

`check_report` extends the same principle to the authored half of the document.
A component the page cannot hydrate, a lane or script that no longer exists, and
a citation to a measurement that was removed are all build errors: each would
render as a silent gap in a sentence the reader is meant to trust. Facts nobody
cites are a warning only—they cost a measurement, not a claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

from . import bibliography, concepts, screenshots, spec, teaser
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


def _implying_path(
    edges: Dict[str, List[str]], start: str, goal: str
) -> Optional[List[str]]:
    """A route from `start` to `goal` that avoids the direct edge between them.

    Its existence makes the direct edge redundant: the reader already reaches
    `goal` by following the chart, so drawing the shortcut only adds a line.
    Breadth-first, so the path reported is the shortest one and reads as the
    argument for dropping the edge.
    """
    queue: List[List[str]] = [
        [start, parent] for parent in edges.get(start, []) if parent != goal
    ]
    seen = {start, *(path[1] for path in queue)}
    while queue:
        path = queue.pop(0)
        for parent in edges.get(path[-1], []):
            if parent == goal:
                return path + [goal]
            if parent in seen:
                continue
            seen.add(parent)
            queue.append(path + [parent])
    return None


def _check_graph() -> List[Problem]:
    """Dangling edges, self-loops, cycles, redundant edges and cross-pipeline ones."""
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

    # An edge another chain already implies changes no layer—the longest path is
    # the same with or without it—so it is clutter rather than an error: two
    # lines where the reader needed one. Naming the implying path lets the
    # maintainer see what would carry the meaning instead.
    for step_id, parents in edges.items():
        for parent in parents:
            path = _implying_path(edges, step_id, parent)
            if path:
                problems.append(
                    Problem(
                        "warning",
                        f"step '{step_id}'",
                        f"the edge from '{parent}' is already implied by "
                        + " -> ".join(reversed(path))
                        + "; drop it and let the summary carry the detail",
                    )
                )

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
        # An artifact with no concept would be drawn as a bare label where every
        # other one carries a glyph, which reads as a rendering bug.
        if concepts.concept_by_id(artifact.concept) is None:
            problems.append(
                Problem(
                    "error",
                    "spec",
                    f"artifact '{artifact.id}' names unknown concept "
                    f"'{artifact.concept}'",
                )
            )

    for message in concepts.check_icons():
        problems.append(Problem("error", "concepts", message))

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
    problems.extend(_check_screenshots(document))
    problems.extend(_check_principles(document))
    problems.extend(_check_references(document))

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


def _check_principles(document: Document) -> List[Problem]:
    """A principle is only a principle if the report acts on it somewhere.

    An unknown id already fails in the compiler. What is left is the relation
    the numbering exists for: a principle stated in the introduction and never
    pointed at again is a claim the report makes once and never keeps, which is
    exactly the failure the references were introduced to prevent.
    """
    problems: List[Problem] = []
    if document.prefs and not document.principles:
        problems.append(
            Problem(
                "error",
                "report.md",
                "the prose references a design principle, but no "
                "'::: principles' block declares one",
            )
        )
    for item in document.principles:
        if item.id not in document.prefs:
            problems.append(
                Problem(
                    "warning",
                    "report.md",
                    f"principle {item.label} '{item.id}' is declared but no "
                    "sentence references it",
                )
            )
    return problems


def _check_references(document: Document) -> List[Problem]:
    """The prose and the `.bib` file have to describe the same set of works.

    An unknown key already fails in the compiler, where the line number is. What
    is left is the relation between the two: a citation with nowhere to point,
    an entry the report never uses, and an entry that names a work without
    saying where to resolve it.
    """
    problems: List[Problem] = []
    if document.refcites and not document.prints_references:
        problems.append(
            Problem(
                "error",
                "report.md",
                "the prose cites work, but no '::: references' block prints the list",
            )
        )
    for severity, message in bibliography.check(
        bibliography.default(), document.refcites
    ):
        problems.append(Problem(severity, "docs/report/references.bib", message))
    return problems


def _check_screenshots(
    document: Document, directory: Optional[Path] = None
) -> List[Problem]:
    """Every declared screenshot has to describe a capture, and have one.

    A missing picture is an error for the same reason a missing measurement is:
    the block would render as a hole in a page whose whole claim is that it was
    derived. A stale one is a warning—the figure still shows the application,
    just not from the position the report now describes—and it names the command
    that fixes it.

    Whether a *current* capture still resembles the application is outside what
    this can know, which is the honest limit of a described figure and the reason
    `--shots all` exists.
    """
    where_dir = directory or screenshots.SHOTS_DIR
    problems: List[Problem] = []
    seen: Dict[str, int] = {}
    parsed: List[screenshots.Shot] = []

    for mount in document.mounts:
        if mount.component != "screenshot":
            continue
        where = f"report.md line {mount.line} ('::: screenshot')"
        try:
            shot = screenshots.parse(mount.params, mount.body_markdown, mount.line)
        except screenshots.ScreenshotError as error:
            problems.append(Problem("error", where, str(error)))
            continue
        if shot.id in seen:
            problems.append(
                Problem(
                    "error",
                    where,
                    f"id '{shot.id}' is already used at line {seen[shot.id]}—two "
                    "shots would write the same file",
                )
            )
            continue
        seen[shot.id] = mount.line
        parsed.append(shot)

    album = screenshots.Album(parsed, screenshots.load_index(where_dir), where_dir)
    for shot in parsed:
        where = f"report.md line {shot.line} ('::: screenshot id={shot.id}')"
        status = album.status(shot)
        if status == "missing":
            problems.append(
                Problem(
                    "error",
                    where,
                    "no capture on disk—take it with "
                    f"'python scripts/generate_report.py --shots {shot.id}'",
                )
            )
        elif status == "stale":
            problems.append(
                Problem(
                    "warning",
                    where,
                    "the declaration changed since the capture was taken—retake "
                    f"it with 'python scripts/generate_report.py --shots {shot.id}'",
                )
            )
        capture = album.captures.get(shot.id)
        if capture and capture.bytes > 1_500_000:
            problems.append(
                Problem(
                    "warning",
                    where,
                    f"the capture is {capture.bytes // 1024} KB and is inlined "
                    "into the page—consider format=jpeg or a smaller viewport",
                )
            )

    for orphan in screenshots.prune(album):
        problems.append(
            Problem(
                "warning",
                "docs/report/screenshots",
                f"'{orphan}' was captured for a block the report no longer has",
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

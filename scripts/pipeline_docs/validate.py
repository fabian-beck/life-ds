#!/usr/bin/env python3
"""Drift checks between `spec.py` and the actual generation scripts.

The chart is only worth reading if it cannot quietly fall behind the code, so
every spec entry is resolved against the source and every AI call site in the
codebase has to be claimed by some step. A new phase that nobody documented is
an error, not a silent omission.

The dependency graph is checked too: an edge to an unknown step, or a cycle,
would make the layered layout meaningless rather than merely wrong, so both are
build errors.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Set

from . import spec
from .introspect import AiCall, Codebase


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
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {step_id: WHITE for step_id in edges}

    def visit(node: str, trail: List[str]) -> None:
        colour[node] = GREY
        for parent in edges.get(node, []):
            if colour[parent] == GREY:
                loop = " -> ".join(trail[trail.index(parent) :] + [parent])
                problems.append(Problem("error", "spec", f"dependency cycle: {loop}"))
            elif colour[parent] == WHITE:
                visit(parent, trail + [parent])
        colour[node] = BLACK

    for step_id in edges:
        if colour[step_id] == WHITE:
            visit(step_id, [step_id])

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
                    f"{step.script} has no function '{step.function}' — it was "
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


def report(problems: List[Problem]) -> int:
    """Print problems; return the number of errors."""
    errors = [problem for problem in problems if problem.severity == "error"]
    warnings = [problem for problem in problems if problem.severity == "warning"]
    if not problems:
        print("Pipeline spec matches the source: no drift.")
        return 0
    for problem in problems:
        print(str(problem))
    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s).")
    return len(errors)

#!/usr/bin/env python3
"""Fuse the static scan and the AI summaries into one payload.

The HTML page is a pure function of the dictionary this module returns, which
keeps the rendering layer free of any knowledge about how a fact was
obtained—and makes the whole build testable without touching a browser.

The payload also carries the report's own structure: the section tree the sidebar
navigates, the mount manifest the page hydrates, and the measurements the
authored prose cites. Everything the page shows therefore arrives through one
dictionary, whether it came from the AST or from a sentence someone wrote by
hand.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import concepts as concepts_module
from . import facts as facts_module
from . import spec, teaser
from .introspect import Codebase
from .report import Document

REPO_ROOT = Path(__file__).resolve().parents[2]

KIND_META: Dict[str, Dict[str, str]] = {
    spec.AI: {
        "label": "AI call",
        "description": "Sends a prompt to a language model and parses a structured result.",
    },
    spec.CODE: {
        "label": "Deterministic",
        "description": "Plain code—same inputs, same outputs, no model involved.",
    },
    spec.EXTERNAL: {
        "label": "External source",
        "description": "Fetches from Wikipedia, Deutsche Biographie, Commons or Nominatim.",
    },
    spec.IMAGE: {
        "label": "Image model",
        "description": "Generates or edits an image rather than text.",
    },
}


def _git(*args: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value or None


def _cli_model_default(codebase: Codebase, script: str) -> Optional[str]:
    """The resolved `--model` default of a script, for steps that inherit it."""
    facts = codebase.scripts.get(script.rsplit("/", 1)[-1])
    if facts is None:
        return None
    for call in facts.ai_calls:
        if call.model_source == "--model default" and call.model_value:
            return call.model_value
    # No call site in that script to borrow the resolution from; fall back to
    # the shared default the flag almost certainly points at.
    from config import DEFAULT_MODEL

    return DEFAULT_MODEL


def _step_ai_calls(codebase: Codebase, step: spec.Step) -> List[Dict[str, Any]]:
    script_name = step.script.rsplit("/", 1)[-1]
    facts = codebase.scripts.get(script_name)
    if facts is None:
        return []
    return [
        call.to_json()
        for call in facts.ai_calls
        if call.function.split(".")[-1] == step.function
    ]


def _step_line(codebase: Codebase, step: spec.Step) -> Optional[int]:
    facts = codebase.scripts.get(step.script.rsplit("/", 1)[-1])
    if facts is None:
        return None
    for name, function in facts.functions.items():
        if name == step.function or name.split(".")[-1] == step.function:
            return function.lineno
    return None


def _collect_schemas(codebase: Codebase, names: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    queue = list(dict.fromkeys(names))
    while queue:
        name = queue.pop()
        if name in out:
            continue
        schema = codebase.schema(name)
        if schema is None:
            continue
        out[name] = schema.to_json()
        # Nested models: pull any referenced type that is itself a schema.
        for item in schema.fields:
            for candidate in _type_names(item.annotation):
                if candidate not in out and codebase.schema(candidate) is not None:
                    queue.append(candidate)
    return out


def _type_names(annotation: str) -> List[str]:
    tokens: List[str] = []
    current = ""
    for char in annotation:
        if char.isalnum() or char == "_":
            current += char
        else:
            if current:
                tokens.append(current)
            current = ""
    if current:
        tokens.append(current)
    return [token for token in tokens if token[:1].isupper()]


def _script_index(codebase: Codebase) -> Dict[str, Dict[str, Any]]:
    """Docstring, size and CLI surface of every scanned script.

    The report cites a script's options by name (`::: cliflags script=...`), so
    the whole surface travels in the payload rather than only the two entry
    points—a section about the maintenance tools can then show theirs too.
    """
    return {
        name: {
            "script": f"scripts/{name}",
            "docstring": facts.docstring,
            "line_count": facts.line_count,
            "flags": [flag.to_json() for flag in facts.cli_flags],
        }
        for name, facts in sorted(codebase.scripts.items())
    }


def _call_sites(codebase: Codebase) -> List[Dict[str, Any]]:
    """Every model call in the repo, and the step that claims it.

    The report uses this to show coverage: a call site with no owning step is a
    part of the system the document does not describe, which is exactly the thing
    a generated report should be able to admit about itself.
    """
    owner: Dict[str, str] = {}
    for step in spec.STEPS:
        owner[f"{step.script.rsplit('/', 1)[-1]}:{step.function}"] = step.id

    rows: List[Dict[str, Any]] = []
    for call in codebase.all_ai_calls():
        function = call.function.split(".")[-1]
        rows.append(
            {
                "script": call.script,
                "function": function,
                "line": call.lineno,
                "method": call.method,
                "model": call.model_value,
                "model_source": call.model_source,
                "effort": call.reasoning_value,
                "schema": call.schema,
                "step": owner.get(f"{call.script}:{function}"),
            }
        )
    rows.sort(key=lambda row: (row["script"], row["line"]))
    return rows


def build_payload(
    codebase: Codebase,
    summaries: Dict[str, Dict[str, Any]],
    document: Optional[Document] = None,
    facts: Optional[Dict[str, facts_module.Fact]] = None,
    shots: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    steps: List[Dict[str, Any]] = []
    # Schemas the steps use, plus any the report asks to expand by name.
    schema_names: List[str] = []
    for mount in (document.mounts if document else []):
        if mount.component == "schemalist":
            schema_names.extend(
                name.strip()
                for name in (mount.params.get("names") or "").split(",")
                if name.strip()
            )

    for step in spec.STEPS:
        group = spec.group_of(step.id)
        ai_calls = _step_ai_calls(codebase, step)
        names = [call["schema"] for call in ai_calls if call.get("schema")]
        schema_names.extend(names)
        models = [call["model_value"] for call in ai_calls if call.get("model_value")]
        efforts = [
            call["reasoning_value"] for call in ai_calls if call.get("reasoning_value")
        ]
        model_value = models[0] if models else None
        model_source = ai_calls[0]["model_source"] if ai_calls else None
        if model_value is None and step.model_from:
            model_value = _cli_model_default(codebase, step.model_from)
            model_source = f"{step.model_from} --model default"
        steps.append(
            {
                "id": step.id,
                "label": step.label,
                "column": spec.column_of(step),
                "lane": step.lane,
                "group": group.id if group else None,
                "kind": step.kind,
                "depends_on": [
                    {"on": dep.on, "data": dep.data} for dep in step.depends_on
                ],
                "script": step.script,
                "function": step.function,
                "line": _step_line(codebase, step),
                "phase": step.phase_label,
                "skip_flag": step.skip_flag,
                "calls_per_run": step.calls_per_run,
                "model": model_value,
                "model_source": model_source,
                "model_note": step.model_note,
                "effort": efforts[0] if efforts else None,
                "schemas": list(dict.fromkeys(names)),
                "spec_summary": step.summary,
                "summary": summaries.get(step.id) or {},
                "inputs": step.inputs,
                "outputs": step.outputs,
                "ai_calls": ai_calls,
            }
        )

    built = time.gmtime()
    return {
        # The report is versioned by the day it was built, because that is what
        # a reader needs to know: which one of these they are holding. The
        # timestamp and the commit stay in the payload for `::: buildinfo`,
        # where provenance belongs.
        "version": f"{time.strftime('%B', built)} {built.tm_mday}, {built.tm_year}",
        "generated_at": time.strftime("%Y-%m-%d %H:%M UTC", built),
        # The commit is the state the page was built from and identifies it for
        # good. The branch it was built on is a fact about someone's working
        # copy—it names a feature branch that will be gone by the time anyone
        # reads this—so it is deliberately not carried.
        "commit": _git("rev-parse", "--short", "HEAD"),
        "report": document.to_json() if document else None,
        "facts": facts_module.to_json(facts or {}),
        "call_sites": _call_sites(codebase),
        "script_index": _script_index(codebase),
        "lanes": spec.LANES,
        "kinds": KIND_META,
        "teaser": teaser.scene(),
        "screenshots": shots or {},
        "steps": steps,
        "groups": [group.__dict__ for group in spec.GROUPS],
        "concepts": concepts_module.to_json(),
        # Deliberately without `path`: the spec knows where an artifact is
        # stored, the page speaks about what it carries.
        "artifacts": [
            {
                "id": artifact.id,
                "label": artifact.label,
                "kind": artifact.kind,
                "note": artifact.note,
                "concept": artifact.concept,
            }
            for artifact in spec.ARTIFACTS
        ],
        "schemas": _collect_schemas(codebase, schema_names),
        "totals": {
            "steps": len(spec.STEPS),
            "ai_steps": sum(1 for step in spec.STEPS if step.kind == spec.AI),
            "call_sites": len(codebase.all_ai_calls()),
        },
    }

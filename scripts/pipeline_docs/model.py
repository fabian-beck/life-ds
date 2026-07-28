#!/usr/bin/env python3
"""Fuse the static scan, the AI summaries and the recorded runs into one payload.

The HTML page is a pure function of the dictionary this module returns, which
keeps the rendering layer free of any knowledge about how a fact was obtained —
and makes the whole build testable without touching a browser.
"""

from __future__ import annotations

import statistics
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import spec
from .introspect import Codebase

REPO_ROOT = Path(__file__).resolve().parents[2]

KIND_META: Dict[str, Dict[str, str]] = {
    spec.AI: {
        "label": "AI call",
        "description": "Sends a prompt to a language model and parses a structured result.",
    },
    spec.CODE: {
        "label": "Deterministic",
        "description": "Plain code — same inputs, same outputs, no model involved.",
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


def _column_of(step: spec.Step) -> str:
    """Which pipeline column a step is drawn in.

    Lane records *ownership* — several shared subsystems (sourcing, review,
    translation) are their own scripts — but the reader wants to see them at the
    point in the flow where they run, so the drawn column comes from the step id.
    """
    return spec.PERSON if step.id.startswith("p_") else spec.META


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


def _step_prompts(codebase: Codebase, step: spec.Step) -> List[Dict[str, Any]]:
    prompts: List[Dict[str, Any]] = []
    for symbol in step.prompts:
        for facts in codebase.scripts.values():
            prompt = facts.prompts.get(symbol)
            if prompt is not None:
                prompts.append(prompt.to_json())
                break
    return prompts


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


def _run_stats(runs: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Per-step aggregates over every recorded run."""
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for run in runs.get("runs", []):
        for call in run.get("calls", []):
            step_id = call.get("step")
            if step_id:
                buckets.setdefault(step_id, []).append(call)

    stats: Dict[str, Dict[str, Any]] = {}
    for step_id, calls in buckets.items():
        durations = [float(call.get("duration_s") or 0) for call in calls]
        input_tokens = 0
        output_tokens = 0
        reasoning_tokens = 0
        for call in calls:
            usage = call.get("usage") or {}
            input_tokens += int(
                usage.get("input_tokens") or usage.get("prompt_tokens") or 0
            )
            output_tokens += int(
                usage.get("output_tokens") or usage.get("completion_tokens") or 0
            )
            reasoning_tokens += int(usage.get("reasoning_tokens") or 0)
        stats[step_id] = {
            "calls": len(calls),
            "total_s": round(sum(durations), 2),
            "median_s": round(statistics.median(durations), 2) if durations else 0,
            "max_s": round(max(durations), 2) if durations else 0,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "errors": sum(
                1 for call in calls if (call.get("result") or {}).get("kind") == "error"
            ),
        }
    return stats


def _unattributed(runs: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Recorded calls that no step claimed — usually a spec gap worth seeing."""
    out: List[Dict[str, Any]] = []
    for run in runs.get("runs", []):
        for call in run.get("calls", []):
            if not call.get("step"):
                out.append(
                    {
                        "origin": call.get("origin"),
                        "model": call.get("model"),
                        "duration_s": call.get("duration_s"),
                    }
                )
    return out


def _entrypoints(codebase: Codebase) -> List[Dict[str, Any]]:
    entries = []
    for lane_id in (spec.PERSON, spec.META):
        script = spec.LANES[lane_id]["entry"].rsplit("/", 1)[-1]
        facts = codebase.scripts.get(script)
        if facts is None:
            continue
        entries.append(
            {
                "lane": lane_id,
                "script": script,
                "docstring": facts.docstring,
                "line_count": facts.line_count,
                "flags": [flag.to_json() for flag in facts.cli_flags],
            }
        )
    return entries


def build_payload(
    codebase: Codebase,
    summaries: Dict[str, Dict[str, Any]],
    runs: Dict[str, Any],
) -> Dict[str, Any]:
    stats = _run_stats(runs)
    schema_names: List[str] = []
    steps: List[Dict[str, Any]] = []

    for step in spec.STEPS:
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
                "column": _column_of(step),
                "lane": step.lane,
                "kind": step.kind,
                "stage": step.stage,
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
                "prompts": _step_prompts(codebase, step),
                "inputs": step.inputs,
                "outputs": step.outputs,
                "ai_calls": ai_calls,
                "stats": stats.get(step.id),
            }
        )

    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "commit": _git("rev-parse", "--short", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "lanes": spec.LANES,
        "kinds": KIND_META,
        "steps": steps,
        "artifacts": [artifact.__dict__ for artifact in spec.ARTIFACTS],
        "schemas": _collect_schemas(codebase, schema_names),
        "entrypoints": _entrypoints(codebase),
        "runs": runs,
        "unattributed": _unattributed(runs),
        "totals": {
            "steps": len(spec.STEPS),
            "ai_steps": sum(1 for step in spec.STEPS if step.kind == spec.AI),
            "call_sites": len(codebase.all_ai_calls()),
            "scripts": len(codebase.scripts),
            "script_lines": sum(
                facts.line_count for facts in codebase.scripts.values()
            ),
        },
    }

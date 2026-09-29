#!/usr/bin/env python3
"""Per-step explanations of the pipeline, kept against the source they describe.

Each entry in `docs/report/summaries.json` explains one step: two or three
plain sentences on what the step contributes and, where one stands out, why it
is built that way, plus a phrase each for what it reads and what it leaves
behind. An entry is stored with a fingerprint of the step's source, prompt
template, and output schema, so a build can tell which entries describe source
that has since moved.

The entries are revised by hand. A build only reads them and never calls a
model: a stale entry is named and fails the check until it is revised and
accepted with `--accept-summary`, and a step without an entry shows the
one-liner from `spec.py`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

from . import spec
from .introspect import Codebase

CACHE_VERSION = 5
MAX_SOURCE_CHARS = 9000
MAX_PROMPT_CHARS = 6000


def _function_source(codebase: Codebase, step: spec.Step) -> str:
    script_name = step.script.rsplit("/", 1)[-1]
    facts = codebase.scripts.get(script_name)
    if facts is None:
        return ""
    match = None
    for name, function in facts.functions.items():
        if name == step.function or name.split(".")[-1] == step.function:
            match = function
            break
    if match is None:
        return ""
    lines = facts.path.read_text(encoding="utf-8").splitlines()
    body = "\n".join(lines[match.lineno - 1 : match.end_lineno])
    return body[:MAX_SOURCE_CHARS]


def _schema_block(codebase: Codebase, step: spec.Step) -> str:
    script_name = step.script.rsplit("/", 1)[-1]
    facts = codebase.scripts.get(script_name)
    names: List[str] = []
    if facts is not None:
        for call in facts.ai_calls:
            if call.function.split(".")[-1] == step.function and call.schema:
                names.append(call.schema)
    blocks: List[str] = []
    for name in dict.fromkeys(names):
        schema = codebase.schema(name)
        if schema is None:
            continue
        fields = "\n".join(
            f"  - {item.name}: {item.annotation}"
            + (f"—{item.description}" if item.description else "")
            for item in schema.fields
        )
        blocks.append(f"{schema.name}: {schema.docstring or ''}\n{fields}")
    return "\n\n".join(blocks)


def _prompt_block(codebase: Codebase, step: spec.Step) -> str:
    """The prompt templates a step is built from, its own script first.

    Builder names repeat across the generators—several scripts have a
    `build_prompt` and a `call_openai`—so a plain scan of every script would
    hand a step whichever namesake happened to be parsed first, and adding a
    script could silently re-document an unrelated step. Only when the step's
    own script does not define the symbol is it looked for elsewhere, which is
    what a step that names a helper from another module means.
    """
    own = codebase.scripts.get(step.script.rsplit("/", 1)[-1])
    ordered = [own] if own else []
    ordered += [facts for facts in codebase.scripts.values() if facts is not own]

    chunks: List[str] = []
    for symbol in step.prompts:
        for facts in ordered:
            prompt = facts.prompts.get(symbol)
            if prompt is None:
                continue
            chunks.append(f"--- {facts.name}:{symbol} ---\n{prompt.text}")
            break
    return "\n\n".join(chunks)[:MAX_PROMPT_CHARS]


def _flow_block(step: spec.Step) -> str:
    """What the spec says the step reads and writes, for the input and output.

    The dependency labels and the artifact names are the pipeline's own
    vocabulary for the data, so the phrases an explanation gives for input
    and output stay in the words the figures use.
    """
    labels = {item.id: item.label for item in spec.STEPS}
    artifacts = {item.id: item.label for item in spec.ARTIFACTS}
    lines: List[str] = []
    for dep in step.depends_on:
        lines.append(f"  - reads from '{labels.get(dep.on, dep.on)}': {dep.data}")
    for item in step.inputs:
        lines.append(f"  - reads the artifact: {artifacts.get(item, item)}")
    for item in step.outputs:
        lines.append(f"  - writes the artifact: {artifacts.get(item, item)}")
    return "\n".join(lines)


def build_context(codebase: Codebase, step: spec.Step) -> str:
    """Everything an explanation describes for one step, as fingerprinted."""
    parts = [
        f"STEP: {step.label}",
        f"PIPELINE: {spec.LANES[step.lane]['label']}",
        f"KIND: {step.kind}",
        f"SOURCE: {step.script} :: {step.function}",
        f"MAINTAINER NOTE: {step.summary}",
    ]
    flow = _flow_block(step)
    if flow:
        parts.append(f"\nDATA FLOW DECLARED IN THE SPEC:\n{flow}")
    schema = _schema_block(codebase, step)
    if schema:
        parts.append(f"\nSTRUCTURED OUTPUT REQUESTED:\n{schema}")
    prompt = _prompt_block(codebase, step)
    if prompt:
        parts.append(f"\nPROMPT TEMPLATE ({{...}} marks injected data):\n{prompt}")
    source = _function_source(codebase, step)
    if source:
        parts.append(f"\nSOURCE:\n{source}")
    return "\n".join(parts)


def _fingerprint(context: str) -> str:
    payload = f"v{CACHE_VERSION}\n{context}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def load_cache(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def save_cache(path: Path, cache: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def cached_summaries(path: Path) -> Dict[str, Dict[str, Any]]:
    """What the cache already holds, keyed by step, without calling anything.

    `--check` has to see the written explanations too—they are published text—
    and it must stay runnable without an API key and without writing a file.
    """
    entries = load_cache(path).get("steps") or {}
    return {
        step_id: entry["summary"]
        for step_id, entry in entries.items()
        if isinstance(entry, dict) and isinstance(entry.get("summary"), dict)
    }


def stale_steps(codebase: Codebase, path: Path) -> List[str]:
    """Steps whose cached explanation was written from source that has moved.

    The explanation is published as written from the step's current source,
    prompt and schema, so an entry whose fingerprint no longer matches is a
    claim the page can no longer support. A step the cache has never described
    is not stale: the build shows the `spec.py` text, which is attributed to the
    maintainer.
    """
    entries = load_cache(path).get("steps") or {}
    stale: List[str] = []
    for step in spec.STEPS:
        entry = entries.get(step.id)
        if not isinstance(entry, dict) or not isinstance(entry.get("summary"), dict):
            continue
        if entry.get("fingerprint") != _fingerprint(build_context(codebase, step)):
            stale.append(step.id)
    return stale


def _fallback(step: spec.Step) -> Dict[str, Any]:
    """The maintainer's own text, with the input and output left to the page.

    Without a written phrase for either, the page falls back to the declared
    dependencies and artifacts, which say the same thing in more words.
    """
    return {
        "description": step.summary,
        "input": "",
        "output": "",
        "source": "spec.py",
    }


def accept_summaries(codebase: Codebase, path: Path, step_ids: List[str]) -> None:
    """Mark hand-revised entries as written from the current source.

    An entry edited by hand in the cache still carries the fingerprint of the
    source it was first written from, and a build would replace it. Accepting
    it stamps the current fingerprint, which is the maintainer's statement
    that the entry now describes this source.
    """
    cache = load_cache(path)
    entries: Dict[str, Any] = dict(cache.get("steps") or {})
    known = {step.id: step for step in spec.STEPS}
    for step_id in step_ids:
        step = known.get(step_id)
        if step is None or not isinstance(entries.get(step_id), dict):
            raise ValueError(f"no cached summary for step '{step_id}'")
        entries[step_id]["fingerprint"] = _fingerprint(build_context(codebase, step))
        print(f"  Accepted the entry for '{step_id}' as written from its source.")
    save_cache(path, {"version": CACHE_VERSION, "steps": entries})


def step_summaries(codebase: Codebase, cache_path: Path) -> Dict[str, Dict[str, Any]]:
    """Return {step_id: summary} from the cache, without calling anything.

    The explanations are revised by hand: a build never asks a model to write
    one. A step whose cached entry was written from source that has since
    changed keeps that entry and is named here, and the check fails on it until
    the entry is revised and accepted with `--accept-summary`. A step the cache
    has never described gets the `spec.py` text.
    """
    entries: Dict[str, Any] = dict(load_cache(cache_path).get("steps") or {})
    results: Dict[str, Dict[str, Any]] = {}
    fresh = 0
    for step in spec.STEPS:
        cached = entries.get(step.id)
        if not isinstance(cached, dict) or not isinstance(cached.get("summary"), dict):
            results[step.id] = _fallback(step)
            continue
        results[step.id] = cached["summary"]
        if cached.get("fingerprint") == _fingerprint(build_context(codebase, step)):
            fresh += 1
        else:
            print(
                f"  '{step.id}' keeps an explanation written from source "
                "that has since changed."
            )
    print(f"  Summaries: {fresh} of {len(spec.STEPS)} current.")
    return results

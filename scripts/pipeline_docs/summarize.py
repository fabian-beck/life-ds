#!/usr/bin/env python3
"""AI-written explanations of each pipeline step, cached against the source.

Each step is summarized once from its own source, prompt template and output
schema. The summary is stored with a fingerprint of exactly those inputs, so a
rebuild only pays for the steps that actually changed—the same
staleness-by-fingerprint idea the translation pipeline uses for person data.

The summarizer reads the source but does not paraphrase it. What it writes is
a report entry: what the step contributes and why it is built that way, at the
level the surrounding prose argues at. Character budgets, field inventories,
and the counts a prompt happens to state are below that level, and the record
printed beside the text carries what is measurable anyway.

Without an API key (or with `--skip-ai`) the build falls back to the
hand-written one-liners in `spec.py`, so the chart always renders.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from . import spec
from .introspect import Codebase

CACHE_VERSION = 3
MAX_SOURCE_CHARS = 9000
MAX_PROMPT_CHARS = 6000

SYSTEM_PROMPT = (
    "You write the step entries of a technical report on a data-journalism "
    "pipeline, for the developer who wrote it and for researchers reading it "
    "later. You are given one processing step: its source, the prompt template "
    "it sends, and the structured output it asks for. Say what the step "
    "contributes to the story the pipeline is building and why it is built "
    "that way. Write at the level of the report around you, which argues about "
    "the design rather than restating it: no character budgets, no "
    "field-by-field inventory of the output, no counts or formatting rules "
    "quoted from the prompt. A specific constraint earns its place only where "
    "the design turns on it. The report prints the step's source, model, "
    "output schema, and dependencies beside your text, so leave those to it. "
    "Its register is plain and concrete. Name the thing that acts, prefer the "
    "active verb and the plain word over the impressive one, and call a thing "
    "what it is: a step reads an article and returns a place name, it does not "
    "ingest a source and emit a geographically resolvable location layer. "
    "Never stack abstract nouns where one concrete noun would do, and cut any "
    "adjective that only praises the design. Every clause carries part of the "
    "claim, so a sentence that merely restates its predecessor is dropped "
    "rather than rewritten. "
    "Never name a model, an API version or a vendor product: the record "
    "printed beside your text carries the model this step resolves, measured "
    "from the code, and a name repeated from a comment is how that record goes "
    "stale. Never address the reader, never use second person, and do not "
    "restate the step's name as a sentence. Open with the verb: the entry is "
    "printed under the step's name, so 'This step gathers the article' spends "
    "the opening on a subject the heading already gave, where 'Gathers the "
    "article' does not. Write in American English, and set "
    "em dashes closed up against the words they join, with no surrounding "
    "spaces, as the rest of the report does."
)


class StepSummary(BaseModel):
    """AI-written documentation for a single pipeline step."""

    what_it_does: str = Field(
        description=(
            "At most two sentences on what this step contributes to the story "
            "the pipeline is building: what it reads, what it decides, what it "
            "leaves behind."
        )
    )
    why_this_design: str = Field(
        description=(
            "One sentence on a non-obvious design decision visible in the "
            "source or prompt: an ordering constraint, a failure mode it "
            "guards, a budget it protects. Empty string if nothing stands out."
        )
    )


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


def build_context(codebase: Codebase, step: spec.Step) -> str:
    """Assemble everything the summarizer is allowed to see for one step."""
    parts = [
        f"STEP: {step.label}",
        f"PIPELINE: {spec.LANES[step.lane]['label']}",
        f"KIND: {step.kind}",
        f"SOURCE: {step.script} :: {step.function}",
        f"MAINTAINER NOTE: {step.summary}",
    ]
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
    is not stale: the build writes it, and without a key it falls back to the
    `spec.py` text, which is attributed to the maintainer rather than a model.
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
    return {
        "what_it_does": step.summary,
        "why_this_design": "",
        "source": "spec.py",
    }


def summarize_steps(
    codebase: Codebase,
    cache_path: Path,
    model: Optional[str] = None,
    skip_ai: bool = False,
    force: bool = False,
    verbose: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """Return {step_id: summary}, refreshing only steps whose source changed."""
    cache = load_cache(cache_path)
    entries: Dict[str, Any] = dict(cache.get("steps") or {})
    results: Dict[str, Dict[str, Any]] = {}

    client = None
    if not skip_ai:
        if not os.getenv("OPENAI_API_KEY"):
            print("  No OPENAI_API_KEY set—using the hand-written spec summaries.")
            skip_ai = True
        else:
            from openai import OpenAI

            client = OpenAI()

    if model is None:
        from config import DEFAULT_MODEL

        model = DEFAULT_MODEL

    from config import BULK_REASONING_EFFORT
    from utils.model_calls import parse_structured

    fresh = 0
    written = 0
    for step in spec.STEPS:
        context = build_context(codebase, step)
        fingerprint = _fingerprint(context)
        cached = entries.get(step.id)
        if not force and cached and cached.get("fingerprint") == fingerprint:
            results[step.id] = cached["summary"]
            fresh += 1
            continue
        if skip_ai or client is None:
            # Reached only when the fingerprint missed, so a cached entry here
            # describes source that has since changed. Rendering it silently is
            # how a refactor across twelve call sites reached the published page
            # under twelve explanations of the code it replaced.
            if cached:
                print(
                    f"  '{step.id}' keeps an explanation written from source "
                    "that has since changed."
                )
            results[step.id] = (cached or {}).get("summary") or _fallback(step)
            continue
        if verbose:
            print(f"  Summarizing {step.id} ({step.label})...")
        parsed = parse_structured(
            client,
            model=model,
            reasoning_effort=BULK_REASONING_EFFORT,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ],
            text_format=StepSummary,
            label=f"Step summary ({step.id})",
        )
        if parsed is None:
            print(f"  Falling back to the spec text for '{step.id}'.")
            results[step.id] = (cached or {}).get("summary") or _fallback(step)
            continue
        summary = parsed.model_dump()
        summary["source"] = model
        entries[step.id] = {"fingerprint": fingerprint, "summary": summary}
        results[step.id] = summary
        written += 1

    # Drop entries for steps that no longer exist, so a renamed or removed step
    # does not keep paying for cache space and reading as current.
    live = {step.id for step in spec.STEPS}
    stale = [step_id for step_id in entries if step_id not in live]
    for step_id in stale:
        del entries[step_id]

    if written or stale:
        save_cache(cache_path, {"version": CACHE_VERSION, "steps": entries})
    print(f"  Summaries: {fresh} cached, {written} regenerated.")
    return results

#!/usr/bin/env python3
"""Record what the pipeline actually sends and receives.

The static layer can show the prompt *template*; only a real run shows the
prompt with a biography poured into it, how long the phase took, how many
tokens it burned, and what came back. This module patches the OpenAI SDK's
request methods for the duration of a run and appends one JSON record per call.

It is deliberately non-invasive: nothing in `scripts/` imports it, and it
patches the resource classes rather than a client instance so it captures every
client the generators construct internally.

Captured text is truncated by default — a Phase 1 prompt carries whole
Wikipedia articles, and the point of the record is to show the *shape* of a
real call, not to vendor the encyclopedia into the repo.
"""

from __future__ import annotations

import inspect
import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from . import spec

DEFAULT_TRUNCATE = 4000
TRUNCATION_MARKER = "\n\n… [truncated by pipeline_docs.capture] …"


def _truncate(text: str, limit: Optional[int]) -> Tuple[str, int]:
    """Return (possibly shortened text, original length)."""
    original = len(text)
    if limit is None or original <= limit:
        return text, original
    head = limit * 2 // 3
    tail = limit - head
    return text[:head] + TRUNCATION_MARKER + text[-tail:], original


def _step_index() -> Dict[Tuple[str, str], str]:
    """(script basename, function name) -> step id, for stack attribution."""
    index: Dict[Tuple[str, str], str] = {}
    for step in spec.STEPS:
        index[(step.script.rsplit("/", 1)[-1], step.function)] = step.id
    return index


def _attribute_call() -> Tuple[Optional[str], str]:
    """Walk out of the SDK and find the pipeline function that made this call."""
    index = _step_index()
    fallback = "<unknown>"
    for frame_info in inspect.stack()[2:]:
        filename = os.path.basename(frame_info.filename)
        function = frame_info.function
        if "openai" in frame_info.filename.replace("\\", "/").split("/"):
            continue
        if filename == "capture.py":
            continue
        if fallback == "<unknown>":
            fallback = f"{filename}:{function}"
        step_id = index.get((filename, function))
        if step_id is not None:
            return step_id, f"{filename}:{function}"
    return None, fallback


def _messages_from(
    kwargs: Dict[str, Any], limit: Optional[int]
) -> List[Dict[str, Any]]:
    """Normalize `input=` (Responses API) and `messages=` (Chat API)."""
    raw = kwargs.get("input")
    if raw is None:
        raw = kwargs.get("messages")
    messages: List[Dict[str, Any]] = []
    if isinstance(raw, str):
        text, original = _truncate(raw, limit)
        return [{"role": "user", "content": text, "full_length": original}]
    if not isinstance(raw, list):
        return messages
    for item in raw:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if isinstance(content, list):
            parts = [
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and "text" in part
            ]
            content = "\n".join(parts)
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False, default=str)[:200]
        text, original = _truncate(content, limit)
        messages.append(
            {
                "role": str(item.get("role", "user")),
                "content": text,
                "full_length": original,
            }
        )
    return messages


def _schema_name(kwargs: Dict[str, Any]) -> Optional[str]:
    schema = kwargs.get("text_format") or kwargs.get("response_format")
    if schema is None:
        return None
    return getattr(schema, "__name__", None) or str(schema)[:80]


def _reasoning_effort(kwargs: Dict[str, Any]) -> Optional[str]:
    reasoning = kwargs.get("reasoning")
    if isinstance(reasoning, dict):
        effort = reasoning.get("effort")
        return str(effort) if effort is not None else None
    return None


def _usage(response: Any) -> Dict[str, Any]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    out: Dict[str, Any] = {}
    for key in (
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
    ):
        value = getattr(usage, key, None)
        if value is not None:
            out[key] = value
    details = getattr(usage, "output_tokens_details", None)
    reasoning_tokens = getattr(details, "reasoning_tokens", None)
    if reasoning_tokens is not None:
        out["reasoning_tokens"] = reasoning_tokens
    return out


def _result_payload(response: Any, limit: Optional[int]) -> Dict[str, Any]:
    """Extract the parsed structured output, or the raw text, from a response."""
    parsed = getattr(response, "output_parsed", None)
    if parsed is None:
        choices = getattr(response, "choices", None)
        if choices:
            message = getattr(choices[0], "message", None)
            parsed = getattr(message, "parsed", None)
            if parsed is None and message is not None:
                content = getattr(message, "content", None)
                if isinstance(content, str):
                    text, original = _truncate(content, limit)
                    return {"kind": "text", "text": text, "full_length": original}
    if parsed is not None:
        dumped = (
            parsed.model_dump()
            if hasattr(parsed, "model_dump")
            else json.loads(json.dumps(parsed, default=str))
        )
        rendered = json.dumps(dumped, indent=2, ensure_ascii=False, default=str)
        text, original = _truncate(rendered, limit)
        return {"kind": "structured", "text": text, "full_length": original}
    text_attr = getattr(response, "output_text", None)
    if isinstance(text_attr, str):
        text, original = _truncate(text_attr, limit)
        return {"kind": "text", "text": text, "full_length": original}
    data = getattr(response, "data", None)
    if data:
        return {
            "kind": "image",
            "text": f"{len(data)} image(s) returned",
            "full_length": 0,
        }
    return {"kind": "unknown", "text": "", "full_length": 0}


@dataclass
class Recorder:
    """Collects one record per model call."""

    truncate: Optional[int] = DEFAULT_TRUNCATE
    records: List[Dict[str, Any]] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)

    def record(
        self,
        method: str,
        kwargs: Dict[str, Any],
        response: Any,
        duration: float,
        error: Optional[str] = None,
    ) -> None:
        step_id, origin = _attribute_call()
        self.records.append(
            {
                "step": step_id,
                "origin": origin,
                "method": method,
                "model": kwargs.get("model"),
                "reasoning_effort": _reasoning_effort(kwargs),
                "schema": _schema_name(kwargs),
                "messages": _messages_from(kwargs, self.truncate),
                "result": (
                    {"kind": "error", "text": error, "full_length": len(error or "")}
                    if error
                    else _result_payload(response, self.truncate)
                ),
                "usage": _usage(response) if not error else {},
                "duration_s": round(duration, 3),
                "at": round(time.time() - self.started_at, 3),
            }
        )

    def to_json(self, label: str) -> Dict[str, Any]:
        return {
            "label": label,
            "recorded_at": time.strftime(
                "%Y-%m-%dT%H:%M:%S", time.gmtime(self.started_at)
            ),
            "truncate": self.truncate,
            "wall_clock_s": round(time.time() - self.started_at, 1),
            "calls": self.records,
        }


# Resource classes patched, as (module path, class name, method names).
_TARGETS: List[Tuple[str, str, Tuple[str, ...]]] = [
    ("openai.resources.responses.responses", "Responses", ("create", "parse")),
    (
        "openai.resources.chat.completions.completions",
        "Completions",
        ("create", "parse"),
    ),
    ("openai.resources.images", "Images", ("generate", "edit")),
]


@contextmanager
def recording(truncate: Optional[int] = DEFAULT_TRUNCATE) -> Iterator[Recorder]:
    """Patch the SDK for the duration of the block and collect every call."""
    import importlib

    recorder = Recorder(truncate=truncate)
    undo: List[Tuple[Any, str, Any]] = []

    for module_path, class_name, methods in _TARGETS:
        try:
            module = importlib.import_module(module_path)
            target = getattr(module, class_name)
        except (ImportError, AttributeError):
            continue  # SDK layout differs; the other targets still record
        for method_name in methods:
            original = getattr(target, method_name, None)
            if original is None:
                continue

            def make_wrapper(original_method: Any, label: str) -> Any:
                def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
                    start = time.perf_counter()
                    try:
                        response = original_method(self, *args, **kwargs)
                    except Exception as error:  # record failures too
                        recorder.record(
                            label,
                            kwargs,
                            None,
                            time.perf_counter() - start,
                            error=f"{type(error).__name__}: {error}",
                        )
                        raise
                    recorder.record(
                        label, kwargs, response, time.perf_counter() - start
                    )
                    return response

                return wrapper

            setattr(
                target,
                method_name,
                make_wrapper(original, f"{class_name.lower()}.{method_name}"),
            )
            undo.append((target, method_name, original))

    try:
        yield recorder
    finally:
        for target, method_name, original in undo:
            setattr(target, method_name, original)


def write_record(recorder: Recorder, label: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(recorder.to_json(label), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def merge_records(paths: List[Path]) -> Dict[str, Any]:
    """Combine several recorded runs (e.g. one person, one meta story)."""
    runs: List[Dict[str, Any]] = []
    for path in paths:
        if path.exists():
            runs.append(json.loads(path.read_text(encoding="utf-8")))
    return {"runs": runs}

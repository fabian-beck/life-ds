#!/usr/bin/env python3
"""The one place the pipeline talks to a model.

Every step that fills a schema calls :func:`parse_structured`, which is a thin
layer over the Responses API. It exists to make three things true of every call
in the pipeline rather than of whichever call a maintainer happened to write
carefully:

**One API.** The pipeline used two — ``responses.parse`` in most steps and
``beta.chat.completions.parse`` in six — and the second silently ran at the
model's default reasoning effort while `config.py` documented effort as a
per-step setting. Effort is now a required argument, so a call site cannot
omit it and inherit whatever the model does by default.

**Retry what is worth retrying.** A connection that dropped, a rate limit, a
502: the same request will likely succeed a moment later. A malformed request
or a refusal will not, and retrying it three times spends money to arrive at
the same answer more slowly. Only the first kind is retried, with a widening
delay; the second returns immediately.

**One shape for failure.** The call returns the parsed object, or ``None`` when
the model produced nothing usable — for any reason, already logged with the
step's name. Callers decide what that means, because only they know: some fall
back to a deterministic answer, some skip an optional section, and curation
stops the run rather than let a story keep every event of every life. The
steps in that last group call :func:`parse_structured_or_raise`, which is the
same call ending in a :class:`ModelCallFailed` instead of a ``None`` nobody
downstream would know how to interpret.

**One cache breakpoint per shared prefix.** A step that researches sixteen
events sends the same article, the same second source and the same
instructions sixteen times. The provider reuses a repeated prefix only up to a
breakpoint that a request wrote, and the one it places by itself covers the
whole prompt — which every call ends differently, so nothing ever matched and
every call wrote a prefix no later call could use. A call site marks where its
reusable part ends with :func:`ends_prompt_prefix`, or hands over a
:class:`Prompt` that already knows, and the breakpoint goes there.

The parsed object is *not* validated here beyond its schema. Identifiers still
have to be matched against real entities, and lists against the source they
must align with, in the step that knows what they mean.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple, Type, TypeVar, cast

from openai import APIConnectionError, APIStatusError, OpenAI
from pydantic import BaseModel

from . import usage

ParsedT = TypeVar("ParsedT", bound=BaseModel)

# Statuses worth trying again: the request was fine, the service was not.
# 409 is included because a conflict here is a concurrent-request artifact
# rather than a statement about the request itself.
RETRYABLE_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})

DEFAULT_ATTEMPTS = 3
BACKOFF_SECONDS = 2.0
"""Delay before attempt N+1, multiplied by N — 2 s, then 4 s."""

PREFIX_END_KEY = "ends_prompt_prefix"
"""Marks the message a request's reusable prefix ends at. Stripped before the wire."""

CACHE_BREAKPOINT = {"mode": "explicit"}
"""The breakpoint itself, as the API spells it."""


def ends_prompt_prefix(message: Dict[str, Any]) -> Dict[str, Any]:
    """Say that the reusable part of the prompt ends with ``message``.

    Everything up to and including it is what the step's calls have in common;
    what follows is this call's own. The marker travels as a key on the message
    rather than as a separate argument so that a caller assembling a list of
    turns marks the boundary where it builds it.
    """
    return {**message, PREFIX_END_KEY: True}


@dataclass(frozen=True)
class Prompt:
    """One prompt, cut where the part its step repeats ends.

    The research of an event and the report on one are each written against a
    life's own article, its second source and a fixed task description, with
    only the event, its class and its articles differing. Held as two strings
    the split survives to the call site, which turns it into the two messages
    the breakpoint sits between; joined into one string it would have to be cut
    again by searching for a heading.
    """

    shared: str
    specific: str

    @property
    def text(self) -> str:
        """The whole prompt, the way a reader or a test sees it."""
        return self.shared + self.specific

    def messages(self, system: str) -> List[Dict[str, Any]]:
        """The input for :func:`parse_structured`, the prefix marked.

        A life whose article was never cached leaves ``shared`` empty. There is
        then no prefix to reuse, and the prompt goes as the single message it
        was before, rather than as an empty turn carrying a breakpoint.
        """
        if not self.shared:
            return [
                {"role": "system", "content": system},
                {"role": "user", "content": self.specific},
            ]
        return [
            {"role": "system", "content": system},
            ends_prompt_prefix({"role": "user", "content": self.shared}),
            {"role": "user", "content": self.specific},
        ]


def _content_blocks(content: Any) -> Optional[List[Dict[str, Any]]]:
    """``content`` as blocks a breakpoint can be attached to, or None.

    A message is usually a plain string, which the API also takes as a single
    text block; a breakpoint is a field of a block, so the string has to become
    one. Content that is already a list of blocks keeps them.
    """
    if isinstance(content, str):
        return [{"type": "input_text", "text": content}] if content else None
    if isinstance(content, list) and content:
        return [dict(block) for block in content]
    return None


def _with_breakpoint(content: Any) -> Optional[List[Dict[str, Any]]]:
    """``content`` with the prefix ending after its last block."""
    blocks = _content_blocks(content)
    if blocks is None:
        return None
    blocks[-1] = {**blocks[-1], "prompt_cache_breakpoint": dict(CACHE_BREAKPOINT)}
    return blocks


def _prefix_cache_key(model: str, prefix: Sequence[Dict[str, Any]]) -> str:
    """A routing key the calls sharing ``prefix`` arrive at independently.

    The provider routes by this key, so two calls that could reuse a prefix
    have to send the same one. Hashing the prefix itself is the only version of
    that which cannot drift: no call site names its key, and a prompt that
    changed by a character stops claiming the entry written for the old one.
    """
    material = json.dumps(
        [model, list(prefix)], sort_keys=True, ensure_ascii=False, default=str
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def _prepare_input(
    model: str, input: Sequence[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """The messages as the API takes them, and the caching arguments they earn.

    Requests with no marked message are sent exactly as before, which is what
    the call sites whose prompts repeat nothing want: an explicit mode with no
    breakpoint in it would cache nothing at all.
    """
    messages: List[Dict[str, Any]] = []
    prefix: Optional[List[Dict[str, Any]]] = None
    for original in input:
        message = dict(original)
        marked = bool(message.pop(PREFIX_END_KEY, False))
        if marked:
            blocks = _with_breakpoint(message.get("content"))
            marked = blocks is not None
            if blocks is not None:
                message["content"] = blocks
        messages.append(message)
        if marked and prefix is None:
            # The first boundary, not the last: it is the one the whole step
            # shares, and a later one is shared by fewer of its calls.
            prefix = list(messages)
    if prefix is None:
        return messages, {}
    return messages, {
        "prompt_cache_key": _prefix_cache_key(model, prefix),
        # Without this the provider adds a breakpoint of its own at the end of
        # the prompt, and writes a prefix that ends with this call's own event.
        "prompt_cache_options": {"mode": "explicit"},
    }


_shared_client: Optional[OpenAI] = None


class MissingApiKey(RuntimeError):
    """OPENAI_API_KEY is not set, so no model can be called."""


class ModelCallFailed(RuntimeError):
    """A call that had to succeed did not.

    Subclasses RuntimeError because that is what the steps raised when each
    of them classified its own API errors, and their callers still catch it.
    """


def get_client() -> OpenAI:
    """The one OpenAI client the process shares.

    Every ``OpenAI(...)`` construction opens its own HTTP connection pool, so
    a script that builds a client per step — or per call, inside a loop —
    pays a fresh TLS handshake for requests that could have reused a
    connection. Subclassing RuntimeError keeps the callers that guarded the
    old per-site constructions with ``except RuntimeError`` working unchanged.
    """
    global _shared_client
    if _shared_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise MissingApiKey("OPENAI_API_KEY is not set.")
        _shared_client = OpenAI(api_key=api_key)
    return _shared_client


def is_retryable(error: Exception) -> bool:
    """Whether trying the identical request again could plausibly work.

    A dropped connection or a timeout is transient by definition. A status
    error is transient only for the codes above: a 400 means the request itself
    is wrong, and a 401 will still be wrong in two seconds.
    """
    if isinstance(error, APIConnectionError):  # includes APITimeoutError
        return True
    if isinstance(error, APIStatusError):
        return error.status_code in RETRYABLE_STATUS
    return False


def _refusal(response: Any) -> Optional[str]:
    """The refusal text, if the model declined rather than answered.

    Chat completions exposed this as a field on the message; the Responses API
    puts it in the output as a content part, so it has to be looked for. Walked
    defensively: a shape this does not recognize simply yields no refusal, and
    the caller reports the ordinary "nothing parsed" instead.
    """
    for item in getattr(response, "output", None) or []:
        for part in getattr(item, "content", None) or []:
            text = getattr(part, "refusal", None)
            if text:
                return str(text)
    return None


def _why_empty(response: Any) -> str:
    """Say what came back instead of a parsed object, for the log."""
    refusal = _refusal(response)
    if refusal:
        return f"the model refused: {refusal}"
    status = getattr(response, "status", None)
    details = getattr(response, "incomplete_details", None)
    reason = getattr(details, "reason", None)
    if reason:
        return f"the response was {status} ({reason})"
    error = getattr(response, "error", None)
    if error:
        return f"the response reported {getattr(error, 'message', error)}"
    return f"the response was {status} with nothing parsed"


def parse_structured(
    client: OpenAI,
    *,
    model: str,
    reasoning_effort: str,
    input: Sequence[Dict[str, Any]],
    text_format: Type[ParsedT],
    label: str,
    attempts: int = DEFAULT_ATTEMPTS,
) -> Optional[ParsedT]:
    """Fill ``text_format`` from the model, or return ``None`` having said why.

    ``label`` names the step in log lines, so a warning in a run of thirty
    calls says which one gave up. ``attempts`` bounds only the retryable
    failures; a refusal or a bad request ends the call at once.
    """
    parsed, _ = _parse_structured(
        client,
        model=model,
        reasoning_effort=reasoning_effort,
        input=input,
        text_format=text_format,
        label=label,
        attempts=attempts,
    )
    return parsed


def parse_structured_or_raise(
    client: OpenAI,
    *,
    model: str,
    reasoning_effort: str,
    input: Sequence[Dict[str, Any]],
    text_format: Type[ParsedT],
    label: str,
    attempts: int = DEFAULT_ATTEMPTS,
) -> ParsedT:
    """The same call for the steps that must stop the run rather than go on.

    Most callers can absorb a ``None``: an optional section is skipped, a
    deterministic answer stands in, a batch is left unrated. Curation cannot.
    A person's dataset with no events, a network with no ties, a review that
    reports nothing — each is worse than no output at all, because it would be
    written to disk and read later as a finding.

    Those steps raised before this wrapper existed and still do. What changes
    is that they now retry the failures worth retrying first, and that the
    reason they give is the same sentence every other step would have logged.
    """
    parsed, reason = _parse_structured(
        client,
        model=model,
        reasoning_effort=reasoning_effort,
        input=input,
        text_format=text_format,
        label=label,
        attempts=attempts,
    )
    if parsed is None:
        raise ModelCallFailed(f"{label} produced no usable result: {reason}")
    return parsed


def _parse_structured(
    client: OpenAI,
    *,
    model: str,
    reasoning_effort: str,
    input: Sequence[Dict[str, Any]],
    text_format: Type[ParsedT],
    label: str,
    attempts: int = DEFAULT_ATTEMPTS,
) -> "tuple[Optional[ParsedT], str]":
    """The call itself, paired with the reason it gave up.

    The reason is already printed on the way out, so ``parse_structured``
    drops it; only the raising variant needs it a second time, to put in the
    exception a caller will surface far from this log line.
    """
    messages, caching = _prepare_input(model, input)
    last_error = ""

    for attempt in range(1, max(1, attempts) + 1):
        try:
            response = client.responses.parse(
                model=model,
                reasoning=cast(Any, {"effort": reasoning_effort}),
                input=cast(Any, messages),
                text_format=text_format,
                **cast(Any, caching),
            )
        except Exception as error:  # noqa: BLE001 — classified immediately below
            reason = f"{type(error).__name__}: {error}"
            if not is_retryable(error):
                print(f"  Error: {label} failed: {reason}")
                return None, reason
            last_error = reason
        else:
            # Recorded before the result is inspected: a refused or empty
            # response consumed tokens too, and a step that spent them without
            # producing anything is exactly what the ledger should show.
            usage.record_response(model, response, label=label)
            parsed = getattr(response, "output_parsed", None)
            if parsed is not None:
                return cast(ParsedT, parsed), ""
            refusal = _refusal(response)
            if refusal:
                print(f"  Error: {label} was refused: {refusal}")
                return None, f"the model refused: {refusal}"
            last_error = _why_empty(response)

        if attempt < attempts:
            print(f"  Retry {attempt}/{attempts - 1} for {label}: {last_error}")
            time.sleep(BACKOFF_SECONDS * attempt)

    print(f"  Error: {label} failed after {attempts} attempt(s): {last_error}")
    return None, last_error

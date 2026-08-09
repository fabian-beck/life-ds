#!/usr/bin/env python3
"""The one place the pipeline talks to a model.

Every phase that fills a schema calls :func:`parse_structured`, which is a thin
layer over the Responses API. It exists to make three things true of every call
in the pipeline rather than of whichever call a maintainer happened to write
carefully:

**One API.** The pipeline used two — ``responses.parse`` in most phases and
``beta.chat.completions.parse`` in six — and the second silently ran at the
model's default reasoning effort while `config.py` documented effort as a
per-phase setting. Effort is now a required argument, so a call site cannot
omit it and inherit whatever the model does by default.

**Retry what is worth retrying.** A connection that dropped, a rate limit, a
502: the same request will likely succeed a moment later. A malformed request
or a refusal will not, and retrying it three times spends money to arrive at
the same answer more slowly. Only the first kind is retried, with a widening
delay; the second returns immediately.

**One shape for failure.** The call returns the parsed object, or ``None`` when
the model produced nothing usable — for any reason, already logged with the
phase's name. Callers decide what that means, because only they know: some fall
back to a deterministic answer, some skip an optional section, and curation
stops the run rather than let a story keep every event of every life.

The parsed object is *not* validated here beyond its schema. Identifiers still
have to be matched against real entities, and lists against the source they
must align with, in the phase that knows what they mean.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional, Sequence, Type, TypeVar, cast

from openai import APIConnectionError, APIStatusError, OpenAI
from pydantic import BaseModel

ParsedT = TypeVar("ParsedT", bound=BaseModel)

# Statuses worth trying again: the request was fine, the service was not.
# 409 is included because a conflict here is a concurrent-request artifact
# rather than a statement about the request itself.
RETRYABLE_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})

DEFAULT_ATTEMPTS = 3
BACKOFF_SECONDS = 2.0
"""Delay before attempt N+1, multiplied by N — 2 s, then 4 s."""

_shared_client: Optional[OpenAI] = None


class MissingApiKey(RuntimeError):
    """OPENAI_API_KEY is not set, so no model can be called."""


def get_client() -> OpenAI:
    """The one OpenAI client the process shares.

    Every ``OpenAI(...)`` construction opens its own HTTP connection pool, so
    a script that builds a client per phase — or per call, inside a loop —
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
    input: Sequence[Dict[str, str]],
    text_format: Type[ParsedT],
    label: str,
    attempts: int = DEFAULT_ATTEMPTS,
) -> Optional[ParsedT]:
    """Fill ``text_format`` from the model, or return ``None`` having said why.

    ``label`` names the phase in log lines, so a warning in a run of thirty
    calls says which one gave up. ``attempts`` bounds only the retryable
    failures; a refusal or a bad request ends the call at once.
    """
    messages: List[Dict[str, str]] = [dict(message) for message in input]
    last_error = ""

    for attempt in range(1, max(1, attempts) + 1):
        try:
            response = client.responses.parse(
                model=model,
                reasoning=cast(Any, {"effort": reasoning_effort}),
                input=cast(Any, messages),
                text_format=text_format,
            )
        except Exception as error:  # noqa: BLE001 — classified immediately below
            if not is_retryable(error):
                print(f"  Error: {label} failed: {type(error).__name__}: {error}")
                return None
            last_error = f"{type(error).__name__}: {error}"
        else:
            parsed = getattr(response, "output_parsed", None)
            if parsed is not None:
                return cast(ParsedT, parsed)
            refusal = _refusal(response)
            if refusal:
                print(f"  Error: {label} was refused: {refusal}")
                return None
            last_error = _why_empty(response)

        if attempt < attempts:
            print(f"  Retry {attempt}/{attempts - 1} for {label}: {last_error}")
            time.sleep(BACKOFF_SECONDS * attempt)

    print(f"  Error: {label} failed after {attempts} attempt(s): {last_error}")
    return None

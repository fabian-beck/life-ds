#!/usr/bin/env python3
"""Shared configuration for generation scripts."""

import os
import sys
from pathlib import Path

# Repository layout. Every script derives its paths from here so the layout is
# declared once rather than re-spelled per file.
REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
PEOPLE_DIR = DATA_DIR / "people"
META_STORIES_DIR = DATA_DIR / "meta_stories"
REGISTER_PATH = DATA_DIR / "persons.json"
META_STORIES_REGISTER = DATA_DIR / "meta_stories.json"
PUBLIC_DIR = REPO_ROOT / "public"
PORTRAITS_DIR = PUBLIC_DIR / "portraits"

# OpenAI API configuration
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-terra")
COMPOSER_DEFAULT_MODEL = os.getenv("OPENAI_COMPOSER_MODEL", "gpt-5.6-sol")
BULK_MODEL = os.getenv("OPENAI_BULK_MODEL", "gpt-5.6-luna")
"""The small model, for call sites whose output is checkable or replaceable.

A step qualifies when a wrong answer cannot quietly become part of the corpus:
its output is either constrained by a schema that is validated against existing
entities afterwards, rewritten by a later step, or backed by a deterministic
fallback. Steps that decide what a life or a theme *is*, that read a whole
document at once, or that criticize another step's output keep DEFAULT_MODEL —
a critic weaker than the generator is worse than no critic, and the small model
is weakest at recalling detail from a long context.
"""

GLOSSARY_MODEL = DEFAULT_MODEL
"""The model for the calls that settle a document's vocabulary before it is written.

Translation itself runs on the small model, and a glossary call is the
exception: it is one small call per document and language, and everything
downstream matches on what it decides. A name rendered two ways is a broken
cross-reference rather than an awkward sentence, and a metaphor rendered
literally once is rendered literally in every passage that repeats it.
"""

DEFAULT_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "medium")
LOW_REASONING_EFFORT = os.getenv("OPENAI_LOW_REASONING_EFFORT", "none")
BULK_REASONING_EFFORT = os.getenv("OPENAI_BULK_REASONING_EFFORT", "low")
GLOSSARY_REASONING_EFFORT = BULK_REASONING_EFFORT
"""Reasoning budget for the glossary calls. Between LOW and DEFAULT for the
same reason as BULK: the call holds a threshold — whether a name has an exonym,
whether a language has an image — rather than transcribing what it was given."""
"""Reasoning budget for bulk call sites that still make a judgment.

Between LOW (slot filling from supplied text) and DEFAULT (interpretation).
The small model needs a little deliberation exactly where it is asked to hold a
threshold or pick one option out of many — classifying an event against a
rubric, choosing which image is a portrait — and none where it is transcribing
what a prompt already contains.
"""


def enable_utf8_console() -> None:
    """Make stdout/stderr accept the non-ASCII characters the scripts print.

    On Windows the default encoding is cp1252 whenever output is redirected
    (a log file, a subprocess pipe), so a status line containing a check mark
    raises UnicodeEncodeError. In a phase wrapped in a broad except that shows
    up as the phase "failing" for a reason unrelated to its work — that is how
    a meta story's translation step got skipped while the run still reported
    success.

    Only the interpreter's own streams are reconfigured. A stream someone else
    installed belongs to them: reconfiguring pytest's capture object closes the
    temporary file pytest reads afterwards, which ends the run in "no tests
    ran" no matter which module imported this one.

    Note: reconfigure() rather than a fresh TextIOWrapper around the buffer —
    replacing the stream orphans the original wrapper, which closes the buffer
    when it is collected and leaves the interpreter with a dead stdout.
    """
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None or stream is not getattr(sys, f"__{name}__", None):
            continue  # a capture object or a redirect the caller owns
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        if (getattr(stream, "encoding", "") or "").lower().replace("-", "") == "utf8":
            continue
        reconfigure(encoding="utf-8", errors="replace")

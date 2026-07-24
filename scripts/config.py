#!/usr/bin/env python3
"""Shared configuration for generation scripts."""

import os
import sys

# OpenAI API configuration
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-terra")
DEFAULT_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "medium")
LOW_REASONING_EFFORT = os.getenv("OPENAI_LOW_REASONING_EFFORT", "none")


def enable_utf8_console() -> None:
    """Make stdout/stderr accept the non-ASCII characters the scripts print.

    On Windows the default encoding is cp1252 whenever output is redirected
    (a log file, a subprocess pipe), so a status line containing a check mark
    raises UnicodeEncodeError. In a phase wrapped in a broad except that shows
    up as the phase "failing" for a reason unrelated to its work — that is how
    a meta story's translation step got skipped while the run still reported
    success.

    Note: reconfigure() rather than a fresh TextIOWrapper around the buffer —
    replacing the stream orphans the original wrapper, which closes the buffer
    when it is collected and leaves the interpreter with a dead stdout.
    """
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue  # replaced by a capture object without reconfigure()
        if (getattr(stream, "encoding", "") or "").lower().replace("-", "") == "utf8":
            continue
        reconfigure(encoding="utf-8", errors="replace")

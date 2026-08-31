"""Tests for the console encoding fix the generation scripts apply on import.

Every generation script calls ``enable_utf8_console()`` at import time, so the
function runs inside whatever process imports one — a test runner included.
Reconfiguring a stream the runner installed closes the file it reads
afterwards, which aborts the whole run before a single test reports.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from config import enable_utf8_console  # noqa: E402


class FakeStream:
    """A text stream that records the reconfigure() calls it receives."""

    def __init__(self, encoding: str) -> None:
        self.encoding = encoding
        self.reconfigured: list[dict] = []

    def reconfigure(self, **kwargs) -> None:
        self.reconfigured.append(kwargs)
        self.encoding = kwargs.get("encoding", self.encoding)


class EnableUtf8ConsoleTest(unittest.TestCase):
    def setUp(self) -> None:
        # Every case is about stdout; hold stderr at UTF-8 so the function has
        # nothing to do there and the process keeps the stderr it started with.
        self._install("stderr", FakeStream("utf-8"), own=True)

    def _install(self, name: str, stream, *, own: bool) -> FakeStream:
        """Put ``stream`` on sys.<name>, and on sys.__<name>__ when it is ours."""
        for attribute in (name, f"__{name}__") if own else (name,):
            original = getattr(sys, attribute)
            setattr(sys, attribute, stream)
            self.addCleanup(setattr, sys, attribute, original)
        return stream

    def test_reconfigures_the_interpreters_own_stream(self):
        stdout = self._install("stdout", FakeStream("cp1252"), own=True)

        enable_utf8_console()

        self.assertEqual(
            stdout.reconfigured, [{"encoding": "utf-8", "errors": "replace"}]
        )

    def test_leaves_a_stream_someone_else_installed_alone(self):
        own = self._install("stdout", FakeStream("cp1252"), own=True)
        capture = self._install("stdout", FakeStream("cp1252"), own=False)

        enable_utf8_console()

        self.assertEqual(capture.reconfigured, [])
        self.assertEqual(own.reconfigured, [])

    def test_leaves_a_stream_that_is_already_utf8_alone(self):
        stdout = self._install("stdout", FakeStream("UTF-8"), own=True)

        enable_utf8_console()

        self.assertEqual(stdout.reconfigured, [])

    def test_survives_a_stream_without_reconfigure(self):
        class Bare:
            encoding = "cp1252"

        self._install("stdout", Bare(), own=True)

        enable_utf8_console()  # must not raise

    def test_survives_a_missing_stream(self):
        self._install("stdout", None, own=True)

        enable_utf8_console()  # must not raise


if __name__ == "__main__":
    unittest.main()

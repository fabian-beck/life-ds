"""Tests for Phase 3 curation of a meta story.

The phase asks for one to three essential events per person out of every dated
event of their lives. So the only dangerous answer to a failed call is "all of
them" — it inverts the phase — and the only dangerous thing to write into
``theme_connection`` is prose about the pipeline, because the timeline prints
that field to the reader as the event's description.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_meta_story as meta  # noqa: E402


def _events(count: int = 2) -> list:
    return [
        {
            "person_id": "ada_lovelace",
            "person_name": "Ada Lovelace",
            "event_index": index,
            "event": {"title": f"Event {index}", "date": "1843", "description": "..."},
        }
        for index in range(count)
    ]


def _client(*messages) -> Mock:
    client = Mock()
    client.beta.chat.completions.parse.side_effect = [
        (
            message
            if isinstance(message, Exception)
            else Mock(choices=[Mock(message=message)])
        )
        for message in messages
    ]
    return client


def _parsed(*decisions) -> Mock:
    return Mock(
        parsed=Mock(
            decisions=[
                Mock(event_id=event_id, is_relevant=relevant, theme_connection=text)
                for event_id, relevant, text in decisions
            ]
        )
    )


class FilterEventBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch.object(meta.time, "sleep")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_failed_batch_is_retried_then_raises(self) -> None:
        client = _client(*[RuntimeError("upstream is down")] * 3)
        with self.assertRaises(meta.FilteringFailed) as raised:
            meta._filter_event_batch(_events(), "topic", client, "gpt", False)

        self.assertEqual(
            client.beta.chat.completions.parse.call_count, meta.FILTER_BATCH_ATTEMPTS
        )
        self.assertIn("upstream is down", str(raised.exception))

    def test_an_unparsed_response_raises_rather_than_including_everything(self) -> None:
        client = _client(*[Mock(parsed=None)] * meta.FILTER_BATCH_ATTEMPTS)
        with self.assertRaises(meta.FilteringFailed):
            meta._filter_event_batch(_events(), "topic", client, "gpt", False)

    def test_a_retry_that_succeeds_returns_the_decisions(self) -> None:
        client = _client(
            RuntimeError("transient"),
            _parsed(("ada_lovelace:0", True, "The first program.")),
        )
        decisions = meta._filter_event_batch(_events(), "topic", client, "gpt", False)

        self.assertEqual(client.beta.chat.completions.parse.call_count, 2)
        self.assertEqual(
            decisions,
            {
                "ada_lovelace:0": {
                    "is_relevant": True,
                    "theme_connection": "The first program.",
                }
            },
        )

    def test_no_fallback_text_is_written_into_a_reader_visible_field(self) -> None:
        """The strings the old fallbacks wrote must not exist in the source."""
        source = Path(meta.__file__).read_text(encoding="utf-8")
        for placeholder in (
            "included by default",
            "Included without AI filtering",
        ):
            self.assertNotIn(placeholder, source)


if __name__ == "__main__":
    unittest.main()

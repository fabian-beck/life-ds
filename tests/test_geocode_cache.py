"""Tests for the geocoder cache in the person-events pipeline.

Nominatim asks for one request per second, and each location is expanded into
several candidate spellings. So what matters here is that an answer is asked for
once — including the answer "this place does not resolve" — while a lookup that
merely failed to reach the geocoder stays open for a later attempt.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_person_events as events  # noqa: E402


def _response(payload: object) -> Mock:
    response = Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


class GeocodeCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.cache_path = Path(self._temp.name) / "geocode.json"

        patcher = patch.multiple(
            events,
            GEOCODE_CACHE_PATH=self.cache_path,
            GEOCODER_DELAY_SECONDS=0.0,
            GEOCODER_MAX_ATTEMPTS=2,
            _geocode_cache={},
            _geocode_cache_loaded=False,
            _geocode_failures=set(),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _reset_in_memory(self) -> None:
        """Forget everything this process learned, keeping the file on disk."""
        events._geocode_cache.clear()
        events._geocode_failures.clear()
        events._geocode_cache_loaded = False

    def test_an_unresolvable_place_is_queried_once(self) -> None:
        with patch.object(
            events.requests, "get", return_value=_response([])
        ) as request:
            self.assertIsNone(events.geocode_location("Nowhere At All"))
            calls_after_first = request.call_count
            self.assertIsNone(events.geocode_location("Nowhere At All"))
            self.assertEqual(request.call_count, calls_after_first)

    def test_a_confirmed_miss_survives_into_the_next_run(self) -> None:
        with patch.object(events.requests, "get", return_value=_response([])):
            self.assertIsNone(events.geocode_location("Nowhere At All"))

        self._reset_in_memory()
        with patch.object(
            events.requests, "get", return_value=_response([])
        ) as request:
            self.assertIsNone(events.geocode_location("Nowhere At All"))
        request.assert_not_called()

    def test_a_hit_is_cached_on_disk(self) -> None:
        hit = _response([{"lon": "13.4", "lat": "52.5", "display_name": "Berlin"}])
        with patch.object(events.requests, "get", return_value=hit):
            first = events.geocode_location("Berlin")
        self.assertIsNotNone(first)

        stored = json.loads(self.cache_path.read_text(encoding="utf-8"))
        self.assertIn("Berlin", stored)

        self._reset_in_memory()
        with patch.object(events.requests, "get", return_value=hit) as request:
            second = events.geocode_location("Berlin")
        request.assert_not_called()
        self.assertEqual(second, first)

    def test_a_transient_failure_is_retried_and_not_remembered(self) -> None:
        with patch.object(
            events.requests, "get", side_effect=OSError("connection reset")
        ) as request:
            self.assertIsNone(events.geocode_location("Berlin"))
        # Every candidate spelling gets the full retry budget.
        self.assertEqual(request.call_count, events.GEOCODER_MAX_ATTEMPTS)
        self.assertFalse(self.cache_path.exists())

        self._reset_in_memory()
        hit = _response([{"lon": "13.4", "lat": "52.5", "display_name": "Berlin"}])
        with patch.object(events.requests, "get", return_value=hit):
            self.assertIsNotNone(events.geocode_location("Berlin"))

    def test_a_transient_failure_is_not_repeated_within_a_run(self) -> None:
        with patch.object(
            events.requests, "get", side_effect=OSError("connection reset")
        ) as request:
            self.assertIsNone(events.geocode_location("Berlin"))
            calls_after_first = request.call_count
            self.assertIsNone(events.geocode_location("Berlin"))
            self.assertEqual(request.call_count, calls_after_first)

    def test_an_unreadable_cache_file_is_ignored(self) -> None:
        self.cache_path.write_text("{ this is not json", encoding="utf-8")
        hit = _response([{"lon": "13.4", "lat": "52.5", "display_name": "Berlin"}])
        with patch.object(events.requests, "get", return_value=hit):
            self.assertIsNotNone(events.geocode_location("Berlin"))


if __name__ == "__main__":
    unittest.main()

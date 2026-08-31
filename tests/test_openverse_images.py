"""Openverse candidates must survive the quality filter they are scored by.

`search_openverse` used to build its candidates without the width, height,
size, and mime fields the quality filter reads, so every candidate scored as a
0x0-pixel image and was rejected before scoring began — 20 HTTP queries per
person whose results never once reached the matcher. The fields are now copied
from the API response, the file-size hard filter treats an unreported size as
unknown rather than as too small (Openverse returns no filesize for Flickr and
museum providers), and wikimedia-provider results are dropped because the
Commons search already covers them under URL forms the exact-URL dedup cannot
match.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from events.images.scoring import calculate_image_quality_score  # noqa: E402
from events.images.sources import search_openverse  # noqa: E402

# The response shape the Openverse API actually returns, one item per case the
# search must handle: a Commons duplicate, a Flickr photograph without size or
# filetype, and a Wikimedia-hosted file with both.
API_RESULTS = [
    {
        "url": "https://upload.wikimedia.org/wikipedia/commons/1/1a/Campus.jpg",
        "title": "Emmy Noether campus",
        "provider": "wikimedia",
        "width": 4168,
        "height": 2824,
        "filesize": 2920412,
        "filetype": "jpg",
        "license": "by-sa",
        "license_version": "4.0",
    },
    {
        "url": "https://live.staticflickr.com/123/noether.jpg",
        "title": "Emmy Noether",
        "provider": "flickr",
        "foreign_landing_url": "https://www.flickr.com/photos/x/123",
        "creator": "Somebody",
        "width": 630,
        "height": 1024,
        "filesize": None,
        "filetype": None,
        "license": "by",
        "license_version": "2.0",
    },
    {
        "url": "https://museum.example.org/tiny.jpg",
        "title": "Tiny scan",
        "provider": "smithsonian",
        "width": 100,
        "height": 80,
        "filesize": None,
        "filetype": None,
        "license": "cc0",
        "license_version": "1.0",
    },
]


def _search() -> list:
    response = Mock()
    response.json.return_value = {"results": API_RESULTS}
    response.raise_for_status.return_value = None
    with patch("events.images.sources.requests.get", return_value=response):
        return search_openverse("Emmy Noether")


class OpenverseSearchTests(unittest.TestCase):
    def test_wikimedia_provider_results_are_dropped(self) -> None:
        providers = [img["provider"] for img in _search()]
        self.assertEqual(providers, ["flickr", "smithsonian"])

    def test_dimension_fields_reach_the_candidate(self) -> None:
        flickr = _search()[0]
        self.assertEqual(flickr["width"], 630)
        self.assertEqual(flickr["height"], 1024)
        self.assertEqual(flickr["size"], 0)
        self.assertEqual(flickr["mime"], "")
        self.assertEqual(flickr["license"], "CC BY 2.0")


class QualityFilterTests(unittest.TestCase):
    def test_unknown_filesize_is_not_too_small(self) -> None:
        flickr = _search()[0]
        self.assertGreaterEqual(
            calculate_image_quality_score(flickr, "Emmy Noether"), 0
        )

    def test_reported_bad_filesize_is_still_rejected(self) -> None:
        candidate = {**_search()[0], "size": 5_000}
        self.assertEqual(calculate_image_quality_score(candidate, "Emmy Noether"), -1.0)

    def test_tiny_image_is_still_rejected(self) -> None:
        tiny = _search()[1]
        self.assertEqual(calculate_image_quality_score(tiny, "Emmy Noether"), -1.0)


if __name__ == "__main__":
    unittest.main()

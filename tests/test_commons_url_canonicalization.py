"""Commons file addresses are stored under one host, without the analytics.

Commons serves the same bytes from more than one name: the API that renders a
thumbnail began answering with `thumb.wikimedia.org` where it had always
answered with `upload.wikimedia.org`. Nothing downstream is written for the
alias. `getThumbnailUrl` in `src/utils/story/images.js` rewrites a width only
for the canonical host, so an aliased address reaches the reader at whatever
width the generator happened to store and at a size the slide never asked for;
the portrait generator's lookup returns early on it; and the privacy notice
names the canonical host as one of three, so an alias in the data makes the
notice untrue about where a visit sends the reader's IP address.

The tracking query is the same kind of defect one layer down: appended to
every URL the API returns, it makes one photograph look like two when a stored
address is compared with a fresh one, and the interface's rewriter—which
appends a size to the path—builds a broken address around it.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from utils.http import COMMONS_FILE_HOST, canonical_commons_url  # noqa: E402

THUMB = (
    "https://thumb.wikimedia.org/wikipedia/commons/thumb/7/7d/"
    "Grace_Hopper_being_promoted_to_Commodore.jpg/"
    "960px-Grace_Hopper_being_promoted_to_Commodore.jpg"
)
TRACKING = "?utm_source=commons.wikimedia.org&utm_campaign=imageinfo"


class CanonicalCommonsUrlTests(unittest.TestCase):
    def test_the_thumbnail_host_becomes_the_canonical_one(self):
        self.assertEqual(
            canonical_commons_url(THUMB),
            THUMB.replace("thumb.wikimedia.org", COMMONS_FILE_HOST, 1),
        )

    def test_the_tracking_query_is_dropped_from_either_host(self):
        for host in (COMMONS_FILE_HOST, "thumb.wikimedia.org"):
            url = THUMB.replace("thumb.wikimedia.org", host, 1)
            with self.subTest(host=host):
                self.assertEqual(
                    canonical_commons_url(url + TRACKING),
                    url.replace("thumb.wikimedia.org", COMMONS_FILE_HOST, 1),
                )

    def test_the_path_survives_untouched(self):
        """The width and the percent-encoding are identity, not decoration."""
        encoded = (
            "https://thumb.wikimedia.org/wikipedia/commons/thumb/6/64/"
            "Sylvania_MOBIDIC_model_%282585216399%29.jpg/"
            "960px-Sylvania_MOBIDIC_model_%282585216399%29.jpg"
        )
        canonical = canonical_commons_url(encoded + TRACKING)
        self.assertIn("%282585216399%29", canonical)
        self.assertIn("960px-", canonical)

    def test_another_archive_is_left_alone(self):
        """Flickr carries no such alias, and its query string is its address."""
        flickr = "https://live.staticflickr.com/65535/49561234567_abc_b.jpg"
        self.assertEqual(canonical_commons_url(flickr), flickr)

    def test_the_commons_page_link_is_not_a_file_address(self):
        """A `source` is a link the reader follows, not an image request."""
        page = "https://commons.wikimedia.org/wiki/File:Grace_Hopper.jpg"
        self.assertEqual(canonical_commons_url(page), page)

    def test_nothing_is_invented_for_a_missing_url(self):
        self.assertIsNone(canonical_commons_url(None))
        self.assertEqual(canonical_commons_url(""), "")


if __name__ == "__main__":
    unittest.main()

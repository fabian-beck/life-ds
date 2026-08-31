"""The privacy notice names the hosts a visitor's browser actually contacts.

`landing.privacy_third_party_text` in both locales lists the image hosts by
name, which is only honest while the list matches the data. Stories are added
and regenerated continually, and an image picked from an archive nobody has
used before adds a host silently: nothing fails, the picture simply loads, and
the notice goes on naming three hosts while the browser contacts four.

The set is derived here from the fields the application turns into an
`<img src>` — event images, depth-layer background images, and meta story
figures. A `source` or `licenseUrl` beside them is a link a reader may follow,
not a request the page makes, so it is deliberately not counted.
"""

import json
import re
import unittest
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
LOCALES = (
    ROOT / "src" / "locales" / "en.json",
    ROOT / "src" / "locales" / "de.json",
)
NOTICE_KEY = "landing.privacy_third_party_text"

# The containers whose "url" is fetched: `images[]`, `background_images[]`, and
# the single `image` of a meta story figure.
IMAGE_CONTAINERS = {"images", "background_images", "image"}

# A bare hostname as the notice spells one: labels joined by dots, ending in a
# letters-only suffix. The surrounding prose carries no other dotted token.
HOST_RE = re.compile(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b")


def fetched_image_hosts():
    """Every host the data makes the application request an image from."""
    hosts = set()

    def walk(node, container):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "url" and container in IMAGE_CONTAINERS:
                    if isinstance(value, str) and value.startswith("http"):
                        hosts.add(urlparse(value).netloc)
                else:
                    walk(value, key)
        elif isinstance(node, list):
            for value in node:
                walk(value, container)

    for path in DATA_DIR.rglob("*.json"):
        # Wikipedia materials are inputs to the generators, never rendered.
        if "_cache" in path.parts:
            continue
        walk(json.loads(path.read_text(encoding="utf-8")), None)
    return hosts


def hosts_named_in(locale_path):
    """The hostnames the locale's third-party paragraph spells out."""
    locale = json.loads(locale_path.read_text(encoding="utf-8"))
    return set(HOST_RE.findall(locale[NOTICE_KEY]))


class PrivacyNoticeHostTests(unittest.TestCase):
    def test_every_host_the_browser_contacts_is_named(self):
        contacted = fetched_image_hosts()
        for locale_path in LOCALES:
            with self.subTest(locale=locale_path.name):
                missing = contacted - hosts_named_in(locale_path)
                self.assertEqual(
                    missing,
                    set(),
                    f"{locale_path.name} does not name these image hosts, so the "
                    "privacy notice understates where a visit sends the reader's "
                    "IP address",
                )

    def test_no_host_is_named_that_the_data_no_longer_uses(self):
        contacted = fetched_image_hosts()
        for locale_path in LOCALES:
            with self.subTest(locale=locale_path.name):
                stale = hosts_named_in(locale_path) - contacted
                self.assertEqual(
                    stale,
                    set(),
                    f"{locale_path.name} names image hosts no dataset references "
                    "any more",
                )

    def test_both_locales_name_the_same_hosts(self):
        english, german = (hosts_named_in(path) for path in LOCALES)
        self.assertEqual(
            english,
            german,
            "the two notices disagree about which hosts a visit contacts",
        )


if __name__ == "__main__":
    unittest.main()

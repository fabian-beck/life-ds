"""The privacy notice names the same image hosts in both languages.

``landing.privacy_third_party_text`` lists the archives a visitor's browser
contacts by name. The German paragraph is translated by hand alongside the
English one, and a host added to one and forgotten in the other is a notice
that is honest in one language only.

Whether the list matches the archives the pictures actually come from is not
checked here: it is a property of the images the generation steps choose, and
a rule about generated data is enforced in the step that writes it.
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALES = (
    ROOT / "src" / "locales" / "en.json",
    ROOT / "src" / "locales" / "de.json",
)
NOTICE_KEY = "landing.privacy_third_party_text"

# A bare hostname as the notice spells one: labels joined by dots, ending in a
# letters-only suffix. The surrounding prose carries no other dotted token.
HOST_RE = re.compile(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b")


def hosts_named_in(locale_path):
    """The hostnames the locale's third-party paragraph spells out."""
    locale = json.loads(locale_path.read_text(encoding="utf-8"))
    return set(HOST_RE.findall(locale[NOTICE_KEY]))


class PrivacyNoticeHostTests(unittest.TestCase):
    def test_both_locales_name_the_same_hosts(self):
        english, german = (hosts_named_in(path) for path in LOCALES)
        self.assertEqual(
            english,
            german,
            "the two notices disagree about which hosts a visit contacts",
        )

    def test_the_notice_names_at_least_one_host(self):
        """A regex that matched nothing would make the parity check vacuous."""
        for path in LOCALES:
            with self.subTest(locale=path.name):
                self.assertTrue(hosts_named_in(path))


if __name__ == "__main__":
    unittest.main()

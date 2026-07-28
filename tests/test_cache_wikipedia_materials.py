import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import cache_wikipedia_materials as cache_script  # noqa: E402
from utils.wikipedia_cache import extract_wikipedia_title  # noqa: E402


class ExtractWikipediaTitleTests(unittest.TestCase):
    def test_extracts_title_and_language(self):
        self.assertEqual(
            extract_wikipedia_title("https://en.wikipedia.org/wiki/Zaha_Hadid"),
            ("Zaha Hadid", "en"),
        )
        self.assertEqual(
            extract_wikipedia_title("https://de.wikipedia.org/wiki/Frei_Otto"),
            ("Frei Otto", "de"),
        )

    def test_decodes_percent_escapes_and_keeps_commas(self):
        self.assertEqual(
            extract_wikipedia_title("https://en.wikipedia.org/wiki/Antoni_Gaud%C3%AD"),
            ("Antoni Gaudí", "en"),
        )
        self.assertEqual(
            extract_wikipedia_title(
                "https://en.wikipedia.org/wiki/Henry_II,_Holy_Roman_Emperor"
            ),
            ("Henry II, Holy Roman Emperor", "en"),
        )

    def test_returns_none_for_non_article_input(self):
        self.assertIsNone(extract_wikipedia_title("Zaha Hadid"))
        self.assertIsNone(extract_wikipedia_title("https://example.com/Zaha_Hadid"))
        self.assertIsNone(extract_wikipedia_title("https://en.wikipedia.org/"))
        self.assertIsNone(extract_wikipedia_title(""))


class FindWikipediaPageTests(unittest.TestCase):
    """A URL must resolve to its own article, never to a search hit."""

    def setUp(self):
        self.fetched = []
        self.searched = []

        def fake_fetch(title):
            self.fetched.append(title)
            if title == "Zaha Hadid":
                return {"title": "Zaha Hadid"}
            raise ValueError(f"No Wikipedia page found for '{title}'.")

        def fake_search(query, limit=5):
            self.searched.append(query)
            return ["Neom"]

        self._fetch = cache_script._fetch_wikipedia_page_direct
        self._search = cache_script.wikipedia_search_titles
        cache_script._fetch_wikipedia_page_direct = fake_fetch
        cache_script.wikipedia_search_titles = fake_search

    def tearDown(self):
        cache_script._fetch_wikipedia_page_direct = self._fetch
        cache_script.wikipedia_search_titles = self._search

    def test_wikipedia_url_resolves_to_its_own_article(self):
        title = cache_script.find_wikipedia_page(
            "https://en.wikipedia.org/wiki/Zaha_Hadid"
        )
        self.assertEqual(title, "Zaha Hadid")
        self.assertEqual(self.fetched, ["Zaha Hadid"])
        self.assertEqual(self.searched, [])

    def test_plain_subject_still_falls_back_to_search(self):
        cache_script.find_wikipedia_page("Zaha Hadid")
        self.assertEqual(self.searched, [])
        self.fetched.clear()
        with self.assertRaises(ValueError):
            cache_script.find_wikipedia_page("Nobody At All")
        self.assertEqual(self.searched, ["Nobody At All"])

    def test_non_wikipedia_url_is_rejected_instead_of_searched(self):
        with self.assertRaises(ValueError) as context:
            cache_script.find_wikipedia_page("https://example.com/Zaha_Hadid")
        self.assertIn("not a Wikipedia article URL", str(context.exception))
        self.assertEqual(self.searched, [])


if __name__ == "__main__":
    unittest.main()

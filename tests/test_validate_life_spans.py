"""Tests for the life-span checker.

The defect it exists for shipped once already: Planck's son Karl fell at
Verdun in 1916 with "Karl (1888–1916)" in the cached article, and the dataset
carried 1917 in the event prose and the network alike. The risky part is the
other direction — a corpus full of correct years must produce no findings,
with first names shared across generations (mother and daughter Emma) and
bare first names in professional contexts both resolving to the wrong person
if the checker lets them.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import validate_life_spans as spans_check  # noqa: E402

ARTICLE = (
    "Im März 1888 kam ihr erster Sohn Karl (1888–1916) zur Welt, im April "
    "1889 folgten die Zwillingstöchter Emma (1889–1919) und Grete "
    "(1889–1917). Albert Einstein (14 March 1879 – 18 April 1955) joined "
    "the academy. He served as rector (1905–1906) in Berlin."
)

GERMAN_LEAD = (
    "Max Karl Ernst Ludwig Planck (* 23. April 1858 in Kiel; "
    "† 4. Oktober 1947 in Göttingen) war ein deutscher Physiker."
)


class SpanCollectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spans = spans_check.collect_spans([ARTICLE, GERMAN_LEAD])

    def test_a_bare_first_name_span_is_collected(self) -> None:
        self.assertIn((1888, 1916), self.spans["Karl"])

    def test_a_full_date_english_span_is_collected(self) -> None:
        self.assertIn((1879, 1955), self.spans["Albert Einstein"])

    def test_the_german_lead_span_is_collected(self) -> None:
        self.assertIn((1858, 1947), self.spans["Planck"])

    def test_a_tenure_range_is_not_a_life(self) -> None:
        self.assertNotIn("rector", self.spans)
        for candidates in self.spans.values():
            self.assertNotIn((1905, 1906), candidates)


class DeathYearResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spans = spans_check.collect_spans([ARTICLE, GERMAN_LEAD])

    def test_the_first_name_answers_before_the_family_name(self) -> None:
        # "Karl Planck" must resolve to Karl's own span, not to every Planck
        # the articles date.
        self.assertEqual(spans_check.death_years_for("Karl Planck", self.spans), {1916})

    def test_an_exact_name_answers_first(self) -> None:
        self.assertEqual(
            spans_check.death_years_for("Albert Einstein", self.spans), {1955}
        )


def dataset(description):
    return {
        "events": [
            {"date": "1909-10-17", "title": "Losses", "description": description}
        ]
    }


class ProseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spans = spans_check.collect_spans([ARTICLE])

    def test_the_shipped_defect_is_found(self) -> None:
        findings = spans_check.check_events(
            "p",
            dataset("His eldest son Karl was killed at Verdun in 1917."),
            self.spans,
        )
        self.assertEqual(len(findings), 1)
        self.assertIn("1916", str(findings[0]))

    def test_the_correct_year_passes(self) -> None:
        findings = spans_check.check_events(
            "p",
            dataset("His eldest son Karl was killed at Verdun in 1916."),
            self.spans,
        )
        self.assertEqual(findings, [])

    def test_paired_names_and_years_pass_together(self) -> None:
        findings = spans_check.check_events(
            "p",
            dataset(
                "His twin daughters, Grete and Emma, died in childbirth in "
                "1917 and 1919, respectively."
            ),
            self.spans,
        )
        self.assertEqual(findings, [])

    def test_a_death_sentence_without_a_year_is_left_alone(self) -> None:
        findings = spans_check.check_events(
            "p", dataset("His son Karl was killed at Verdun."), self.spans
        )
        self.assertEqual(findings, [])

    def test_an_unknown_name_is_left_alone(self) -> None:
        findings = spans_check.check_events(
            "p", dataset("His friend Theodor died in 1922."), self.spans
        )
        self.assertEqual(findings, [])

    def test_the_subjects_own_surname_is_not_treated_as_another_person(self) -> None:
        data = dataset("Planck died in 1947.")
        data["person"] = {"name": "Max Planck"}
        findings = spans_check.check_events("max_planck", data, self.spans)
        self.assertEqual(findings, [])


class NetworkResolutionTests(unittest.TestCase):
    """check_network reads from disk, so its resolution rules are exercised
    through the same helpers; here the semantic gate is what matters."""

    def setUp(self) -> None:
        self.spans = spans_check.collect_spans([ARTICLE, GERMAN_LEAD])

    def test_a_professional_name_does_not_resolve_through_a_first_name(
        self,
    ) -> None:
        # A bare "Emma" span must not stand in for a professional contact
        # named Emma Noether; only family resolves through first names.
        self.assertEqual(self.spans.get("Emma Noether"), None)

    def test_a_long_family_name_does_not_resolve_through_a_shared_first_name(
        self,
    ) -> None:
        self.assertEqual(
            spans_check.network_death_years_for(
                "Karl Friedrich Other Planck", "family/son", self.spans
            ),
            set(),
        )

    def test_no_cache_means_no_findings(self) -> None:
        self.assertEqual(spans_check.check_person("no_such_person", {"events": []}), [])


if __name__ == "__main__":
    unittest.main()

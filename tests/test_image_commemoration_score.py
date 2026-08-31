"""Tests for the penalty that keeps commemorations out of the top of the pool.

A photograph of a plaque, a grave or a statue is the best-lit, highest-
resolution candidate a search returns, and it shows how a subject is
remembered rather than the life the story tells. The pipeline had a penalty for
exactly that, but it sat behind event data no caller passes, inside a score
clamped at zero, reading a Commons field Openverse never fills — so it never
subtracted anything from anything.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from events.images.scoring import (  # noqa: E402
    COMMEMORATION_PENALTY,
    calculate_image_quality_score,
    filter_images_by_quality,
    score_commemoration,
    score_temporal_relevance,
)

# The two candidates from the issue: a modern photograph of Hilbert's memorial
# plaque, and a scanned photograph taken while he was lecturing.
PLAQUE = dict(
    width=4000,
    height=3000,
    size=6_000_000,
    mime="image/jpeg",
    filename="Memorial_plaque_for_David_Hilbert_Wilhelm-Weber-Strasse_29_Goettingen.jpg",
    categories=["Category:Memorial plaques in Göttingen", "Category:David Hilbert"],
    dateTimeOriginal="2021",
    dateTimeUpload="2021",
)
PERIOD_PHOTOGRAPH = dict(
    width=900,
    height=700,
    size=180_000,
    mime="image/jpeg",
    filename="Hilbert_lecture_Goettingen_1932.jpg",
    categories=["Category:David Hilbert", "Category:University of Göttingen"],
    dateTimeOriginal="1932",
    dateTimeUpload="2009",
)


class CommemorationOutranksNothingTest(unittest.TestCase):
    def test_a_plaque_scores_below_a_period_photograph(self):
        """The ranking the whole issue is about, on the call production makes.

        Neither production caller passes event data, so this has to hold with
        the candidate alone — which is why the penalty cannot live behind the
        event-specific half of the score.
        """
        plaque = calculate_image_quality_score(PLAQUE, "David Hilbert")
        period = calculate_image_quality_score(PERIOD_PHOTOGRAPH, "David Hilbert")

        self.assertLess(plaque, period)

    def test_it_still_holds_when_the_caller_has_an_event(self):
        plaque = calculate_image_quality_score(
            PLAQUE, "David Hilbert", event_date="1930", event_text="Retired from teaching"
        )
        period = calculate_image_quality_score(
            PERIOD_PHOTOGRAPH,
            "David Hilbert",
            event_date="1930",
            event_text="Retired from teaching",
        )

        self.assertLess(plaque, period)

    def test_the_penalty_outweighs_what_a_modern_photograph_wins_on(self):
        """Resolution and file efficiency are worth 15 points between them, and
        a modern digital photograph takes most of that margin off a scan."""
        self.assertGreater(
            COMMEMORATION_PENALTY,
            calculate_image_quality_score(PLAQUE)
            - calculate_image_quality_score(PERIOD_PHOTOGRAPH)
            + COMMEMORATION_PENALTY,
        )


class WhatCountsAsACommemorationTest(unittest.TestCase):
    def test_reads_the_filename_when_there_are_no_categories(self):
        """Openverse reports no categories; the old penalty read only those."""
        openverse = {
            "filename": "Grave of Grace Murray Hopper at Arlington National Cemetery",
            "caption": "Grave of Grace Murray Hopper",
        }

        self.assertEqual(score_commemoration(openverse), -COMMEMORATION_PENALTY)

    def test_reads_the_categories_when_the_filename_says_nothing(self):
        commons = {
            "filename": "Hilbert_Wilhelm-Weber-Strasse.jpg",
            "categories": ["Category:Memorial plaques in Göttingen"],
        }

        self.assertEqual(score_commemoration(commons), -COMMEMORATION_PENALTY)

    def test_reads_german_commemorations(self):
        """Commons names a German subject's commemorations in German."""
        for filename in (
            "Gedenktafel_Max_Planck_Goettingen.jpg",
            "Denkmal_fuer_Johann_Lukas_von_Schoenlein_Bamberg.jpg",
            "Grabstein_Konrad_Zuse_Huenfeld.jpg",
        ):
            with self.subTest(filename=filename):
                self.assertEqual(
                    score_commemoration({"filename": filename}), -COMMEMORATION_PENALTY
                )

    def test_an_engraving_is_not_a_grave(self):
        """"grave" sits inside "engraved", and an engraved portrait is exactly
        the period picture the penalty exists to protect."""
        for filename in (
            "Engraved_portrait_of_David_Hilbert_1900.jpg",
            "Engraving_of_the_Analytical_Engine_1840.jpg",
        ):
            with self.subTest(filename=filename):
                self.assertEqual(score_commemoration({"filename": filename}), 0.0)

    def test_an_ordinary_photograph_costs_nothing(self):
        self.assertEqual(score_commemoration(PERIOD_PHOTOGRAPH), 0.0)

    def test_a_candidate_with_no_text_at_all_costs_nothing(self):
        self.assertEqual(score_commemoration({}), 0.0)


class RankingTest(unittest.TestCase):
    def test_the_filter_ranks_the_period_photograph_first(self):
        ranked = filter_images_by_quality(
            [dict(PLAQUE), dict(PERIOD_PHOTOGRAPH)], person_name="David Hilbert"
        )

        self.assertEqual(
            [image["filename"] for image in ranked],
            [PERIOD_PHOTOGRAPH["filename"], PLAQUE["filename"]],
        )


class TemporalRelevanceTest(unittest.TestCase):
    """The upload date is gone: a recent upload means a recent photograph as
    often as it means a fresh scan, and a plaque is the recent photograph."""

    def test_a_contemporary_picture_scores_highest(self):
        self.assertEqual(score_temporal_relevance("1932", "1932"), 10.0)

    def test_the_score_is_only_about_the_pictures_own_date(self):
        self.assertEqual(score_temporal_relevance("1932", ""), 0.0)


if __name__ == "__main__":
    unittest.main()

"""Chapters are a partition the proposal draws and the pipeline dates.

The proposal names a chapter on every event skeleton instead of dating the chapters,
so the pipeline has two deterministic jobs the model used to be asked for:
refuse a plan whose chapters are not contiguous runs of the timeline, and read
each chapter's dates, ages, and people off its own events. The Planck case is
what the dating has to get right: a chapter that once opened on the day his
son was executed held a move dated only to the year, so the chapter began after
one of its events.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from events.pipeline import (  # noqa: E402
    MIN_CHAPTER_EVENTS,
    PROPOSAL_ATTEMPTS,
    build_chapters,
    propose_events,
    validate_chapter_partition,
)
from events.schemas import (  # noqa: E402
    ChapterPlan,
    EventSkeleton,
    LifeEvent,
    LifePlan,
    Person,
)


def skeleton(title: str, date: str, chapter: str | None) -> EventSkeleton:
    return EventSkeleton(
        date=date,
        date_precision="day" if len(date) == 10 else "year",
        title=title,
        description="",
        chapter=chapter,
    )


def plan(*ids: str) -> list[ChapterPlan]:
    return [ChapterPlan(id=cid, headline=cid.replace("_", " ").title()) for cid in ids]


def event(date: str, precision: str, chapter: str, **overrides) -> LifeEvent:
    fields = {
        "date": date,
        "date_precision": precision,
        "title": "An event",
        "description": "",
        "locations": [],
        "sources": [],
        "chapter": chapter,
    }
    fields.update(overrides)
    return LifeEvent(**fields)


class PartitionTests(unittest.TestCase):
    def test_contiguous_runs_in_plan_order_pass(self) -> None:
        skeletons = [
            skeleton("Birth", "1858-04-23", "beginnings"),
            skeleton("Doctorate", "1879", "beginnings"),
            skeleton("Berlin chair", "1889", "berlin"),
            skeleton("Quantum", "1900-12-14", "berlin"),
        ]
        validate_chapter_partition(plan("beginnings", "berlin"), skeletons)

    def test_a_chapter_that_resumes_is_refused(self) -> None:
        skeletons = [
            skeleton("Birth", "1858", "beginnings"),
            skeleton("Berlin chair", "1889", "berlin"),
            skeleton("Late doctorate", "1890", "beginnings"),
        ]
        with self.assertRaisesRegex(RuntimeError, "resumes"):
            validate_chapter_partition(plan("beginnings", "berlin"), skeletons)

    def test_an_unknown_chapter_is_refused(self) -> None:
        skeletons = [skeleton("Birth", "1858", "youth")]
        with self.assertRaisesRegex(RuntimeError, "unknown chapter 'youth'"):
            validate_chapter_partition(plan("beginnings"), skeletons)

    def test_an_event_without_a_chapter_is_refused(self) -> None:
        skeletons = [skeleton("Birth", "1858", None)]
        with self.assertRaisesRegex(RuntimeError, "names no chapter"):
            validate_chapter_partition(plan("beginnings"), skeletons)

    def test_an_empty_chapter_is_refused(self) -> None:
        skeletons = [skeleton("Birth", "1858", "beginnings")]
        with self.assertRaisesRegex(RuntimeError, "hold no event: berlin"):
            validate_chapter_partition(plan("beginnings", "berlin"), skeletons)

    def test_a_single_event_chapter_is_refused(self) -> None:
        # Turing's plan: a Princeton chapter holding the doctorate alone.
        skeletons = [
            skeleton("Birth", "1912-06-23", "southern_england"),
            skeleton("Sherborne", "1926", "southern_england"),
            skeleton("Doctorate", "1938", "princeton_years"),
            skeleton("Bletchley", "1939-09", "wartime"),
            skeleton("Bombe", "1939-11", "wartime"),
        ]
        self.assertEqual(MIN_CHAPTER_EVENTS, 2)
        with self.assertRaisesRegex(
            RuntimeError, "fewer than 2 events: princeton_years \\(1\\)"
        ):
            validate_chapter_partition(
                plan("southern_england", "princeton_years", "wartime"), skeletons
            )

    def test_chapters_listed_out_of_timeline_order_are_refused(self) -> None:
        skeletons = [
            skeleton("Birth", "1858", "beginnings"),
            skeleton("Berlin chair", "1889", "berlin"),
        ]
        with self.assertRaisesRegex(RuntimeError, "out of order"):
            validate_chapter_partition(plan("berlin", "beginnings"), skeletons)

    def test_duplicate_chapter_ids_are_refused(self) -> None:
        skeletons = [skeleton("Birth", "1858", "beginnings")]
        with self.assertRaisesRegex(RuntimeError, "not unique"):
            validate_chapter_partition(plan("beginnings", "beginnings"), skeletons)


class BuildChaptersTests(unittest.TestCase):
    def test_a_chapter_is_dated_from_its_first_and_last_event(self) -> None:
        events = [
            event("1945-01-23", "day", "after_the_ruins", age=86),
            event("1945", "year", "after_the_ruins", age=87),
            event("1947-10-04", "day", "after_the_ruins", age=89),
        ]
        (chapter,) = build_chapters(
            [ChapterPlan(id="after_the_ruins", headline="After the Ruins")], events
        )
        # The year-dated move begins before the day-dated execution, so the
        # chapter opens on the year, at the year's precision.
        self.assertEqual(chapter.date_start, "1945")
        self.assertEqual(chapter.date_start_precision, "year")
        self.assertEqual(chapter.date_end, "1947-10-04")
        self.assertEqual(chapter.date_end_precision, "day")
        self.assertEqual(chapter.age_start, 87)
        self.assertEqual(chapter.age_end, 89)

    def test_a_spanning_event_closes_the_chapter_at_its_end(self) -> None:
        events = [
            event("1945-01-23", "day", "c", date_end="1948", date_end_precision="year"),
            event("1946-05", "month", "c"),
        ]
        (chapter,) = build_chapters([ChapterPlan(id="c", headline="C")], events)
        self.assertEqual(chapter.date_end, "1948")
        self.assertEqual(chapter.date_end_precision, "year")

    def test_people_are_gathered_from_the_members_and_folded(self) -> None:
        events = [
            event("1900", "year", "c", involved_people=["Anna Lloyd Jones"]),
            event(
                "1901",
                "year",
                "c",
                involved_people=["Anna Lloyd Jones Wright", "Louis Sullivan"],
            ),
            event("1902", "year", "d", involved_people=["Edwin Cheney"]),
        ]
        chapters = build_chapters(
            [
                ChapterPlan(id="c", headline="C", location="Illinois"),
                ChapterPlan(id="d", headline="D"),
            ],
            events,
        )
        self.assertEqual(
            chapters[0].involved_people, ["Anna Lloyd Jones", "Louis Sullivan"]
        )
        self.assertEqual(chapters[0].location, "Illinois")
        self.assertEqual(chapters[1].involved_people, ["Edwin Cheney"])

    def test_a_chapter_without_people_carries_none(self) -> None:
        (chapter,) = build_chapters(
            [ChapterPlan(id="c", headline="C")], [event("1900", "year", "c")]
        )
        self.assertIsNone(chapter.involved_people)

    def test_the_plan_order_is_kept(self) -> None:
        events = [event("1900", "year", "a"), event("1910", "year", "b")]
        chapters = build_chapters(plan("a", "b"), events)
        self.assertEqual([c.id for c in chapters], ["a", "b"])

    def test_an_empty_chapter_fails(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "holds no event"):
            build_chapters(plan("a"), [event("1900", "year", "b")])


def life_plan(*chapter_of_event: str) -> LifePlan:
    """A plan of dated events, each naming its chapter, in the given order."""
    events = [
        skeleton(f"Event {i}", str(1900 + i), chapter)
        for i, chapter in enumerate(chapter_of_event)
    ]
    ids = list(dict.fromkeys(chapter_of_event))
    return LifePlan(
        dataset="Biographical Timeline",
        created_on="2026-09-06",
        person=Person(
            name="Someone", primary_roles=["writer"], tagline="A life", summary=""
        ),
        chapters=plan(*ids),
        event_skeletons=events,
        conclusion="",
    )


class ProposalRetryTests(unittest.TestCase):
    """A refused plan is asked for once more, with the reason; then it fails."""

    def test_a_refused_plan_is_asked_again_with_the_reason(self) -> None:
        thin = life_plan("a", "a", "b")
        sound = life_plan("a", "a", "b", "b")
        with (
            mock.patch(
                "events.pipeline.parse_structured_or_raise", side_effect=[thin, sound]
            ) as call,
            mock.patch("events.pipeline.get_client"),
        ):
            result = propose_events("the article", "a-model")
        self.assertIs(result, sound)
        self.assertEqual(call.call_count, 2)
        first, second = (c.kwargs["input"] for c in call.call_args_list)
        self.assertEqual(len(second), len(first) + 1)
        self.assertIn("fewer than 2 events: b (1)", second[-1]["content"])

    def test_a_plan_refused_twice_fails_the_run(self) -> None:
        self.assertEqual(PROPOSAL_ATTEMPTS, 2)
        with (
            mock.patch(
                "events.pipeline.parse_structured_or_raise",
                side_effect=[life_plan("a", "b", "b"), life_plan("a", "b", "b")],
            ) as call,
            mock.patch("events.pipeline.get_client"),
        ):
            with self.assertRaisesRegex(RuntimeError, "fewer than 2 events: a"):
                propose_events("the article", "a-model")
        self.assertEqual(call.call_count, PROPOSAL_ATTEMPTS)


if __name__ == "__main__":
    unittest.main()

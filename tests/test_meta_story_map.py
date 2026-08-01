"""Chronological order of the events inside a geographic map stop.

A stop card lists its cluster's events in array order and spells out only the
first few, so an unordered cluster both reads backwards and can hide the wrong
events. The order is a property of the stored data, checked here for the
generator and for the meta-story files the app actually reads.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from meta_story_map import (  # noqa: E402
    cluster_located_events,
    event_date_key,
)

META_STORIES_DIR = ROOT / "data" / "meta_stories"


def located(person_id, index, date, coordinates):
    return {
        "id": f"{person_id}:{index}",
        "person_id": person_id,
        "person_name": person_id.replace("_", " ").title(),
        "event_index": index,
        "event_title": f"Event {index}",
        "event_date": date,
        "year": int(str(date)[:4]),
        "place": "Yorktown",
        "coordinates": coordinates,
        "theme_connection": "",
    }


class EventDateKeyTests(unittest.TestCase):
    def test_orders_dates_within_a_year(self):
        dates = ["1787-09-17", "1787", "1787-05-25", "1787-05"]
        self.assertEqual(
            sorted(dates, key=event_date_key),
            ["1787", "1787-05", "1787-05-25", "1787-09-17"],
        )

    def test_undated_events_sort_last(self):
        self.assertEqual(
            sorted(["", "1781-10-14"], key=event_date_key),
            ["1781-10-14", ""],
        )


class ClusterEventOrderTests(unittest.TestCase):
    def test_same_year_events_are_ordered_by_month_and_day(self):
        events = [
            located("alexander_hamilton", 7, "1781-10-14", [-76.5097, 37.2388]),
            located("george_washington", 9, "1781-09-28", [-76.5097, 37.2388]),
        ]
        clusters = cluster_located_events(events)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(
            [e["event_date"] for e in clusters[0]["events"]],
            ["1781-09-28", "1781-10-14"],
        )


class StoredMetaStoryTests(unittest.TestCase):
    def test_stored_clusters_list_events_chronologically(self):
        paths = sorted(META_STORIES_DIR.rglob("*.json"))
        self.assertTrue(paths)
        for path in paths:
            data = json.loads(path.read_text(encoding="utf-8"))
            clusters = (data.get("geo_map") or {}).get("clusters") or []
            for cluster in clusters:
                dates = [e.get("event_date") for e in cluster.get("events") or []]
                with self.subTest(story=path.name, cluster=cluster.get("key")):
                    self.assertEqual(dates, sorted(dates, key=event_date_key))


if __name__ == "__main__":
    unittest.main()

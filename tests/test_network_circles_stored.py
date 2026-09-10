"""The network's circles are stored with the narration, not re-derived.

The client once repeated the greedy-modularity community detection to find
out which people each narration card highlights, mirrored line by line from
``derive_clusters``. Two implementations of one numeric algorithm in two
languages must stay identical or the cards silently lose their members, so
Phase 6 now writes each circle's main members as ``member_ids`` beside the key
and text, the way the composer already did, and the client only reads them.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_meta_story as generator  # noqa: E402
from meta_story_network import derive_clusters  # noqa: E402


def _main(person_id: str, birth_year: int) -> dict:
    return {
        "id": person_id,
        "name": person_id.replace("_", " "),
        "type": "main",
        "birth_year": birth_year,
    }


def _link(source: str, target: str, kind: str, strength: str) -> dict:
    return {"source": source, "target": target, "kind": kind, "strength": strength}


NETWORK = {
    "nodes": [
        _main("ada_lovelace", 1815),
        _main("charles_babbage", 1791),
        _main("alan_turing", 1912),
        _main("john_von_neumann", 1903),
        {"id": "max_newman", "name": "Max Newman", "type": "secondary"},
    ],
    "links": [
        _link("ada_lovelace", "charles_babbage", "main", "strong"),
        _link("alan_turing", "john_von_neumann", "main", "strong"),
        _link("alan_turing", "max_newman", "secondary", "strong"),
        _link("john_von_neumann", "max_newman", "secondary", "weak"),
        _link("charles_babbage", "alan_turing", "main", "weak"),
    ],
}


class StoredCircleTests(unittest.TestCase):
    def test_phase6_stores_the_main_members_of_every_circle(self) -> None:
        dataset = {
            "meta_story": {"title": "Computing", "tagline": "Machines"},
            "social_network": dict(NETWORK),
        }
        clusters = derive_clusters(dataset["social_network"])
        self.assertEqual(len(clusters), 2)
        answer = generator.NetworkNarrationResult(
            circles=[
                generator.NetworkCircleNarration(
                    key=c["key"], title=f"Title {i}", text=f"Text {i}."
                )
                for i, c in enumerate(clusters)
            ]
        )
        with mock.patch.object(generator, "parse_structured", return_value=answer):
            generator.phase6_network_narration(dataset, client=mock.Mock())

        circles = dataset["social_network"]["narration"]["circles"]
        self.assertEqual(
            [c["member_ids"] for c in circles],
            [[n["id"] for n in c["mains"]] for c in clusters],
        )
        for circle in circles:
            # The key encodes the same members in the same order.
            self.assertEqual(circle["key"], "+".join(circle["member_ids"]))
            self.assertNotIn("max_newman", circle["member_ids"])
        self.assertEqual([c["title"] for c in circles], ["Title 0", "Title 1"])


if __name__ == "__main__":
    unittest.main()

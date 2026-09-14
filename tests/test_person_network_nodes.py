"""Tests that the ego network generator admits only individuals as nodes.

A network once carried "Nazi regime" as Albert Einstein's persecutor and
"IBM" as Frances Allen's employer: the schema offered an `entity_kind` of
`organization` or `group`, and the prompt invited both. Every node is now one
named human being — the schema has no field for anything else, the prompt
says so, and a name that still reads as a collective is reported.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_person_network as generator  # noqa: E402


class ConnectionSchemaTests(unittest.TestCase):
    def test_a_connection_has_no_field_for_a_collective(self) -> None:
        fields = generator.Connection.model_fields
        self.assertNotIn("entity_kind", fields)
        self.assertNotIn("qualifier", fields)

    def test_the_name_field_asks_for_an_individual(self) -> None:
        description = generator.Connection.model_fields["person_name"].description
        self.assertIn("individual", description)
        self.assertIn("never an organization", description)


class PromptTests(unittest.TestCase):
    def test_the_instructions_forbid_collectives_and_name_the_way_out(self) -> None:
        source = Path(generator.__file__).read_text(encoding="utf-8")
        self.assertIn("INDIVIDUALS ONLY", source)
        self.assertIn("a regime that persecuted them", source)
        self.assertIn("name the individual through whom the tie ran", source)
        self.assertIn("never the regime, the state, or the police force as such", source)
        self.assertNotIn("entity_kind", source)


class CollectiveNameTests(unittest.TestCase):
    COLLECTIVES = [
        "Nazi regime",
        "IBM",
        "National Security Agency",
        "Neue Leipziger Zeitung editorial staff",
        "Students at the University of Texas at Austin",
        "Editors of Berliner Tageblatt, Vossische Zeitung, and Die Weltbühne",
        "University of California, Berkeley",
        "St Anne\u2019s College, Oxford",
        "Kaufungen Abbey community",
        "Philip Johnson and Mark Wigley",
        "General Electric Computer Development Laboratory colleagues (collective)",
    ]
    PERSONS = [
        "Albert Einstein",
        "Mileva Mari\u0107",
        "Max Planck",
        "Cunigunde of Luxembourg",
        "Henry II, Holy Roman Emperor",
        "Edsger W. Dijkstra",
        "J. Robert Oppenheimer",
        "Ada Lovelace",
        "Grace Hopper",
        "Elisabeth of Bavaria",
    ]

    def test_collective_names_are_reported(self) -> None:
        for name in self.COLLECTIVES:
            with self.subTest(name=name):
                self.assertTrue(generator.looks_collective(name))

    def test_person_names_are_not(self) -> None:
        for name in self.PERSONS:
            with self.subTest(name=name):
                self.assertFalse(generator.looks_collective(name))


if __name__ == "__main__":
    unittest.main()

"""Tests for the involved-name spelling checker.

Its finding is defined by two judgments agreeing: the folding side must call
two names the same person, and the ported interface scoring must nonetheless
reject the pair. The port matters most — a checker that thinks the interface
is stricter than it is would flag pairs whose chips work fine, which is what
the first corpus run showed for maiden names and containment matches.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import validate_involved_names as names  # noqa: E402


def would_match(a: str, b: str) -> bool:
    return names.interface_would_match(a, b)


class InterfacePortTests(unittest.TestCase):
    def test_a_maiden_name_parenthetical_still_matches(self) -> None:
        self.assertTrue(
            would_match("Ethel Sara Turing", "Ethel Sara Turing (née Stoney)")
        )

    def test_containment_carries_a_short_name(self) -> None:
        self.assertTrue(would_match("John Quincy", "John Quincy Adams"))

    def test_diacritics_defeat_the_matcher(self) -> None:
        self.assertFalse(would_match("Leó Szilárd", "Leo Szilard"))

    def test_eszett_defeats_the_matcher(self) -> None:
        self.assertFalse(would_match("Marga von Hößlin Planck", "Marga von Hösslin"))

    def test_different_regnal_numbers_never_match(self) -> None:
        self.assertFalse(would_match("Henry II", "Henry V"))


class FoldingTests(unittest.TestCase):
    def test_the_shipped_pair_folds_to_one_person(self) -> None:
        self.assertTrue(
            names.same_person_folded("Marga von Hößlin Planck", "Marga von Hösslin")
        )

    def test_a_family_is_not_a_spelling(self) -> None:
        self.assertFalse(names.same_person_folded("Karl Planck", "Grete Planck"))

    def test_a_slavic_l_is_one_edit(self) -> None:
        self.assertTrue(names.same_person_folded("Stanisław Ulam", "Stanislaw Ulam"))


class FindingTests(unittest.TestCase):
    def test_the_shipped_defect_is_the_finding(self) -> None:
        # The ß pair folds together and the interface rejects it: exactly one
        # person, two spellings.
        self.assertTrue(
            names.same_person_folded("Marga von Hößlin Planck", "Marga von Hösslin")
            and not would_match("Marga von Hößlin Planck", "Marga von Hösslin")
        )

    def test_a_working_chip_is_not_a_finding(self) -> None:
        # Folds together, but the interface matches it fine — no finding.
        self.assertTrue(
            names.same_person_folded("Margrethe Nørlund", "Margrethe Nørlund Bohr")
            and would_match("Margrethe Nørlund", "Margrethe Nørlund Bohr")
        )


if __name__ == "__main__":
    unittest.main()


class ResolutionTests(unittest.TestCase):
    # The port of the chip resolution itself (issue #140): one name, its best
    # connection, and a suffix that decides between a father and his namesake.
    def test_the_best_match_is_the_exact_one(self) -> None:
        ranked = names.matching_connections(
            "Benjamin Babbage", ["Benjamin Herschel Babbage", "Benjamin Babbage"]
        )
        self.assertEqual([name for _, name in ranked][0], "Benjamin Babbage")
        self.assertLess(ranked[1][0], ranked[0][0])

    def test_a_suffix_breaks_the_tie_without_refusing_the_match(self) -> None:
        ranked = names.matching_connections(
            "Christian Bohr", ["Christian Bohr Jr.", "Christian Bohr"]
        )
        self.assertEqual(ranked[0][1], "Christian Bohr")
        self.assertLess(ranked[1][0], 1.0)
        self.assertTrue(would_match("Christian Bohr", "Christian Bohr Jr."))

    def test_a_tie_at_the_top_is_a_finding(self) -> None:
        self.assertTrue(names.is_ambiguous("Rosa Gaudí", ["Rosa Gaudí", "Rosa Gaudí"]))
        self.assertFalse(
            names.is_ambiguous("Rosa Gaudí", ["Rosa Egea Gaudí", "Rosa Gaudí"])
        )

"""Tests for the mixed-writing-system checker.

Both shapes it exists for shipped once: three Georgian letters spliced into
"Zwillingstöchter" and a Cyrillic opening on "lektionierte". The risky part
is the other direction — physics notation ("hν"), chemistry ("MoS₂"), pure
Cyrillic names in image credits, and ordinary German must all pass.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from validate_scripts import control_characters, mixed_script_words  # noqa: E402


class MixedScriptTests(unittest.TestCase):
    def test_the_georgian_splice_is_found(self) -> None:
        self.assertEqual(
            mixed_script_words("seine Zwillინგstöchter Grete und Emma"),
            ["Zwillინგstöchter"],
        )

    def test_the_cyrillic_opening_is_found(self) -> None:
        self.assertEqual(
            mixed_script_words("der über Gödels Satz лекtionierte"),
            ["лекtionierte"],
        )

    def test_one_cyrillic_homoglyph_is_enough(self) -> None:
        self.assertEqual(mixed_script_words("Mаthematik"), ["Mаthematik"])

    def test_a_single_greek_letter_is_notation(self) -> None:
        self.assertEqual(mixed_script_words("die Energie hν eines Quants"), [])

    def test_two_greek_letters_are_not(self) -> None:
        self.assertEqual(mixed_script_words("hνν"), ["hνν"])

    def test_a_pure_cyrillic_name_is_attribution(self) -> None:
        self.assertEqual(mixed_script_words("Олег Мариненко"), [])

    def test_chemistry_subscripts_are_not_letters(self) -> None:
        self.assertEqual(mixed_script_words("ein Molybdänsulfid (MoS₂)"), [])

    def test_physics_superscripts_are_not_letters(self) -> None:
        self.assertEqual(mixed_script_words("die Formel E = mc²"), [])

    def test_plain_german_passes(self) -> None:
        self.assertEqual(
            mixed_script_words("Die Zwillingstöchter starben im Kindbett."), []
        )


class ControlCharacterTests(unittest.TestCase):
    def test_the_wright_corruption_is_found(self) -> None:
        self.assertEqual(control_characters("Olgivanna Lazovi\x0107"), ["U+0001"])

    def test_structural_whitespace_passes(self) -> None:
        self.assertEqual(control_characters("line one\nline two\ttabbed"), [])


if __name__ == "__main__":
    unittest.main()

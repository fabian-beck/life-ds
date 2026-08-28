"""Tests for the fact-checking evaluation pipeline.

Narrow on purpose. The stages that call a model are not tested — their output
is judged by people, which is the point of the tool. What is tested is the
deterministic machinery a round silently depends on: a fact's identity, whether
a quote is really in the source, whether the sample is reproducible, and whether
the agreement figures mean what the report says they mean. Each of these can be
wrong without anything failing, and each would invalidate a round's results
after the evaluators had already spent their time.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from evaluation.factcheck import agreement, report, text  # noqa: E402
from evaluation.factcheck.evidence import MaterialIndex, is_apparatus  # noqa: E402
from evaluation.factcheck.materials import Material  # noqa: E402
from evaluation.factcheck.merge_results import summarize  # noqa: E402
from evaluation.factcheck.models import EvidenceOutput, VERDICTS  # noqa: E402
from evaluation.factcheck.sampling import allocate, stratified_sample  # noqa: E402
from evaluation.factcheck.units import build_units, load_person_story  # noqa: E402

EVALUATOR_PAGE = REPO_ROOT / "evaluation" / "app" / "index.html"


class QuoteMatchingTests(unittest.TestCase):
    """A quote counts as evidence only if it is really in the source."""

    SOURCE = "Turing was elected a Fellow of King’s College — Cambridge.\n\nHe stayed."

    def test_matches_through_rewritten_punctuation(self) -> None:
        span = text.find_quote("Fellow of King's College - Cambridge", self.SOURCE)
        self.assertIsNotNone(span)
        assert span is not None
        self.assertEqual(
            self.SOURCE[span[0] : span[1]], "Fellow of King’s College — Cambridge"
        )

    def test_matches_across_a_line_break(self) -> None:
        self.assertIsNotNone(text.find_quote("Cambridge. He stayed.", self.SOURCE))

    def test_rejects_a_sentence_the_source_does_not_contain(self) -> None:
        self.assertIsNone(text.find_quote("Turing was elected in 1936", self.SOURCE))


class ProvenanceTests(unittest.TestCase):
    """A claim has to name text the dataset really contains."""

    PAYLOAD = {
        "description": 'He published "On Computable Numbers".',
        "age": 22,
        "locations": [{"centroid": [0.11, 52.2]}],
    }

    def setUp(self) -> None:
        self.haystack = text.provenance_haystack(
            self.PAYLOAD, json.dumps(self.PAYLOAD, indent=2, ensure_ascii=False)
        )

    def test_accepts_prose_containing_a_double_quote(self) -> None:
        self.assertIn(text.fold('He published "On Computable Numbers".'), self.haystack)

    def test_accepts_a_number_and_a_structure(self) -> None:
        self.assertIn(text.fold("22"), self.haystack)
        self.assertIn(text.fold("[\n  0.11,\n  52.2\n]"), self.haystack)

    def test_rejects_invented_text(self) -> None:
        self.assertNotIn(text.fold("He published On Growth and Form."), self.haystack)


class IdentityTests(unittest.TestCase):
    """Fact ids must be reproducible, and must not collide across units."""

    def test_same_inputs_give_the_same_id(self) -> None:
        first = text.fact_id("alan_turing", "event:03", "Turing moved to Cambridge.")
        second = text.fact_id("alan_turing", "event:03", "Turing moved to  Cambridge. ")
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("alan_turing:"))

    def test_different_units_give_different_ids(self) -> None:
        self.assertNotEqual(
            text.fact_id("alan_turing", "event:03", "A claim."),
            text.fact_id("alan_turing", "event:04", "A claim."),
        )


class ChunkingTests(unittest.TestCase):
    """Retrieval offsets have to point at the text they claim to."""

    def test_chunk_offsets_locate_the_chunk_in_the_source(self) -> None:
        source = "\n\n".join(f"Paragraph {index} " + "word " * 60 for index in range(5))
        for chunk in text.chunk_text("m", source):
            self.assertEqual(source[chunk.start : chunk.start + 11], chunk.text[:11])

    def test_reference_sections_are_not_searched(self) -> None:
        self.assertTrue(is_apparatus("== References ==\nSome citation"))
        self.assertTrue(is_apparatus("== Weblinks ==\nEin Link"))
        self.assertFalse(is_apparatus("== Early life ==\nHe was born in 1912."))


class SamplingTests(unittest.TestCase):
    """A round must be reproducible from its seed alone."""

    def population(self) -> dict:
        return {
            "b_person": [{"id": f"b:{index}"} for index in range(40)],
            "a_person": [{"id": f"a:{index}"} for index in range(10)],
        }

    def test_allocation_sums_to_the_requested_size(self) -> None:
        self.assertEqual(sum(allocate({"a": 100, "b": 50, "c": 3}, 20).values()), 20)

    def test_allocation_never_asks_for_more_than_a_person_has(self) -> None:
        allocation = allocate({"a": 2, "b": 50}, 20)
        self.assertLessEqual(allocation["a"], 2)
        self.assertEqual(sum(allocation.values()), 20)

    def test_same_seed_draws_the_same_facts(self) -> None:
        first = stratified_sample(self.population(), 15, 7)
        second = stratified_sample(
            dict(reversed(list(self.population().items()))), 15, 7
        )
        self.assertEqual(
            [fact["id"] for fact in first], [fact["id"] for fact in second]
        )

    def test_a_different_seed_draws_a_different_sample(self) -> None:
        first = [fact["id"] for fact in stratified_sample(self.population(), 15, 7)]
        other = [fact["id"] for fact in stratified_sample(self.population(), 15, 8)]
        self.assertNotEqual(first, other)


class AgreementTests(unittest.TestCase):
    """The agreement figures decide whether a round's numbers can be trusted."""

    def test_perfect_agreement_is_one(self) -> None:
        table = {"u1": {"a": "x", "b": "x"}, "u2": {"a": "y", "b": "y"}}
        self.assertEqual(agreement.krippendorff_alpha(table), 1.0)
        self.assertEqual(agreement.pairwise_agreement(table)[0], 1.0)

    def test_systematic_disagreement_is_negative(self) -> None:
        table = {"u1": {"a": "x", "b": "y"}, "u2": {"a": "y", "b": "x"}}
        alpha = agreement.krippendorff_alpha(table)
        assert alpha is not None
        self.assertLess(alpha, 0)

    def test_alpha_is_undefined_when_nobody_used_a_second_category(self) -> None:
        self.assertIsNone(agreement.krippendorff_alpha({"u": {"a": "x", "b": "x"}}))

    def test_units_one_person_judged_do_not_count_as_agreement(self) -> None:
        table = {"u1": {"a": "x"}, "u2": {"a": "x", "b": "y"}}
        overall, pairs = agreement.pairwise_agreement(table)
        self.assertEqual(overall, 0.0)
        self.assertEqual(pairs[("a", "b")], (0, 1))

    def test_a_tie_has_no_majority(self) -> None:
        self.assertEqual(agreement.majority(["x", "y"]), (None, False))
        self.assertEqual(agreement.majority(["x", "x", "y"]), ("x", False))
        self.assertEqual(agreement.majority(["x", "x"]), ("x", True))


class EvidenceVerificationTests(unittest.TestCase):
    """Quotes are checked against the sources, not taken on trust."""

    def index(self) -> MaterialIndex:
        return MaterialIndex(
            [
                Material(
                    "wp-main",
                    "Alan Turing",
                    "u",
                    "Wikipedia",
                    "en",
                    "He was born in 1912 in London.",
                ),
                Material(
                    "rel-01",
                    "Max Newman",
                    "u",
                    "Wikipedia",
                    "en",
                    "Newman was elected a Fellow in 1923.",
                ),
            ]
        )

    def parsed(self, *quotes) -> EvidenceOutput:
        return EvidenceOutput(
            status="supported",
            notes="",
            quotes=[
                {
                    "material_id": material,
                    "quote": quote,
                    "stance": "supports",
                    "covers": "x",
                }
                for material, quote in quotes
            ],
        )

    def test_a_quote_that_is_not_in_any_source_is_marked(self) -> None:
        from evaluation.factcheck.evidence import verify_quotes

        records = verify_quotes(
            self.index(), self.parsed(("wp-main", "He was born in 1913")), []
        )
        self.assertFalse(records[0]["verified"])

    def test_a_mislabeled_quote_is_credited_to_the_source_it_is_in(self) -> None:
        from evaluation.factcheck.evidence import verify_quotes

        records = verify_quotes(
            self.index(),
            self.parsed(("wp-main", "Newman was elected a Fellow in 1923.")),
            [],
        )
        self.assertTrue(records[0]["verified"])
        self.assertEqual(records[0]["material_id"], "rel-01")
        self.assertIn("Newman", records[0]["context"])


class UnitTests(unittest.TestCase):
    """The decomposition has to cover a real dataset, and only assert its data."""

    def test_a_real_person_decomposes_into_every_part_of_the_story(self) -> None:
        units = build_units(load_person_story("alan_turing"))
        scopes = {unit.scope for unit in units}
        self.assertEqual(
            scopes,
            {"person", "chapters", "conclusion", "event", "background", "network"},
        )

    def test_generated_artwork_prompts_are_not_claims(self) -> None:
        units = build_units(load_person_story("alan_turing"))
        chapters = [unit for unit in units if unit.scope == "chapters"][0]
        self.assertTrue(
            any(chapter.get("headline") for chapter in chapters.payload["chapters"])
        )
        self.assertFalse(
            any("illustration" in chapter for chapter in chapters.payload["chapters"])
        )

    def test_source_lists_are_context_rather_than_claims(self) -> None:
        units = build_units(load_person_story("alan_turing"))
        events = [unit for unit in units if unit.scope == "event"]
        self.assertTrue(any(unit.context.get("sources") for unit in events))
        self.assertFalse(any("sources" in unit.payload for unit in events))


def _bundle(items) -> dict:
    return {
        "schema": "life-ds-factcheck-bundle/1",
        "bundle_id": "bundle1",
        "name": "round",
        "created": "2026-01-01T00:00:00+00:00",
        "seed": 1,
        "model": "test-model",
        "reasoning_effort": "medium",
        "excerpt_budget": 100,
        "max_excerpts": 4,
        "population": {"facts_total": 100, "per_person": {"alan_turing": 100}},
        "persons": {
            "alan_turing": {"id": "alan_turing", "name": "Alan Turing", "materials": []}
        },
        "items": items,
    }


def _item(fact_id: str, claim: str, status: str, verified: bool = True) -> dict:
    return {
        "id": fact_id,
        "person_id": "alan_turing",
        "person_name": "Alan Turing",
        "unit_id": "event:00",
        "unit_label": "1912 — Born",
        "scope": "event",
        "claim": claim,
        "claim_type": "date",
        "checkable": True,
        "source_field": "description",
        "source_text": claim,
        "source_text_found": True,
        "context": {},
        "evidence": {
            "status": status,
            "notes": "",
            "quotes": [
                {
                    "quote": "q",
                    "stance": "supports",
                    "covers": "c",
                    "material_id": "wp-main",
                    "verified": verified,
                }
            ],
        },
    }


def _result(evaluator: str, verdicts: dict) -> dict:
    return {
        "schema": "life-ds-factcheck-results/1",
        "bundle_id": "bundle1",
        "bundle_name": "round",
        "evaluator": evaluator,
        "started": "2026-01-01T00:00:00Z",
        "updated": "2026-01-01T01:00:00Z",
        "judgments": [
            {"fact_id": fact_id, "verdict": verdict, "note": "", "seconds": 30}
            for fact_id, verdict in verdicts.items()
        ],
        "_path": f"{evaluator}.json",
    }


class MergeTests(unittest.TestCase):
    """The merge decides what a round concluded; a wrong join reports fiction."""

    def summary(self) -> dict:
        bundle = _bundle(
            [
                _item("f1", "Turing was born in 1912.", "supported"),
                _item(
                    "f2",
                    "Turing moved to Bletchley in 1938.",
                    "contradicted",
                    verified=False,
                ),
                _item("f3", "Turing's mind bridged two worlds.", "absent"),
            ]
        )
        results = [
            _result(
                "FB", {"f1": "supported", "f2": "contradicted", "f3": "not_a_claim"}
            ),
            _result("AM", {"f1": "supported", "f2": "supported"}),
        ]
        return summarize(bundle, results)

    def test_unanimous_and_contested_facts_are_told_apart(self) -> None:
        summary = self.summary()
        self.assertEqual(summary["verdicts"]["consensus"]["supported"], 1)
        self.assertEqual(summary["verdicts"]["consensus"]["contested"], 1)
        self.assertEqual(len(summary["disagreements"]), 1)

    def test_unverified_quotes_are_counted(self) -> None:
        evidence = self.summary()["evidence"]
        self.assertEqual(evidence["quotes_total"], 3)
        self.assertEqual(evidence["quotes_verified"], 2)

    def test_a_fact_nobody_judged_has_no_verdict(self) -> None:
        summary = self.summary()
        coverage = summary["coverage"]
        self.assertEqual(coverage["facts"], 3)
        self.assertEqual(coverage["judged_by_any"], 3)
        self.assertEqual(coverage["judged_by_all"], 2)

    def test_judgments_from_a_different_bundle_are_refused(self) -> None:
        from evaluation.factcheck.merge_results import check_one_bundle

        other = _result("AM", {"f1": "supported"})
        other["bundle_id"] = "bundle2"
        with self.assertRaises(SystemExit):
            check_one_bundle([_result("FB", {"f1": "supported"}), other], None)

    def test_the_report_renders_the_claims_and_escapes_them(self) -> None:
        bundle = _bundle(
            [_item("f1", "Turing & <script>alert(1)</script>", "supported")]
        )
        html = report.render(summarize(bundle, [_result("FB", {"f1": "supported"})]))
        self.assertIn("Verdicts", html)
        self.assertIn("Agreement between evaluators", html)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)


class PackagingTests(unittest.TestCase):
    """A packaged round is the file an evaluator actually opens."""

    def packaged(self, bundle: dict) -> str:
        from evaluation.factcheck.package_round import package

        return package(bundle)

    def embedded(self, page: str) -> dict:
        from evaluation.factcheck.package_round import (
            PLACEHOLDER_CLOSE,
            PLACEHOLDER_OPEN,
        )

        start = page.index(PLACEHOLDER_OPEN) + len(PLACEHOLDER_OPEN)
        end = page.index(PLACEHOLDER_CLOSE, start)
        return json.loads(page[start:end])

    def test_the_bundle_survives_the_round_trip(self) -> None:
        bundle = _bundle([_item("f1", "Turing was born in 1912.", "supported")])
        self.assertEqual(self.embedded(self.packaged(bundle)), bundle)

    def test_quoted_source_text_cannot_close_the_script_element(self) -> None:
        """A bundle quotes text it did not write, and a source can contain markup."""
        bundle = _bundle(
            [
                _item(
                    "f1",
                    "The page carried </script><script>alert(1)</script>.",
                    "supported",
                )
            ]
        )
        page = self.packaged(bundle)
        embedded_start = page.index('<script id="embedded-bundle"')
        embedded_end = page.index("</script>", embedded_start)
        self.assertNotIn("<", page[embedded_start + 60 : embedded_end])
        self.assertEqual(
            self.embedded(page)["items"][0]["claim"],
            "The page carried </script><script>alert(1)</script>.",
        )

    def test_an_unpackaged_page_still_asks_for_a_bundle(self) -> None:
        source = EVALUATOR_PAGE.read_text(encoding="utf-8")
        self.assertIn(
            '<script id="embedded-bundle" type="application/json">null</script>', source
        )


class VocabularyTests(unittest.TestCase):
    """The page and the merge must name the verdicts identically.

    They are separate artifacts joined only by these strings. A verdict renamed
    on one side would not fail anything: the merge would simply count a category
    nobody chose, and report a round in which half the judgments vanished.
    """

    def test_the_evaluator_page_offers_exactly_the_known_verdicts(self) -> None:
        source = EVALUATOR_PAGE.read_text(encoding="utf-8")
        block = source.split("const VERDICTS = [", 1)[1].split("];", 1)[0]
        keys = re.findall(r"key:\s*\"([a-z_]+)\"", block)
        self.assertEqual(keys, list(VERDICTS))

    def test_the_page_stores_the_schema_the_merge_reads(self) -> None:
        source = EVALUATOR_PAGE.read_text(encoding="utf-8")
        from evaluation.factcheck.merge_results import RESULT_SCHEMA

        self.assertIn(f'RESULT_SCHEMA = "{RESULT_SCHEMA}"', source)


if __name__ == "__main__":
    unittest.main()

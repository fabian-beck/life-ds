"""The closed relationship vocabulary, held against the data and the locales.

A `relationship_type` is reader-facing through two locale lookups, so three
things have to agree: the vocabulary module the generator and the reviews are
constrained by, the tokens the corpus actually carries, and the entries both
locale files provide. Any of them can drift alone without a build failure —
the interface would quietly fall back to its generic label — so these tests
are where the drift becomes visible (issues #117 and #119).
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from utils.relationship_vocabulary import (  # noqa: E402
    CATEGORIES,
    ENTITY_KINDS,
    ROLES,
    TYPE_ALIASES,
    is_canonical,
    normalize_relationship_type,
)

DATA_DIR = ROOT / "data"
LOCALES = {
    lang: json.loads((ROOT / "src" / "locales" / f"{lang}.json").read_text("utf-8"))
    for lang in ("en", "de")
}


def ego_network_files():
    for path in sorted((DATA_DIR / "people").glob("*/ego_network.json")):
        yield path
    for path in sorted((DATA_DIR / "people").glob("*/*/ego_network.json")):
        if "_cache" not in path.parts:
            yield path


def meta_story_files():
    yield from sorted((DATA_DIR / "meta_stories").glob("*.json"))
    yield from sorted((DATA_DIR / "meta_stories").glob("*/*.json"))


class VocabularyLocaleParity(unittest.TestCase):
    def test_every_role_has_both_locale_forms_in_both_languages(self):
        missing = [
            f"network.role.{role}_{suffix} ({lang})"
            for role in sorted(ROLES)
            for suffix in ("one", "other")
            for lang, locale in LOCALES.items()
            if f"network.role.{role}_{suffix}" not in locale
        ]
        self.assertEqual(missing, [])

    def test_every_category_has_a_locale_entry_in_both_languages(self):
        missing = [
            f"network.category.{category} ({lang})"
            for category in sorted(CATEGORIES)
            for lang, locale in LOCALES.items()
            if f"network.category.{category}" not in locale
        ]
        self.assertEqual(missing, [])

    def test_locale_roles_do_not_outgrow_the_vocabulary(self):
        # A role translated but absent from the module would let the
        # generator's constraint and the interface's coverage drift apart.
        prefix, suffix = "network.role.", "_one"
        stems = [
            key[len(prefix) : -len(suffix)]
            for key in LOCALES["en"]
            if key.startswith(prefix) and key.endswith(suffix)
        ]
        # "unknown" is the generic fallback label, not a role of its own.
        stray = [stem for stem in stems if stem not in ROLES and stem != "unknown"]
        self.assertEqual(stray, [])

    def test_entity_kinds_have_labels_for_the_collective_kinds(self):
        for kind in ENTITY_KINDS:
            if kind == "person":
                continue
            for lang, locale in LOCALES.items():
                self.assertIn(f"network.entity.{kind}", locale, f"{kind} ({lang})")

    def test_every_alias_lands_inside_the_vocabulary(self):
        stray = {
            source: target
            for source, target in TYPE_ALIASES.items()
            if not is_canonical(target)
        }
        self.assertEqual(stray, {})


class CorpusStaysCanonical(unittest.TestCase):
    def test_every_ego_network_type_is_in_the_vocabulary(self):
        offenders = []
        for path in ego_network_files():
            data = json.loads(path.read_text("utf-8"))
            for connection in data.get("connections", []):
                token = connection.get("relationship_type", "")
                if not is_canonical(token):
                    offenders.append(
                        f"{path.relative_to(ROOT)}: "
                        f"{connection.get('person_name')} — {token!r}"
                    )
        self.assertEqual(offenders, [])

    def test_every_meta_story_link_type_is_in_the_vocabulary(self):
        offenders = []
        for path in meta_story_files():
            data = json.loads(path.read_text("utf-8"))
            links = (data.get("social_network") or {}).get("links") or []
            for link in links:
                holders = [link, *(link.get("endpoints") or {}).values()]
                for holder in holders:
                    token = holder.get("relationship_type")
                    if token and not is_canonical(token):
                        offenders.append(f"{path.relative_to(ROOT)}: {token!r}")
        self.assertEqual(offenders, [])

    def test_entity_kinds_in_the_corpus_are_the_declared_ones(self):
        offenders = []
        for path in ego_network_files():
            data = json.loads(path.read_text("utf-8"))
            for connection in data.get("connections", []):
                kind = connection.get("entity_kind")
                if kind is not None and kind not in ENTITY_KINDS:
                    offenders.append(f"{path.relative_to(ROOT)}: {kind!r}")
        self.assertEqual(offenders, [])

    def test_the_perpetrator_class_carries_directional_tags(self):
        # The reader feedback behind issue #119: Goebbels in Hans Fallada's
        # network wore the neutral "Political Gatekeeper". The directional
        # tag now states on whose side the pressure ran.
        fallada = json.loads(
            (DATA_DIR / "people/hans_fallada/ego_network.json").read_text("utf-8")
        )
        by_name = {
            connection["person_name"]: connection["relationship_type"]
            for connection in fallada["connections"]
        }
        self.assertEqual(by_name["Joseph Goebbels"], "political/censor")
        self.assertEqual(by_name["Alfred Rosenberg"], "political/banned_by")


class Normalization(unittest.TestCase):
    def test_folds_spelling_variants_without_an_alias(self):
        self.assertEqual(
            normalize_relationship_type("family/mother-in-law"),
            ("family/mother_in_law", True),
        )

    def test_maps_known_inventions_onto_the_vocabulary(self):
        self.assertEqual(
            normalize_relationship_type("other/political_gatekeeper"),
            ("political/censor", True),
        )
        self.assertEqual(
            normalize_relationship_type("colleague"),
            ("professional/colleague", True),
        )

    def test_reports_a_token_it_cannot_place(self):
        token, known = normalize_relationship_type("cosmic/entanglement")
        self.assertEqual(token, "cosmic/entanglement")
        self.assertFalse(known)


if __name__ == "__main__":
    unittest.main()

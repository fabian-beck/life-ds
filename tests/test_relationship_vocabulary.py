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
    RETIRED_CATEGORIES,
    ROLES,
    is_canonical,
    normalize_relationship_type,
    plain_parent_roles,
)

DATA_DIR = ROOT / "data"
OUTDATED = (DATA_DIR / "outdated.md").read_text("utf-8")
# Hidden persons and collections are off the deployed site and are not tracked
# in data/outdated.md; they are regenerated before they are shown again.
HIDDEN = {
    entry["id"]
    for registry, collection in (
        ("persons.json", "people"),
        ("meta_stories.json", "meta_stories"),
    )
    for entry in json.loads((DATA_DIR / registry).read_text("utf-8"))[collection]
    if entry.get("hidden") is True
}
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


def dataset_id(path):
    """The person or meta story id a data file belongs to."""
    relative = path.relative_to(DATA_DIR)
    if relative.parts[0] == "people":
        return relative.parts[1]
    return path.stem


def carries_retired_category(token):
    category = str(token or "").partition("/")[0]
    return category in RETIRED_CATEGORIES


def is_flagged_outdated(path):
    """Flagged in data/outdated.md, or hidden and therefore not tracked there."""
    return dataset_id(path) in HIDDEN or f"`{dataset_id(path)}`" in OUTDATED


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

    def test_locale_categories_do_not_outgrow_the_vocabulary(self):
        # A category the locales name but the module lacks is either a gap
        # the generator can no longer fill or a retired one kept only while
        # outdated datasets still carry it.
        prefix = "network.category."
        stray = [
            key[len(prefix) :]
            for key in LOCALES["en"]
            if key.startswith(prefix)
            and key[len(prefix) :] not in CATEGORIES | RETIRED_CATEGORIES
        ]
        self.assertEqual(stray, [])

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


class CorpusStaysCanonical(unittest.TestCase):
    # A retired category is not canonical — a run cannot emit it — but a
    # dataset that still carries one is tolerated as long as it is flagged
    # for regeneration in data/outdated.md, where the no-repair rule sends
    # it, or hidden, which keeps it off the deployed site until it is
    # regenerated. Anything else outside the vocabulary is an offender as
    # before.
    def _classify(self, path, token, offenders, unflagged):
        if is_canonical(token):
            return
        if carries_retired_category(token):
            if not is_flagged_outdated(path):
                unflagged.append(f"{path.relative_to(ROOT)}: {token!r}")
            return
        offenders.append(f"{path.relative_to(ROOT)}: {token!r}")

    def test_every_ego_network_type_is_in_the_vocabulary(self):
        offenders, unflagged = [], []
        for path in ego_network_files():
            data = json.loads(path.read_text("utf-8"))
            for connection in data.get("connections", []):
                token = connection.get("relationship_type", "")
                self._classify(path, token, offenders, unflagged)
        self.assertEqual(offenders, [])
        self.assertEqual(unflagged, [], "retired category not flagged as outdated")

    def test_every_meta_story_link_type_is_in_the_vocabulary(self):
        offenders, unflagged = [], []
        for path in meta_story_files():
            data = json.loads(path.read_text("utf-8"))
            links = (data.get("social_network") or {}).get("links") or []
            for link in links:
                holders = [link, *(link.get("endpoints") or {}).values()]
                for holder in holders:
                    token = holder.get("relationship_type")
                    if token:
                        self._classify(path, token, offenders, unflagged)
        self.assertEqual(offenders, [])
        self.assertEqual(unflagged, [], "retired category not flagged as outdated")

    def test_a_retired_category_is_out_of_the_vocabulary(self):
        self.assertEqual(RETIRED_CATEGORIES & CATEGORIES, frozenset())
        self.assertFalse(is_canonical("intellectual/influence"))

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
    def test_folds_spelling_variants(self):
        self.assertEqual(
            normalize_relationship_type("family/mother-in-law"),
            ("family/mother_in_law", True),
        )
        self.assertEqual(
            normalize_relationship_type("Professional/Political Rival"),
            ("professional/political_rival", True),
        )

    def test_reports_a_token_it_cannot_place(self):
        token, known = normalize_relationship_type("cosmic/entanglement")
        self.assertEqual(token, "cosmic/entanglement")
        self.assertFalse(known)


if __name__ == "__main__":
    unittest.main()


class ParentRoles(unittest.TestCase):
    # Issue #142: offered "biological_father" beside "father" and told to be
    # specific, the model labeled every ordinary parent biological. The fold
    # keeps the qualifier only where an adoptive or step parent gives it
    # something to contrast with.
    def _network(self, *types):
        return [
            {"person_name": f"P{i}", "relationship_type": t}
            for i, t in enumerate(types)
        ]

    def test_ordinary_parents_lose_the_qualifier(self):
        connections = self._network(
            "family/biological_father", "family/biological_mother", "family/son"
        )
        self.assertEqual(plain_parent_roles(connections), ["P0", "P1"])
        self.assertEqual(
            [c["relationship_type"] for c in connections],
            ["family/father", "family/mother", "family/son"],
        )

    def test_birth_parents_keep_it_beside_adoptive_ones(self):
        connections = self._network(
            "family/adoptive_father", "family/biological_mother"
        )
        self.assertEqual(plain_parent_roles(connections), [])
        self.assertEqual(
            connections[1]["relationship_type"], "family/biological_mother"
        )

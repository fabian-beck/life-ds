"""The closed relationship vocabulary, held against the locales.

A `relationship_type` is reader-facing through two locale lookups, so the
vocabulary module the generator and the reviews are constrained by and the
entries both locale files provide have to agree. Either can drift alone
without a build failure — the interface would quietly fall back to its generic
label — so these tests are where the drift becomes visible (issues #117 and
#119). What tokens a shipped dataset carries is not checked here: a run can
only emit a canonical one, and a dataset generated under an older vocabulary
is regenerated, not audited.
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

LOCALES = {
    lang: json.loads((ROOT / "src" / "locales" / f"{lang}.json").read_text("utf-8"))
    for lang in ("en", "de")
}


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

    def test_a_retired_category_is_out_of_the_vocabulary(self):
        self.assertEqual(RETIRED_CATEGORIES & CATEGORIES, frozenset())
        self.assertFalse(is_canonical("intellectual/influence"))


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

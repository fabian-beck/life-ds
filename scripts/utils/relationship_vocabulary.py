"""The closed relationship-type vocabulary for ego networks.

A `relationship_type` is a machine token of the form `category/role`. Both
segments are reader-facing through the locale files — the interface resolves
`network.category.{category}` and `network.role.{role}_one|_other` — so the
vocabulary is closed: the generator must choose from it, and a dataset that
predates a vocabulary change is regenerated rather than migrated.
`tests/test_relationship_vocabulary.py` holds the data, this module, and
both locale files to one another.

Two rules shape the role list:

- A role names what the other person is or did **toward the subject**, never
  a neutral office. Conflict roles are directional: `censor`, `persecutor`,
  and `banned_by` state that the regime or authority acted against the
  subject, where an "opponent" would misread one-sided persecution as mutual
  rivalry (issue #119). `opponent`, `rival`, and `adversary` remain for
  genuinely two-sided conflicts.
- Extending the vocabulary is a deliberate act: add the role here **and** its
  `network.role.*_one`/`_other` entries to `src/locales/en.json` and
  `de.json`, or the test fails and the interface falls back to a generic
  label.
"""

from __future__ import annotations

import re

CATEGORIES = frozenset(
    {
        "academic",
        "artistic",
        "business",
        "contextual",
        "enslaver",
        "family",
        "innovation",
        "intellectual",
        "other",
        "political",
        "professional",
        "religious",
        "social",
    }
)

ROLES = frozenset(
    {
        # family
        "aunt",
        "aunt_by_marriage",
        "biological_father",
        "biological_mother",
        "brother",
        "brother_in_law",
        "child",
        "child_in_law",
        "cousin",
        "daughter",
        "extended_family",
        "family_friend",
        "father",
        "father_in_law",
        "grandchild",
        "grandmother",
        "grandparent",
        "half_brother",
        "half_sibling",
        "in_law",
        "mother",
        "mother_in_law",
        "nephew",
        "nephew_successor",
        "niece",
        "sibling",
        "sister",
        "son",
        "son_in_law",
        "spouse",
        "stepchild",
        "stepfather",
        "uncle",
        "ward",
        # partners and intimates
        "fiancée",
        "muse",
        "partner",
        "romantic_partner",
        # friendship and social life
        "acquaintance",
        "association",
        "correspondent",
        "connector",
        "friend",
        "religious_community",
        # teaching and formation
        "advisor",
        "guardian",
        "household_tutor",
        "mentor",
        "protégé",
        "student",
        "teacher",
        # work
        "adjutant",
        "assistant",
        "business_partner",
        "client",
        "close_colleague",
        "co_founder",
        "co_inventor",
        "collaborator",
        "colleague",
        "commander",
        "consultant",
        "curator",
        "editor",
        "employee",
        "employer",
        "engineer_collaborator",
        "field_peer",
        "founding_colleague",
        "illustrator",
        "industry_partner",
        "institution",
        "manager",
        "organizer",
        "patient",
        "peer",
        "physician",
        "predecessor",
        "publisher",
        "subordinate",
        "successor",
        "superior",
        "supervisor",
        # support and reception
        "advocate",
        "ally",
        "biographer",
        "chronicler",
        "endorser",
        "funder",
        "influence",
        "inspiration",
        "legacy",
        "patron",
        "subject",
        # conflict — two-sided
        "adversary",
        "conspirator",
        "critic",
        "opponent",
        "political_rival",
        "rival",
        # conflict — directional: the authority acted against the subject
        "banned_by",
        "censor",
        "persecutor",
    }
)

ENTITY_KINDS = ("person", "organization", "group")

_SEPARATORS = re.compile(r"[\s\-]+")


def token_key(token: str) -> str:
    """Fold one segment to its canonical key: lower case, one separator."""
    return _SEPARATORS.sub("_", str(token or "").strip().lower())


def fold_type(value: str) -> str:
    """Fold a whole `category/role` token, both segments, keeping the slash."""
    parts = [token_key(part) for part in str(value or "").split("/", 1)]
    return "/".join(part for part in parts if part)


def is_canonical(value: str) -> bool:
    """True when the token is `category/role` with both segments known."""
    category, slash, role = str(value or "").partition("/")
    return bool(slash) and category in CATEGORIES and role in ROLES


def normalize_relationship_type(value: str) -> tuple[str, bool]:
    """Fold a relationship type and check it against the vocabulary.

    Returns the folded token (spelling variants collapsed to one canonical
    spelling) and whether it is in the vocabulary. An unknown token comes
    back folded but otherwise unchanged, with False — the caller decides
    whether to warn and keep it (generator) or refuse it (review). Data
    generated before the vocabulary existed is not mapped here; outdated
    datasets are simply regenerated.
    """
    folded = fold_type(value)
    return folded, is_canonical(folded)

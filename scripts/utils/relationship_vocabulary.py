"""The closed relationship-type vocabulary for ego networks.

A `relationship_type` is a machine token of the form `category/role`. Both
segments are reader-facing through the locale files — the interface resolves
`network.category.{category}` and `network.role.{role}_one|_other` — so the
vocabulary is closed: the generation schema types both segments as the
Literals below, so a run cannot emit a token outside it, and a dataset that
predates a vocabulary change is regenerated rather than migrated.
`tests/test_relationship_vocabulary.py` holds this module and both locale
files to each other.

Categories stay coarse: the interface opens one circle per category, so two
categories that a reader cannot tell apart split one circle in two. That is
why `academic` alone holds the ties of scholarship — teachers, students,
colleagues, influences, and the opponent of a long scientific debate — and
the `intellectual` category that used to sit beside it is retired (see
`RETIRED_CATEGORIES`).

Two rules shape the role list:

- A role names what the other person is or did **toward the subject**, never
  a neutral office. Conflict roles are directional: `censor`, `persecutor`,
  and `banned_by` state that the regime or authority acted against the
  subject, where an "opponent" would misread one-sided persecution as mutual
  rivalry (issue #119). `opponent`, `rival`, and `adversary` remain for
  genuinely two-sided conflicts.
- A parent is `father` or `mother` unless the sources say otherwise. The
  qualified roles mark the exception: `adoptive_*` and `step*` for the
  parents who raised a subject born to others, `biological_*` for the birth
  parents in exactly that case. Offered both tokens and asked for the most
  specific one, a model labeled every ordinary parent "biological" (issue
  #142), so `plain_parent_roles` below folds the qualifier away whenever the
  network holds no adoptive or step parent to contrast it with.
- Extending the vocabulary is a deliberate act: add the role here **and** its
  `network.role.*_one`/`_other` entries to `src/locales/en.json` and
  `de.json`, or the test fails and the interface falls back to a generic
  label.
"""

from __future__ import annotations

import re
from typing import Literal, get_args

RelationshipCategory = Literal[
    "academic",
    "artistic",
    "business",
    "contextual",
    "enslaver",
    "family",
    "innovation",
    "other",
    "political",
    "professional",
    "religious",
    "social",
]

RelationshipRole = Literal[
    # family
    "adoptive_father",
    "adoptive_mother",
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
    "stepmother",
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
]

CATEGORIES = frozenset(get_args(RelationshipCategory))
ROLES = frozenset(get_args(RelationshipRole))

# Categories a run can no longer emit. A dataset still carrying one is
# outdated (listed in data/outdated.md) and is regenerated, not rewritten;
# until then the locales keep the entry so the shipped circle stays named.
RETIRED_CATEGORIES = frozenset({"intellectual"})

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


_QUALIFIED_PARENTS = {
    "family/biological_father": "family/father",
    "family/biological_mother": "family/mother",
}
_CONTRASTING_PARENTS = frozenset(
    {
        "family/adoptive_father",
        "family/adoptive_mother",
        "family/stepfather",
        "family/stepmother",
    }
)


def plain_parent_roles(connections: list) -> list:
    """Fold `biological_*` back to `father`/`mother` where nothing contrasts it.

    The qualifier is meaningful only beside an adoptive or step parent in the
    same network. Everywhere else it is the model's reading of "most
    specific" — see the module docstring — and folding it here, in place,
    means the shipped data never depends on the prompt winning that argument.
    Returns the names whose role was folded, for the run log.
    """
    if any(c.get("relationship_type") in _CONTRASTING_PARENTS for c in connections):
        return []
    folded = []
    for connection in connections:
        plain = _QUALIFIED_PARENTS.get(connection.get("relationship_type"))
        if plain:
            connection["relationship_type"] = plain
            folded.append(connection.get("person_name"))
    return folded

"""The closed relationship-type vocabulary for ego networks.

A `relationship_type` is a machine token of the form `category/role`. Both
segments are reader-facing through the locale files — the interface resolves
`network.category.{category}` and `network.role.{role}_one|_other` — so the
vocabulary is closed: the generator must choose from it, and the corpus is
normalized onto it. `tests/test_relationship_vocabulary.py` holds the data,
this module, and both locale files to one another.

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

# Every relationship type the corpus has carried that is not (or not yet) in
# the closed vocabulary, mapped onto it. Keys are matched after `token_key`
# folding of both segments, so spelling variants need no entry of their own.
# The map is what `normalize_relationship_type` and the corpus sweep in
# `scripts/normalize_network_types.py` apply; the generator applies it to
# fresh output so an invented type is folded back into the vocabulary before
# it reaches disk.
TYPE_ALIASES: dict[str, str] = {
    # bare legacy tokens (category-less files predating `category/role`)
    "collaborator": "professional/collaborator",
    "colleague": "professional/colleague",
    "friend": "social/friend",
    "household_tutor": "academic/household_tutor",
    "mentor": "professional/mentor",
    "patron": "professional/patron",
    "rival": "professional/rival",
    "student": "academic/student",
    # academic
    "academic/civic_colleague": "academic/colleague",
    "academic/commentator": "academic/endorser",
    "academic/dialogue_partner": "academic/correspondent",
    "academic/doctoral_associated": "academic/advisor",
    "academic/influencee": "academic/successor",
    "academic/institutional_affiliation": "academic/institution",
    "academic/intellectual_mentor": "academic/mentor",
    "academic/intellectual_influence": "academic/influence",
    "academic/intellectual_predecessor": "academic/predecessor",
    "academic/lecturer_and_professional_advisor": "academic/advisor",
    "academic/lecturer_and_professional_predecessor": "academic/predecessor",
    "academic/patron_recommender": "academic/patron",
    "academic/schoolteacher": "academic/teacher",
    "academic/scientific_colleague": "academic/colleague",
    "academic/scientific_correspondent": "academic/correspondent",
    "academic/social_friend": "academic/friend",
    # artistic
    "artistic/correspondent_and_admirer": "artistic/correspondent",
    "artistic/correspondent_and_philanthropic_supporter": "artistic/patron",
    "artistic/curatorial_team": "artistic/curator",
    "artistic/documentarian": "artistic/chronicler",
    "artistic/indirect_association": "artistic/peer",
    "artistic/intellectual_foil": "artistic/peer",
    "artistic/intellectual_peer": "artistic/peer",
    "artistic/movement_colleague": "artistic/colleague",
    "artistic/peer_poet": "artistic/peer",
    "artistic/poetic_subject": "artistic/muse",
    "artistic/poetic_subject_and_possible_collaborator": "artistic/muse",
    "artistic/potential_collaborator": "artistic/acquaintance",
    # contextual
    "contextual/political_figure": "contextual/influence",
    # enslaver
    "enslaver/household_patron": "enslaver/patron",
    # intellectual
    "intellectual/cited_influence": "intellectual/influence",
    "intellectual/psychoanalytic_consultant": "intellectual/consultant",
    # other — the perpetrator class of issue #119 first
    "other/political_gatekeeper": "political/censor",
    "other/political_opponent": "political/banned_by",
    "other/historical_comparison": "professional/peer",
    "other/intellectual_influence": "intellectual/influence",
    "other/posthumous_editor": "professional/editor",
    "other/recognition": "professional/peer",
    "other/religious_influence": "religious/influence",
    "other/religious_teacher": "religious/teacher",
    # political
    "political/adversary_target": "political/adversary",
    "political/government_leader": "political/superior",
    # professional
    "professional/ceo_colleague_rival": "professional/rival",
    "professional/administrator": "professional/manager",
    "professional/analyst": "professional/chronicler",
    "professional/analyst_supporter": "professional/advocate",
    "professional/archbishop_ally": "religious/ally",
    "professional/authorship_attester": "professional/endorser",
    "professional/award_jury": "professional/endorser",
    "professional/award_presenter": "professional/patron",
    "professional/business_associate": "business/business_partner",
    "professional/business_collaborator": "professional/collaborator",
    "professional/cabinet_member": "professional/colleague",
    "professional/cabinet_rivals": "professional/political_rival",
    "professional/client_or_talent": "professional/client",
    "professional/collaborator_and_rival": "professional/collaborator",
    "professional/collaborator_friend": "professional/collaborator",
    "professional/colleague_and_recruit": "professional/colleague",
    "professional/commander_and_patron": "professional/commander",
    "professional/corporate_leader": "professional/superior",
    "professional/corporate_successor": "professional/successor",
    "professional/critic_subject": "professional/subject",
    "professional/cultural_partner": "professional/collaborator",
    "professional/design_partner": "professional/collaborator",
    "professional/diplomatic_adversaries": "professional/adversary",
    "professional/diplomatic_colleague": "professional/colleague",
    "professional/early_collaborator": "professional/collaborator",
    "professional/educator": "professional/teacher",
    "professional/employer_rival": "professional/employer",
    "professional/encounter": "professional/acquaintance",
    "professional/fellow_officer": "professional/colleague",
    "professional/foreman": "professional/collaborator",
    "professional/foundation_legacy": "professional/legacy",
    "professional/friend_and_colleague": "professional/colleague",
    "professional/government_client": "professional/client",
    "professional/honour": "professional/patron",
    "professional/industry_peer": "professional/peer",
    "professional/institutional_partner": "professional/client",
    "professional/institutional_collaborator": "professional/collaborator",
    "professional/institutional_context": "contextual/influence",
    "professional/intellectual_counterpart": "professional/peer",
    "professional/intellectual_peer": "professional/peer",
    "professional/intellectual_interlocutor": "professional/peer",
    "professional/intellectual_predecessor": "professional/predecessor",
    "professional/investor_mentor": "professional/funder",
    "professional/legacy_eponym": "professional/legacy",
    "professional/legacy_network": "professional/legacy",
    "professional/licensee": "business/business_partner",
    "professional/mentee_collaborator": "professional/protégé",
    "professional/military_adversary": "professional/adversary",
    "professional/military_collaborator": "professional/collaborator",
    "professional/military_colleague": "professional/colleague",
    "professional/military_commander": "professional/commander",
    "professional/military_subordinate": "professional/subordinate",
    "professional/modernist_peer": "professional/peer",
    "professional/operations_and_successor": "professional/successor",
    "professional/overlord_predecessor": "professional/predecessor",
    "professional/pamphlet_opponent": "professional/opponent",
    "professional/papal_ally": "religious/ally",
    "professional/patron_editor": "professional/patron",
    "professional/peer_criticized": "professional/subject",
    "professional/political_collaborator": "professional/collaborator",
    "professional/political_colleague": "professional/colleague",
    "professional/political_correspondent": "professional/correspondent",
    "professional/political_ally": "professional/ally",
    "professional/political_appointer": "professional/patron",
    "professional/posthumous_political": "professional/legacy",
    "professional/posthumous_symbolic": "professional/legacy",
    "professional/predecessor_claimant": "professional/predecessor",
    "professional/revolutionary_and_constitutional_collaborator": "professional/collaborator",
    "professional/revolutionary_and_executive_colleague": "professional/colleague",
    "professional/rival_collaborator": "professional/rival",
    "professional/rival_critic": "professional/critic",
    "professional/science_communicator": "professional/advocate",
    "professional/scientific_collaborator": "professional/collaborator",
    "professional/scientific_organizer": "professional/organizer",
    "professional/scientific_peer": "professional/peer",
    "professional/society_colleague": "professional/colleague",
    "professional/source_subject": "professional/inspiration",
    "professional/symbolic": "professional/patron",
    "professional/translation_project": "professional/influence",
    "professional/tutor_and_travel_companion": "academic/household_tutor",
    # religious
    "religious/archbishop_ally": "religious/ally",
    "religious/bishop_chronicler": "religious/chronicler",
    # social
    "social/affair": "social/romantic_partner",
    "social/caregiver": "social/family_friend",
    "social/commentator": "social/chronicler",
    "social/corps_network": "social/acquaintance",
    "social/friend_board_colleague": "social/friend",
    "social/friend_colleague": "social/friend",
    "social/friend_mentor": "social/friend",
    "social/intellectual_collaborator": "intellectual/collaborator",
    "social/intellectual_peer": "intellectual/peer",
    "social/intimate_friend": "social/friend",
    "social/participant": "social/acquaintance",
    "social/romantic_friend": "social/friend",
    "social/romantic_friendship": "social/friend",
    "social/scientific_contact": "social/connector",
    "social/society_figure": "social/ally",
    "social/spiritual_teacher": "religious/teacher",
    # meta-story derivations that predate the vocabulary
    "friendship/close_friend": "social/friend",
    "friendship/colleague": "professional/colleague",
}

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
    """Map a relationship type onto the closed vocabulary.

    Returns the canonical token and whether it is in the vocabulary. An
    unknown token comes back folded but otherwise unchanged, with False —
    the caller decides whether that is a warning (corpus sweep) or a reason
    to log and keep going (generator).
    """
    folded = fold_type(value)
    resolved = TYPE_ALIASES.get(folded, folded)
    return resolved, is_canonical(resolved)

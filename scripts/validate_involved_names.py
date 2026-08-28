#!/usr/bin/env python3
"""Check that an event's people are spelled the way the network spells them.

The story matches ``involved_people`` against ``ego_network.json`` by name to
draw the person chips (``getRelevantPeople`` in
``src/utils/story/personMatching.js``), scoring first and last names without
folding diacritics or ß/ss. The corpus has already shipped the miss this
produces: the events wrote "Marga von Hößlin Planck" while the network wrote
"Marga von Hösslin", the ß kept the components from matching, and the chip
silently lost its relationship metadata. Nothing reported it, because a failed
match is also the correct outcome for the many involved people who are simply
not in the network.

What this flags is the near miss the matcher cannot see: an involved name
that folds to the same person as a connection — diacritics and ß/ss
collapsed, particles dropped, parentheticals stripped, token subsets and
one-letter slips allowed — and that the interface's own scoring nonetheless
rejects. The scoring is the port in ``scripts/utils/person_matching.py``; keep it
in sync when the matcher changes. Findings are one person spelled two ways,
and the fix is to spell them identically; which spelling wins is the
editor's call, not this script's.

A pair that is genuinely two people belongs in ACCEPTED below, with the
reason.

Usage:
    python scripts/validate_involved_names.py            # exit 1 on any finding
    python scripts/validate_involved_names.py max_planck
"""

from __future__ import annotations

import re
import sys
import unicodedata
from typing import Any, Dict, List, Optional, Set, Tuple

from config import PEOPLE_DIR
from utils.json_io import read_json
from utils.person_matching import PARENTHETICAL, interface_would_match
from utils.validation import run_dataset_check

# Pairs that look like one person spelled two ways and are nonetheless two
# people. Keyed by person id, the involved name, and the connection's name.
ACCEPTED: Dict[Tuple[str, str, str], str] = {}

PARTICLES = {
    "von",
    "van",
    "de",
    "der",
    "zu",
    "da",
    "of",
    "the",
    "née",
    "nee",
    "geb",
    "geborene",
}


class NameFinding:
    def __init__(self, person_id: str, involved: str, connection: str, where: str):
        self.person_id = person_id
        self.involved = involved
        self.connection = connection
        self.where = where

    def __str__(self) -> str:
        return (
            f'{self.person_id} {self.where}: "{self.involved}" will not match '
            f'the network\'s "{self.connection}" — one person, two spellings'
        )


# ---------------------------------------------------------------------------
# The folding side: would an editor call these the same person?
# ---------------------------------------------------------------------------


def fold(name: str) -> List[str]:
    """A name as comparable tokens: unaccented, ß collapsed, particles gone."""
    plain = PARENTHETICAL.sub(" ", name).replace("ß", "ss")
    plain = unicodedata.normalize("NFKD", plain)
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    tokens = re.findall(r"[^\W\d_]+", plain.lower())
    return [t for t in tokens if t not in PARTICLES]


def within_one_edit(a: str, b: str) -> bool:
    """Whether two tokens differ by a single letter — long tokens only, so
    "Grete"/"Greta" can trip it but "Karl"/"Carl" style short names cannot
    outweigh their difference."""
    if a == b:
        return True
    if min(len(a), len(b)) < 5 or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    longer, shorter = (a, b) if len(a) > len(b) else (b, a)
    return any(longer[:i] + longer[i + 1 :] == shorter for i in range(len(longer)))


def tokens_subsume(smaller: List[str], larger: List[str]) -> bool:
    """Every token of the smaller name appears in the larger, one edit off at
    most."""
    remaining = list(larger)
    for token in smaller:
        for candidate in remaining:
            if within_one_edit(token, candidate):
                remaining.remove(candidate)
                break
        else:
            return False
    return True


def same_person_folded(involved: str, connection: str) -> bool:
    a, b = fold(involved), fold(connection)
    if not a or not b:
        return False
    smaller, larger = (a, b) if len(a) <= len(b) else (b, a)
    # The given name must survive the comparison: a shared surname alone
    # ("Karl Planck" against "Grete Planck") is a family, not a spelling.
    return tokens_subsume(smaller, larger) and within_one_edit(smaller[0], larger[0])


# ---------------------------------------------------------------------------
# The check: the same person folded, rejected by the interface.
# ---------------------------------------------------------------------------


def check_person(person_id: str, data: Dict[str, Any]) -> List[NameFinding]:
    network_path = PEOPLE_DIR / person_id / "ego_network.json"
    if not network_path.exists():
        return []
    network = read_json(network_path)
    connections = [
        name
        for connection in network.get("connections") or []
        if isinstance(name := connection.get("person_name"), str)
    ]
    findings: List[NameFinding] = []
    reported: Set[Tuple[str, str]] = set()
    for event in data.get("events") or []:
        for involved in event.get("involved_people") or []:
            if not isinstance(involved, str):
                continue
            if any(interface_would_match(involved, c) for c in connections):
                continue
            for connection in connections:
                key = (involved, connection)
                if key in reported or (person_id, *key) in ACCEPTED:
                    continue
                if same_person_folded(involved, connection):
                    reported.add(key)
                    findings.append(
                        NameFinding(
                            person_id,
                            involved,
                            connection,
                            f'event {event.get("date")} "{event.get("title")}"',
                        )
                    )
    return findings


def main(argv: Optional[List[str]] = None) -> int:
    return run_dataset_check(check_person, description=__doc__, argv=argv)


if __name__ == "__main__":
    sys.exit(main())

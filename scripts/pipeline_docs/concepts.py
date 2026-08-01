#!/usr/bin/env python3
"""The conceptual vocabulary of the system, and the glyph that stands for each.

The report is about a system, not about a directory. A reader who is told that
`ego_network.json` is written by one step and read by another has learned a
fact about a path; a reader who is told that the *social network* is derived
once per subject and merged again per theme has learned the same fact about the
system. This module holds the second vocabulary: the handful of things the
pipelines actually produce and the interface actually shows—source material,
profile, life events, narrative text, geography, the social network, imagery,
visual identity, theme, languages—each with an id the rest of the docs build
refers to, and each marked as the one thing read from outside or as something
derived from it.

Every concept carries an icon, and the icons are the interface's own: they are
Material Design Icons, named exactly as `@mdi/js` exports them, and where the
application already draws a concept it draws the same glyph. The network button
above a story and the network column of a pipeline figure are then visibly the
same thing, which is the point—the report and the product share one visual
vocabulary instead of each inventing its own.

Path data is vendored rather than resolved at build time, because the report
must build from a checkout with no `node_modules`. `check_icons()` closes the
loop when the package *is* installed: a vendored path that has drifted from the
icon the application would render is reported as a drift error, exactly as a
step that no longer exists is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
MDI_SOURCE = REPO_ROOT / "node_modules" / "@mdi" / "js" / "mdi.js"


INPUT = "input"
DERIVED = "derived"


@dataclass(frozen=True)
class Concept:
    """One thing the system is about, in the vocabulary a reader thinks in.

    `role` is the distinction the data model turns on: one concept is read from
    outside and the rest are derived, and a reader who cannot see which is which
    cannot see what the pipelines are for.

    `interface` records where the application draws the same glyph. It is a
    maintainer's justification for the icon, not page copy: the report explains
    the interface in its own section and has no business doing it again in a
    legend, so this never reaches the payload.
    """

    id: str
    label: str
    icon: str
    """The `@mdi/js` icon, in its kebab-case name—`mdi-account-multiple-outline`."""
    blurb: str
    interface: str
    role: str = DERIVED


CONCEPTS: Tuple[Concept, ...] = (
    Concept(
        "sources",
        "Source material",
        "mdi-book",
        "Encyclopedic prose, images and place names—the only thing the system "
        "does not produce itself.",
        "The sources listed under every event, and the links that close a story.",
        role=INPUT,
    ),
    Concept(
        "profile",
        "Profile",
        "mdi-account-outline",
        "Who a story is about: a name, a lifespan, the roles a life is "
        "remembered for, and the portrait that stands for it.",
        "The cards on the landing page and the person chips inside a story.",
    ),
    Concept(
        "events",
        "Life events",
        "mdi-timeline-text-outline",
        "Dated episodes with a place, the persons involved and the sources "
        "behind them, grouped into the phases of a life.",
        "The event slides and the timeline that runs along the foot of them.",
    ),
    Concept(
        "narrative",
        "Narrative text",
        "mdi-text-long",
        "The written register: an event’s own description, and the article "
        "prose that surrounds a theme’s components.",
        "The long-form text of an event slide and of a meta story’s sections.",
    ),
    Concept(
        "places",
        "Geography",
        "mdi-map-marker-outline",
        "Historical toponyms resolved to modern coordinates, so a life can be "
        "read as a movement through space.",
        "The place under an event’s date, and the map the camera flies across.",
    ),
    Concept(
        "network",
        "Social network",
        "mdi-account-multiple-outline",
        "Typed, weighted and dated relationships—one ego network per subject, "
        "merged into one graph per theme.",
        "The network button above a story and the force-directed graph it opens.",
    ),
    Concept(
        "imagery",
        "Imagery",
        "mdi-image-outline",
        "Licensed illustrations matched to the events they depict, and the "
        "portrait derived from one of them.",
        "The pictures on an event slide, the lightbox, and every portrait.",
    ),
    Concept(
        "identity",
        "Visual identity",
        "mdi-palette-outline",
        "A palette, a typography and a background pattern generated per "
        "subject, so each story is presented in a register of its own.",
        "The color and type of every story, injected as CSS custom properties.",
    ),
    Concept(
        "theme",
        "Theme",
        "mdi-lightbulb-on-outline",
        "An idea traced across several finished biographies—the second-order "
        "story, and the only one whose inputs are this system’s own output.",
        "The meta stories on the landing page and the lives they link into.",
    ),
    Concept(
        "languages",
        "Languages",
        "mdi-translate",
        "Every document in every supported language, each carrying a "
        "fingerprint of the text it was derived from.",
        "The language selector, and the address of every localized story.",
    ),
)


# Vendored from @mdi/js. `check_icons()` verifies these against the installed
# package whenever there is one, so a drift is a build error, not a surprise.
ICON_PATHS: Dict[str, str] = {
    "mdi-book": "M18,22A2,2 0 0,0 20,20V4C20,2.89 19.1,2 18,2H12V9L9.5,7.5L7,9V2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18Z",
    "mdi-account-outline": "M12,4A4,4 0 0,1 16,8A4,4 0 0,1 12,12A4,4 0 0,1 8,8A4,4 0 0,1 12,4M12,6A2,2 0 0,0 10,8A2,2 0 0,0 12,10A2,2 0 0,0 14,8A2,2 0 0,0 12,6M12,13C14.67,13 20,14.33 20,17V20H4V17C4,14.33 9.33,13 12,13M12,14.9C9.03,14.9 5.9,16.36 5.9,17V18.1H18.1V17C18.1,16.36 14.97,14.9 12,14.9Z",
    "mdi-timeline-text-outline": "M5 12C5 13.11 4.11 14 3 14C1.9 14 1 13.11 1 12C1 10.9 1.9 10 3 10C4.11 10 5 10.9 5 12M4 2V8H2V2H4M2 22V16H4V22H2M24 6V18C24 19.11 23.11 20 22 20H10C8.9 20 8 19.11 8 18V14L6 12L8 10V6C8 4.89 8.9 4 10 4H22C23.11 4 24 4.89 24 6M22 6H10V10.83L8.83 12L10 13.17V18H22V6M12 9H20V11H12V9M12 13H18V15H12V13Z",
    "mdi-text-long": "M4,5H20V7H4V5M4,9H20V11H4V9M4,13H20V15H4V13M4,17H14V19H4V17Z",
    "mdi-map-marker-outline": "M12,6.5A2.5,2.5 0 0,1 14.5,9A2.5,2.5 0 0,1 12,11.5A2.5,2.5 0 0,1 9.5,9A2.5,2.5 0 0,1 12,6.5M12,2A7,7 0 0,1 19,9C19,14.25 12,22 12,22C12,22 5,14.25 5,9A7,7 0 0,1 12,2M12,4A5,5 0 0,0 7,9C7,10 7,12 12,18.71C17,12 17,10 17,9A5,5 0 0,0 12,4Z",
    "mdi-account-multiple-outline": "M13.07 10.41A5 5 0 0 0 13.07 4.59A3.39 3.39 0 0 1 15 4A3.5 3.5 0 0 1 15 11A3.39 3.39 0 0 1 13.07 10.41M5.5 7.5A3.5 3.5 0 1 1 9 11A3.5 3.5 0 0 1 5.5 7.5M7.5 7.5A1.5 1.5 0 1 0 9 6A1.5 1.5 0 0 0 7.5 7.5M16 17V19H2V17S2 13 9 13 16 17 16 17M14 17C13.86 16.22 12.67 15 9 15S4.07 16.31 4 17M15.95 13A5.32 5.32 0 0 1 18 17V19H22V17S22 13.37 15.94 13Z",
    "mdi-image-outline": "M19,19H5V5H19M19,3H5A2,2 0 0,0 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V5A2,2 0 0,0 19,3M13.96,12.29L11.21,15.83L9.25,13.47L6.5,17H17.5L13.96,12.29Z",
    "mdi-palette-outline": "M12,22A10,10 0 0,1 2,12A10,10 0 0,1 12,2C17.5,2 22,6 22,11A6,6 0 0,1 16,17H14.2C13.9,17 13.7,17.2 13.7,17.5C13.7,17.6 13.8,17.7 13.8,17.8C14.2,18.3 14.4,18.9 14.4,19.5C14.5,20.9 13.4,22 12,22M12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20C12.3,20 12.5,19.8 12.5,19.5C12.5,19.3 12.4,19.2 12.4,19.1C12,18.6 11.8,18.1 11.8,17.5C11.8,16.1 12.9,15 14.3,15H16A4,4 0 0,0 20,11C20,7.1 16.4,4 12,4M6.5,10C7.3,10 8,10.7 8,11.5C8,12.3 7.3,13 6.5,13C5.7,13 5,12.3 5,11.5C5,10.7 5.7,10 6.5,10M9.5,6C10.3,6 11,6.7 11,7.5C11,8.3 10.3,9 9.5,9C8.7,9 8,8.3 8,7.5C8,6.7 8.7,6 9.5,6M14.5,6C15.3,6 16,6.7 16,7.5C16,8.3 15.3,9 14.5,9C13.7,9 13,8.3 13,7.5C13,6.7 13.7,6 14.5,6M17.5,10C18.3,10 19,10.7 19,11.5C19,12.3 18.3,13 17.5,13C16.7,13 16,12.3 16,11.5C16,10.7 16.7,10 17.5,10Z",
    "mdi-lightbulb-on-outline": "M20,11H23V13H20V11M1,11H4V13H1V11M13,1V4H11V1H13M4.92,3.5L7.05,5.64L5.63,7.05L3.5,4.93L4.92,3.5M16.95,5.63L19.07,3.5L20.5,4.93L18.37,7.05L16.95,5.63M12,6A6,6 0 0,1 18,12C18,14.22 16.79,16.16 15,17.2V19A1,1 0 0,1 14,20H10A1,1 0 0,1 9,19V17.2C7.21,16.16 6,14.22 6,12A6,6 0 0,1 12,6M14,21V22A1,1 0 0,1 13,23H11A1,1 0 0,1 10,22V21H14M11,18H13V15.87C14.73,15.43 16,13.86 16,12A4,4 0 0,0 12,8A4,4 0 0,0 8,12C8,13.86 9.27,15.43 11,15.87V18Z",
    "mdi-translate": "M12.87,15.07L10.33,12.56L10.36,12.53C12.1,10.59 13.34,8.36 14.07,6H17V4H10V2H8V4H1V6H12.17C11.5,7.92 10.44,9.75 9,11.35C8.07,10.32 7.3,9.19 6.69,8H4.69C5.42,9.63 6.42,11.17 7.67,12.56L2.58,17.58L4,19L9,14L12.11,17.11L12.87,15.07M18.5,10H16.5L12,22H14L15.12,19H19.87L21,22H23L18.5,10M15.88,17L17.5,12.67L19.12,17H15.88Z",
}


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------


def concept_ids() -> List[str]:
    return [concept.id for concept in CONCEPTS]


def concept_by_id(concept_id: str) -> Optional[Concept]:
    for concept in CONCEPTS:
        if concept.id == concept_id:
            return concept
    return None


def icon_of(concept_id: str) -> str:
    """The SVG path data a page draws for a concept, or an empty string."""
    concept = concept_by_id(concept_id)
    if concept is None:
        return ""
    return ICON_PATHS.get(concept.icon, "")


def to_json() -> List[Dict[str, str]]:
    """The vocabulary as the payload carries it, icon path included.

    Without `interface`: where the application draws the same glyph is why the
    icon was chosen, not something the data model section should stop to
    explain.
    """
    return [
        {
            "id": concept.id,
            "label": concept.label,
            "icon": concept.icon,
            "path": ICON_PATHS.get(concept.icon, ""),
            "blurb": concept.blurb,
            "role": concept.role,
        }
        for concept in CONCEPTS
    ]


# ---------------------------------------------------------------------------
# Self-checks
# ---------------------------------------------------------------------------


def _installed_icons() -> Dict[str, str]:
    """Every icon `@mdi/js` exports, keyed by its kebab-case name.

    Returns nothing at all when the package is not installed: the report has to
    build from a bare checkout, so a missing `node_modules` is a skipped check
    rather than a failure.
    """
    if not MDI_SOURCE.is_file():
        return {}
    text = MDI_SOURCE.read_text(encoding="utf-8")
    found: Dict[str, str] = {}
    for name, data in re.findall(r'export var (mdi\w+) = "([^"]*)"', text):
        kebab = re.sub(r"(?<!^)(?=[A-Z0-9])", "-", name[3:]).lower()
        found["mdi-" + kebab] = data
    return found


def check_icons() -> List[str]:
    """Problems a reader would see as a wrong or missing glyph."""
    problems: List[str] = []
    seen: Dict[str, str] = {}
    for concept in CONCEPTS:
        where = f"concept '{concept.id}'"
        if concept.id in seen:
            problems.append(f"{where}: duplicate id")
        seen[concept.id] = concept.label
        if concept.icon not in ICON_PATHS:
            problems.append(f"{where}: no vendored path for '{concept.icon}'")
        if not concept.blurb.strip() or not concept.interface.strip():
            problems.append(f"{where}: has no blurb or no interface note")
        if concept.role not in (INPUT, DERIVED):
            problems.append(f"{where}: unknown role '{concept.role}'")

    installed = _installed_icons()
    if not installed:
        return problems
    for name, data in sorted(ICON_PATHS.items()):
        if name not in installed:
            problems.append(f"icon '{name}' is not an @mdi/js export")
        elif installed[name] != data:
            problems.append(
                f"icon '{name}' has drifted from @mdi/js—revendor its path data"
            )
    return problems

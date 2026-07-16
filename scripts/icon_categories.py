#!/usr/bin/env python3
"""Icon category mappings for event type visualization using Material Design Icons (MDI)."""

from typing import Dict, List, Optional

# Comprehensive icon category mappings for biographical events
ICON_CATEGORIES = {
    # Life Milestones
    "birth": "mdi-candle",
    "death": "mdi-cross",
    "marriage": "mdi-ring",
    "engagement": "mdi-heart",
    "divorce": "mdi-heart-broken",

    # Education & Academic
    "education_start": "mdi-school",
    "enrollment": "mdi-school",
    "graduation": "mdi-school",
    "degree": "mdi-certificate",
    "scholarship": "mdi-trophy",
    "thesis": "mdi-book-open-variant",
    "dissertation": "mdi-book-open-variant",
    "lecture": "mdi-school-outline",
    "professorship": "mdi-school-outline",

    # Professional & Career
    "appointment": "mdi-briefcase",
    "employment": "mdi-briefcase",
    "promotion": "mdi-arrow-up-bold",
    "resignation": "mdi-exit-to-app",
    "retirement": "mdi-account-clock",

    # Awards & Recognition
    "award": "mdi-medal",
    "prize": "mdi-trophy",
    "honor": "mdi-star",
    "knighthood": "mdi-shield-crown",
    "fellowship": "mdi-account-group",

    # Publications & Creative Work
    "publication": "mdi-book",
    "paper": "mdi-file-document",
    "article": "mdi-file-document",
    "book": "mdi-book",
    "patent": "mdi-certificate",
    "artwork": "mdi-palette",
    "painting": "mdi-palette",
    "sculpture": "mdi-cube",
    "composition": "mdi-music-note",
    "performance": "mdi-microphone",

    # Political & Military
    "coronation": "mdi-crown",
    "enthronement": "mdi-crown",
    "title_grant": "mdi-seal",
    "succession": "mdi-crown",
    "battle": "mdi-sword-cross",
    "war": "mdi-sword-cross",
    "military_service": "mdi-shield",
    "treaty": "mdi-handshake",
    "alliance": "mdi-handshake",
    "peace": "mdi-peace",
    "conquest": "mdi-flag",
    "rebellion": "mdi-flag-triangle",

    # Religious & Spiritual
    "consecration": "mdi-church",
    "ordination": "mdi-church",
    "religious_event": "mdi-book-cross",
    "canonization": "mdi-star-circle",
    "pilgrimage": "mdi-walk",
    "monastery": "mdi-church",
    "diocese": "mdi-church",

    # Construction & Architecture
    "building_construction": "mdi-office-building",
    "foundation": "mdi-hammer",
    "castle": "mdi-castle",
    "cathedral": "mdi-church",
    "monument": "mdi-pillar",
    "design": "mdi-drawing",

    # Travel & Movement
    "travel": "mdi-map-marker",
    "journey": "mdi-map-marker",
    "expedition": "mdi-compass",
    "exploration": "mdi-compass",
    "migration": "mdi-map-marker-multiple",
    "relocation": "mdi-home-switch-outline",
    "exile": "mdi-exit-to-app",

    # Scientific & Technical
    "discovery": "mdi-lightbulb-on-outline",
    "invention": "mdi-lightbulb-on-outline",
    "experiment": "mdi-test-tube",
    "research": "mdi-microscope",
    "observation": "mdi-eye",
    "conference": "mdi-account-group",
    "symposium": "mdi-account-group",

    # Legal & Political Events
    "trial": "mdi-gavel",
    "court_case": "mdi-gavel",
    "arrest": "mdi-handcuffs",
    "imprisonment": "mdi-lock",
    "pardon": "mdi-lock-open",
    "election": "mdi-vote",
    "legislation": "mdi-file-document-edit",

    # Social & Cultural
    "meeting": "mdi-account-group",
    "collaboration": "mdi-account-multiple",
    "correspondence": "mdi-email",
    "debate": "mdi-forum",
    "speech": "mdi-microphone",

    # Financial & Economic
    "inheritance": "mdi-cash",
    "bankruptcy": "mdi-currency-usd-off",
    "investment": "mdi-chart-line",
    "donation": "mdi-hand-coin",

    # Health & Medical
    "illness": "mdi-hospital",
    "recovery": "mdi-heart-pulse",
    "surgery": "mdi-hospital",

    # Communication & Media
    "broadcast": "mdi-radio",
    "interview": "mdi-microphone",
    "documentary": "mdi-video",
    "film": "mdi-movie",

    # Default fallback
    "default": "mdi-calendar",
}


def format_icon_categories_for_prompt() -> str:
    """
    Format icon categories as a readable list for AI prompt.

    Returns:
        Formatted string with category → icon mappings
    """
    lines = ["Available event type icons (MDI identifiers):"]
    lines.append("")
    lines.append(
        "Copy an identifier from the left of each line EXACTLY as written. The "
        "words in parentheses are only hints about when an icon fits — they are "
        "NOT icon names. Never invent an identifier and never turn a hint into "
        'one (there is no "mdi-lecture"; the icon for a lecture is '
        '"mdi-school-outline").'
    )
    lines.append("")

    # Group by category for readability
    categories = {
        "Life Milestones": ["birth", "death", "marriage", "engagement", "divorce"],
        "Education & Academic": ["education_start", "enrollment", "graduation", "degree", "scholarship", "thesis", "dissertation", "lecture", "professorship"],
        "Professional": ["appointment", "employment", "promotion", "resignation", "retirement"],
        "Awards": ["award", "prize", "honor", "knighthood", "fellowship"],
        "Publications": ["publication", "paper", "article", "book", "patent"],
        "Creative Work": ["artwork", "painting", "sculpture", "composition", "performance"],
        "Political & Military": ["coronation", "enthronement", "title_grant", "succession", "battle", "war", "military_service", "treaty", "alliance", "peace", "conquest", "rebellion"],
        "Religious": ["consecration", "ordination", "religious_event", "canonization", "pilgrimage", "monastery", "diocese"],
        "Construction": ["building_construction", "foundation", "castle", "cathedral", "monument", "design"],
        "Travel": ["travel", "journey", "expedition", "exploration", "migration", "relocation", "exile"],
        "Scientific": ["discovery", "invention", "experiment", "research", "observation", "conference", "symposium"],
        "Legal": ["trial", "court_case", "arrest", "imprisonment", "pardon", "election", "legislation"],
        "Social": ["meeting", "collaboration", "correspondence", "debate", "speech"],
        "Financial": ["inheritance", "bankruptcy", "investment", "donation"],
        "Health": ["illness", "recovery", "surgery"],
        "Media": ["broadcast", "interview", "documentary", "film"],
    }

    for category_name, keywords in categories.items():
        lines.append(f"{category_name}:")
        # Several keywords share one icon, so list each icon once with all of
        # its hints instead of repeating the icon per keyword.
        hints_by_icon: Dict[str, List[str]] = {}
        for keyword in keywords:
            icon = ICON_CATEGORIES.get(keyword, ICON_CATEGORIES["default"])
            hints_by_icon.setdefault(icon, []).append(keyword)
        for icon, hints in hints_by_icon.items():
            lines.append(f"  - {icon}  ({', '.join(hints)})")
        lines.append("")

    lines.append(f"Default (if uncertain): {ICON_CATEGORIES['default']}")

    return "\n".join(lines)


def get_icon_for_event_type(event_type: str) -> str:
    """
    Get MDI icon for a given event type.

    Args:
        event_type: Event type keyword (e.g., "birth", "graduation")

    Returns:
        MDI icon identifier (e.g., "mdi-candle")
    """
    return ICON_CATEGORIES.get(event_type.lower(), ICON_CATEGORIES["default"])


# Every icon this project may emit. Each one is a real @mdi/js export;
# vite.config.js re-verifies that at build time and warns on any that is not.
VALID_ICONS = frozenset(ICON_CATEGORIES.values())

# Names from earlier versions of this file that are not real MDI icons, kept so
# that data generated against the old vocabulary still normalizes cleanly.
RETIRED_ICONS = {
    "mdi-teach": "mdi-school-outline",
    "mdi-home-move": "mdi-home-switch-outline",
    "mdi-monument": "mdi-pillar",
}


def normalize_icon(raw: Optional[str]) -> str:
    """
    Rewrite a model-supplied icon name that is known to name no real icon.

    The model is shown category keywords alongside their icons, and regularly
    returns the keyword with an "mdi-" prefix ("mdi-lecture") instead of the
    icon the keyword maps to ("mdi-school-outline"). Such names render nothing,
    so resolve them here rather than writing them to disk.

    Only names provably wrong are rewritten. MDI ships ~7,400 icons and this
    module knows 68 of them, so an unrecognized "mdi-" name is far more likely
    to be a real icon the model reached for beyond this vocabulary (mdi-airplane,
    mdi-tractor) than a hallucination. Those are passed through untouched: the
    UI renders any real icon, and vite.config.js warns at build time about names
    that turn out not to exist. Downgrading them here would silently replace
    working icons with generic calendars.

    Args:
        raw: Whatever the model produced, or None.

    Returns:
        An icon identifier. Guaranteed real only for names this module knows.
    """
    if not isinstance(raw, str):
        return ICON_CATEGORIES["default"]

    name = raw.strip().lower()
    if not name:
        return ICON_CATEGORIES["default"]

    if name in VALID_ICONS:
        return name
    if name in RETIRED_ICONS:
        return RETIRED_ICONS[name]

    # "mdi-lecture" -> "lecture" -> "mdi-school-outline"; also accepts a bare
    # keyword ("lecture"), which the model occasionally returns unprefixed.
    keyword = name[4:] if name.startswith("mdi-") else name
    if keyword in ICON_CATEGORIES:
        return ICON_CATEGORIES[keyword]

    # Unknown but icon-shaped: assume a real icon outside this vocabulary.
    if name.startswith("mdi-"):
        return name

    return ICON_CATEGORIES["default"]

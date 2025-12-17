#!/usr/bin/env python3
"""Icon category mappings for event type visualization using Material Design Icons (MDI)."""

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
    "lecture": "mdi-teach",
    "professorship": "mdi-teach",

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
    "monument": "mdi-monument",
    "design": "mdi-drawing",

    # Travel & Movement
    "travel": "mdi-map-marker",
    "journey": "mdi-map-marker",
    "expedition": "mdi-compass",
    "exploration": "mdi-compass",
    "migration": "mdi-airplane",
    "relocation": "mdi-home-move",
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
        for keyword in keywords:
            icon = ICON_CATEGORIES.get(keyword, "mdi-calendar")
            lines.append(f"  - {keyword}: {icon}")
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

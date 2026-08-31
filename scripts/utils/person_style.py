#!/usr/bin/env python3
"""The style a person's story is dressed in, for the steps that draw in it.

The portrait and the chapter illustrations are drawn in the story's own primary
and secondary color, which makes both of them downstream of
`generate_person_style.py` rather than beside it. Each image script used to read
`person_styles.json` through a copy of the same loader, and both copies answered
a missing entry with a hardcoded cyan and violet: the images came back in a
palette no story uses, were cached under the person's name, and nothing in the
run said the style had been missing. This is the one reader, and it answers a
missing style with an exception rather than a default, because an image drawn in
the wrong colors outlives the run that drew it.

The style generators write through here too, so what counts as a color is
decided once for the file both the writers and the readers share.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional, TypeGuard

from config import DATA_DIR

STYLES_PATH = DATA_DIR / "person_styles.json"


class MissingStyleError(RuntimeError):
    """A person whose story has no generated style to draw in."""


def is_hex_color(value: Any) -> TypeGuard[str]:
    """True if value is a "#RRGGBB" string.

    Declared as a TypeGuard because callers rely on it to narrow: they pull
    values out of an untyped payload and reject anything this returns False
    for, after which the value is known to be a str.
    """
    if not isinstance(value, str):
        return False
    return bool(re.fullmatch(r"#[0-9a-fA-F]{6}", value.strip()))


def load_style(person_id: str) -> Optional[Dict[str, Any]]:
    """The person's style entry, or None when the file holds none for them."""
    try:
        data = json.loads(STYLES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    styles = data.get("styles") if isinstance(data, dict) else None
    style = styles.get(person_id) if isinstance(styles, dict) else None
    return style if isinstance(style, dict) else None


def has_style(person_id: str) -> bool:
    """Whether an image for this person could be drawn in the story's colors."""
    try:
        story_colors(person_id)
    except MissingStyleError:
        return False
    return True


def story_colors(person_id: str) -> Dict[str, str]:
    """The primary and secondary color every image for this person is drawn in.

    Raises `MissingStyleError` when the style step has not run for this person,
    or ran and left colors that are not colors. The caller reports that as the
    unmet dependency it is; it must not draw anything.
    """
    style = load_style(person_id)
    if style is None:
        raise MissingStyleError(
            f"No interface style for '{person_id}' in {STYLES_PATH.name}. "
            f"Run 'python scripts/generate_person_style.py {person_id}' first — "
            "the images are drawn in the style's primary and secondary color."
        )
    colors = {key: style.get(key) for key in ("primary", "secondary")}
    unusable = sorted(key for key, value in colors.items() if not is_hex_color(value))
    if unusable:
        raise MissingStyleError(
            f"The interface style for '{person_id}' carries no usable "
            f"{' and '.join(unusable)} color. Regenerate it with "
            f"'python scripts/generate_person_style.py {person_id}'."
        )
    return {
        "primary": str(colors["primary"]).strip().upper(),
        "secondary": str(colors["secondary"]).strip().upper(),
    }

#!/usr/bin/env python3
"""
Repair event_type_icon values that do not name a real MDI icon.

Generation showed the model category keywords next to their icons, and it often
returned the keyword with an "mdi-" prefix ("mdi-lecture") rather than the icon
the keyword maps to ("mdi-school-outline"). Those names resolve to nothing, so
the affected events render with no icon at all.

normalize_icon() in icon_categories.py now runs during generation, so new data
cannot pick up these values. This script repairs data written before that.

Values are rewritten in place with a targeted text substitution rather than a
JSON round-trip: these files are excluded from prettier and use CRLF endings,
which json.dump would silently rewrite across every line.

Usage:
    python scripts/fix_event_icons.py --dry-run
    python scripts/fix_event_icons.py
    python scripts/fix_event_icons.py alan_turing ada_lovelace
"""

import argparse
import io
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from icon_categories import normalize_icon

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "people"

# Captures the value of an event_type_icon field, leaving surrounding bytes alone.
ICON_FIELD = re.compile(r'("event_type_icon"\s*:\s*")([^"]*)(")')


def find_event_files(person_ids: List[str]) -> List[Path]:
    """Every life_events.json, including translations, optionally filtered."""
    files = [
        path
        for path in sorted(DATA_DIR.glob("*/**/life_events.json"))
        if "_cache" not in path.parts
    ]
    if person_ids:
        wanted = set(person_ids)
        files = [f for f in files if _person_id_of(f) in wanted]
    return files


def _person_id_of(path: Path) -> str:
    """data/people/<person_id>/[lang/]life_events.json -> <person_id>"""
    return path.relative_to(DATA_DIR).parts[0]


def plan_fixes(text: str) -> Dict[str, str]:
    """Map each icon value in this file that needs rewriting to its replacement."""
    fixes = {}
    for match in ICON_FIELD.finditer(text):
        current = match.group(2)
        replacement = normalize_icon(current)
        if replacement != current:
            fixes[current] = replacement
    return fixes


def apply_fixes(text: str) -> Tuple[str, Dict[str, str]]:
    """Rewrite every event_type_icon value that does not name a real icon."""
    fixes = plan_fixes(text)
    if not fixes:
        return text, fixes

    def substitute(match: "re.Match[str]") -> str:
        return match.group(1) + normalize_icon(match.group(2)) + match.group(3)

    return ICON_FIELD.sub(substitute, text), fixes


def process(path: Path, dry_run: bool) -> Dict[str, int]:
    """Repair one file. Returns a count per replacement, e.g. {"a -> b": 3}."""
    original = path.read_text(encoding="utf-8")
    json.loads(original)  # Refuse to touch a file that is already broken.

    updated, fixes = apply_fixes(original)
    if not fixes:
        return {}

    # Parsing the result guarantees the substitution did not corrupt the file.
    reparsed = json.loads(updated)
    for event in reparsed.get("events", []):
        icon = event.get("event_type_icon")
        if icon is not None and normalize_icon(icon) != icon:
            raise RuntimeError(f"{path}: {icon!r} survived normalization")

    if not dry_run:
        # newline="" keeps the CRLF endings already in the text as-is.
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(updated)

    counts = {}
    for old, new in fixes.items():
        pattern = rf'"event_type_icon"\s*:\s*"{re.escape(old)}"'
        counts[f"{old} -> {new}"] = len(re.findall(pattern, original))
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Repair event_type_icon values that name no real MDI icon."
    )
    parser.add_argument(
        "person_ids",
        nargs="*",
        help="Person IDs to repair (default: every person)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing",
    )
    args = parser.parse_args()

    files = find_event_files(args.person_ids)
    if not files:
        print("No life_events.json found for the given person(s).")
        return 1

    totals: Dict[str, int] = {}
    changed_files = 0
    for path in files:
        counts = process(path, args.dry_run)
        if not counts:
            continue
        changed_files += 1
        rel = path.relative_to(DATA_DIR)
        print(f"{'Would fix' if args.dry_run else 'Fixed'} {rel}")
        for label, count in sorted(counts.items()):
            print(f"    {label}  ({count}x)")
            totals[label] = totals.get(label, 0) + count

    print()
    print(f"Scanned {len(files)} file(s); {changed_files} needed repair.")
    if totals:
        events = sum(totals.values())
        print(f"{events} event(s) across {len(totals)} distinct value(s):")
        for label, count in sorted(totals.items(), key=lambda kv: -kv[1]):
            print(f"  {count:4d}x  {label}")
    if args.dry_run and totals:
        print("\nDry run - nothing written. Re-run without --dry-run to apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

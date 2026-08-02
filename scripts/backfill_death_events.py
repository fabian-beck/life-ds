#!/usr/bin/env python3
"""Backfill the ``death`` classification into existing life-event datasets.

New datasets get the classification from Phase 1 of ``generate_person_events.py``,
which reads the article and can research a cause the events do not mention.
Datasets generated before the classification existed are repaired here instead
of being regenerated. The death event is detected deterministically (the same
``find_death_event_index`` the generator uses); the cause, the circumstances,
and the resting place are read out of the event the dataset already holds, by
one small model call per person that is **only allowed to quote what that text
says** — it may not add a cause from its own knowledge, because a cause nobody
wrote down is exactly the kind of plausible detail that should not enter the
corpus unsourced. Deaths whose event does not name a cause simply get none;
regenerating that person is what researches one.

``event_class`` is technical rather than prose — the translator never sees it —
so the same block is written to the English file and to every translated copy
under ``data/people/{person_id}/{lang}/``.

Usage:
    python scripts/backfill_death_events.py                  # every person
    python scripts/backfill_death_events.py niels_bohr
    python scripts/backfill_death_events.py --dry-run
    python scripts/backfill_death_events.py --skip-cause     # classify only, no AI
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from openai import OpenAI

from config import BULK_MODEL, LOW_REASONING_EFFORT, enable_utf8_console
from generate_person_events import (
    DATA_DIR,
    PEOPLE_DIR,
    DeathClassification,
    find_death_event_index,
)

enable_utf8_console()

# ``[[term|display]]`` annotation markers are an interface detail; the model
# reads the sentence, not the markup.
_MARKER = re.compile(r"\[\[[^\[\]|]+\|([^\[\]]+)\]\]")

EXTRACTION_SYSTEM = (
    "You extract facts that a given text states. You never add facts from your own "
    "knowledge, and you leave a field empty rather than guess at it."
)


def _load(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return cast(Dict[str, Any], json.load(f))


def _save(path: Path, data: Dict[str, Any]) -> None:
    # Match the generator's formatting (indent=2, unicode preserved, no CRLF).
    with open(path, "w", encoding="utf-8", newline="") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _person_ids() -> List[str]:
    return sorted(
        p.name for p in PEOPLE_DIR.iterdir() if (p / "life_events.json").exists()
    )


def _event_files(person_id: str) -> List[Path]:
    """The English life events file plus every translated copy."""
    files = []
    english = PEOPLE_DIR / person_id / "life_events.json"
    if english.exists():
        files.append(english)
    for lang_dir in sorted((PEOPLE_DIR / person_id).iterdir()):
        if lang_dir.is_dir() and not lang_dir.name.startswith("_"):
            translated = lang_dir / "life_events.json"
            if translated.exists():
                files.append(translated)
    return files


def build_extraction_prompt(person_name: str, event: Dict[str, Any]) -> str:
    """The one thing the model is shown: the death event as the dataset holds it."""
    description = _MARKER.sub(r"\1", event.get("description") or "")
    prompt = f"PERSON: {person_name}\n"
    prompt += f"DEATH EVENT ({event.get('date')}): {event.get('title')}\n"
    prompt += f"{description}\n"
    if event.get("date_note"):
        prompt += f"Date note: {event['date_note']}\n"
    prompt += (
        "\nFrom THIS TEXT ONLY, extract:\n"
        "- cause: the cause of death the text gives, as a noun phrase of 1-6 words "
        "('heart failure', 'cyanide poisoning', 'gunshot wound from a duel'). Drop "
        "pronouns and hedging words the sentence needed but the label does not: "
        "'his wound' becomes 'gunshot wound', 'complications related to his pancreatic "
        "tumor' becomes 'pancreatic tumor'. Leave it empty when the text does not say "
        "what the person died of — old age, a place, or a date is not a cause.\n"
        "- characterization: 1-4 words on the circumstances the text describes "
        "('after long illness', 'ruled a suicide', 'in exile'). Leave empty when the "
        "text says nothing about them.\n"
        "- place_of_rest: the burial or resting place, only if the text names one.\n"
        "\nDo not use anything you know about this person beyond the text above."
    )
    return prompt


def extract_death_facts(
    person_name: str, event: Dict[str, Any], model: str
) -> Optional[DeathClassification]:
    """One small call per person; a failure costs the cause, not the run."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("    ⚠ OPENAI_API_KEY is not set — classifying without a cause")
        return None

    try:
        response = OpenAI(api_key=api_key).responses.parse(
            model=model,
            reasoning=cast(Any, {"effort": LOW_REASONING_EFFORT}),
            input=[
                {"role": "system", "content": EXTRACTION_SYSTEM},
                {
                    "role": "user",
                    "content": build_extraction_prompt(person_name, event),
                },
            ],
            text_format=DeathClassification,
        )
    except Exception as error:  # noqa: BLE001 - non-fatal by design
        print(f"    ⚠ Extraction failed ({type(error).__name__}: {error})")
        return None

    if response.status != "completed" or response.output_parsed is None:
        print(f"    ⚠ Extraction returned no result (status: {response.status})")
        return None
    return response.output_parsed


def build_death_class(
    existing: Optional[Dict[str, Any]], extracted: Optional[DeathClassification]
) -> Dict[str, Any]:
    """The death classification to store, keeping whatever is already there.

    A regenerated dataset may already hold a researched cause the event text
    never stated, so stored values win over extracted ones.
    """
    death_class: Dict[str, Any] = {"type": "death"}
    if isinstance(existing, dict) and existing.get("type") == "death":
        death_class.update({k: v for k, v in existing.items() if v is not None})
    if extracted:
        for field, value in extracted.model_dump(exclude_none=True).items():
            if field != "type" and str(value).strip():
                death_class.setdefault(field, value)
    return death_class


def backfill_person(
    person_id: str, model: str, skip_cause: bool, dry_run: bool
) -> bool:
    """Classify one person's death event. Returns True when something changed."""
    english_path = PEOPLE_DIR / person_id / "life_events.json"
    if not english_path.exists():
        print(f"  ⚠ Skipping unknown person: {person_id}")
        return False

    english = _load(english_path)
    events = english.get("events") or []
    person = english.get("person") or {}
    index = find_death_event_index(events, person.get("death_date"))
    if index is None:
        print(f"{person_id}: no death event found — left unchanged")
        return False

    existing = events[index].get("event_class")
    extracted = None
    if not skip_cause and not (
        isinstance(existing, dict) and existing.get("type") == "death"
    ):
        extracted = extract_death_facts(
            person.get("name") or person_id, events[index], model
        )
    death_class = build_death_class(existing, extracted)

    print(
        f"{person_id}: event {index} '{events[index].get('title')}' "
        f"→ death ({death_class.get('cause') or 'cause undocumented'})"
    )

    changed = False
    for path in _event_files(person_id):
        data = _load(path)
        file_events = data.get("events") or []
        if len(file_events) != len(events):
            print(
                f"    ⚠ {path.relative_to(DATA_DIR)}: {len(file_events)} events, "
                f"English has {len(events)} — skipped, re-translate first"
            )
            continue

        before = json.dumps(
            [event.get("event_class") for event in file_events], sort_keys=True
        )
        for position, event in enumerate(file_events):
            if position == index:
                event["event_class"] = json.loads(json.dumps(death_class))
            elif (event.get("event_class") or {}).get("type") == "death":
                # A death class on any other event is a misclassification —
                # the story has exactly one death, the subject's own.
                event.pop("event_class")
        after = json.dumps(
            [event.get("event_class") for event in file_events], sort_keys=True
        )
        if before == after:
            print(f"    = {path.relative_to(DATA_DIR)} (already current)")
            continue

        changed = True
        if dry_run:
            print(f"    [dry-run] would update {path.relative_to(DATA_DIR)}")
        else:
            _save(path, data)
            print(f"    ✓ {path.relative_to(DATA_DIR)}")

    return changed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill the death classification into life event datasets"
    )
    parser.add_argument(
        "person_ids",
        nargs="*",
        help="Specific person IDs (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing",
    )
    parser.add_argument(
        "--skip-cause",
        action="store_true",
        help="Only classify the event, without the model call that reads the cause",
    )
    parser.add_argument(
        "--model",
        default=BULK_MODEL,
        help=f"Model for the cause extraction (default: {BULK_MODEL})",
    )
    args = parser.parse_args()

    person_ids = args.person_ids or _person_ids()
    updated = sum(
        backfill_person(person_id, args.model, args.skip_cause, args.dry_run)
        for person_id in person_ids
    )
    print(f"\n{updated} of {len(person_ids)} person(s) changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

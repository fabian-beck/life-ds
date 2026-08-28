#!/usr/bin/env python3
"""Stage one: extract the claims a person's story makes.

One call per unit of the dataset — the registry entry, the chapter frame, the
conclusion, each event, and the ego network — each asked for every assertion its
slice makes, and nothing beyond it. The output is a fact file per person under
``evaluation/out/facts/``.

Two things are checked afterwards without a model. Every claim's ``source_text``
is looked for in the unit it was extracted from, so a claim whose provenance was
invented is marked rather than trusted; and claims that fold to the same wording
within a unit are dropped, because the same assertion twice would let one error
count twice in the results.

Usage:
    python -m evaluation.factcheck.extract_facts alan_turing ada_lovelace
    python -m evaluation.factcheck.extract_facts --all --workers 6
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import ExtractionOutput
from .paths import FACTS_DIR, ensure_out_dirs
from .prompts import EXTRACTION_SYSTEM, extraction_prompt
from .text import collapse, fact_id, fold, provenance_haystack
from .units import (
    PersonStory,
    Unit,
    build_units,
    load_person_story,
    person_ids_with_stories,
    unit_summary,
)

from config import (
    DEFAULT_MODEL,
    DEFAULT_REASONING_EFFORT,
    enable_utf8_console,
)  # noqa: E402
from utils.model_calls import MissingApiKey, get_client, parse_structured  # noqa: E402

SCHEMA = "life-ds-factcheck-facts/1"


def extract_unit(
    story: PersonStory,
    unit: Unit,
    *,
    model: str,
    reasoning_effort: str,
) -> List[Dict[str, Any]]:
    """The claims one unit makes, as fact records."""
    parsed = parse_structured(
        get_client(),
        model=model,
        reasoning_effort=reasoning_effort,
        input=[
            {"role": "system", "content": EXTRACTION_SYSTEM},
            {
                "role": "user",
                "content": extraction_prompt(
                    story.person_name, unit.label, unit.scope, unit.as_prompt_text()
                ),
            },
        ],
        text_format=ExtractionOutput,
        label=f"Fact extraction ({story.person_id} {unit.id})",
    )
    if parsed is None:
        return []

    haystack = provenance_haystack(unit.payload, unit.as_prompt_text())
    facts: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for claim in parsed.claims:
        text = claim.claim.strip()
        if not text:
            continue
        key = fold(text).lower()
        if key in seen:
            continue
        seen.add(key)
        quoted = fold(claim.source_text)
        facts.append(
            {
                "id": fact_id(story.person_id, unit.id, text),
                "person_id": story.person_id,
                "person_name": story.person_name,
                "unit_id": unit.id,
                "scope": unit.scope,
                "unit_label": unit.label,
                "claim": text,
                "claim_type": claim.claim_type,
                "checkable": bool(claim.checkable),
                "source_field": claim.source_field,
                "source_text": claim.source_text,
                "source_text_found": bool(quoted) and quoted in haystack,
                "context": unit.context,
            }
        )
    return facts


def extract_person(
    person_id: str,
    *,
    model: str,
    reasoning_effort: str,
    workers: int,
) -> Dict[str, Any]:
    """Every claim one person's story makes, as a fact file payload."""
    story = load_person_story(person_id)
    units = build_units(story)
    print(f"{person_id}: {len(units)} units ({unit_summary(units)})")

    def run(unit: Unit) -> Tuple[Unit, List[Dict[str, Any]]]:
        return unit, extract_unit(
            story, unit, model=model, reasoning_effort=reasoning_effort
        )

    results: List[Tuple[Unit, List[Dict[str, Any]]]]
    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(run, units))
    else:
        results = [run(unit) for unit in units]

    facts: List[Dict[str, Any]] = []
    for unit, extracted in results:
        print(f"  {unit.id:<12} {len(extracted):>3} claims  {collapse(unit.label, 60)}")
        facts.extend(extracted)

    unverified = sum(1 for fact in facts if not fact["source_text_found"])
    if unverified:
        print(
            f"  note: {unverified} of {len(facts)} claims quote source text that is "
            "not in the dataset verbatim"
        )

    return {
        "schema": SCHEMA,
        "person_id": story.person_id,
        "person_name": story.person_name,
        "dataset_fingerprint": story.fingerprint,
        "extracted_on": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": model,
        "reasoning_effort": reasoning_effort,
        "unit_count": len(units),
        "facts": facts,
    }


def write_facts(payload: Dict[str, Any], out_dir: Path) -> Path:
    """Write one person's fact file."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{payload['person_id']}.json"
    with open(path, "w", encoding="utf-8", newline="") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return path


def resolve_person_ids(requested: List[str], use_all: bool) -> List[str]:
    """The people to extract, checked against what exists."""
    available = person_ids_with_stories()
    if use_all:
        return available
    unknown = [person_id for person_id in requested if person_id not in available]
    if unknown:
        raise SystemExit(
            f"Unknown person id(s): {', '.join(unknown)}. "
            f"{len(available)} datasets exist under data/people/."
        )
    return requested


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract the factual claims a person story makes."
    )
    parser.add_argument("person_ids", nargs="*", help="Person ids, e.g. alan_turing.")
    parser.add_argument(
        "--all", action="store_true", help="Extract every person with a dataset."
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"({DEFAULT_MODEL})")
    parser.add_argument(
        "--reasoning-effort",
        default=DEFAULT_REASONING_EFFORT,
        help=f"({DEFAULT_REASONING_EFFORT})",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Units extracted in parallel per person (default: 4).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=FACTS_DIR,
        help="Where fact files are written (default: evaluation/out/facts).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-extract people whose fact file already exists.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    enable_utf8_console()
    args = parse_args(argv)
    if not args.person_ids and not args.all:
        print("Name at least one person id, or pass --all.", file=sys.stderr)
        return 2

    ensure_out_dirs()
    person_ids = resolve_person_ids(args.person_ids, args.all)

    try:
        get_client()
    except MissingApiKey as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    total = 0
    for person_id in person_ids:
        target = args.out_dir / f"{person_id}.json"
        if target.exists() and not args.force:
            print(f"{person_id}: fact file exists, skipping (--force to redo)")
            continue
        payload = extract_person(
            person_id,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            workers=max(1, args.workers),
        )
        path = write_facts(payload, args.out_dir)
        total += len(payload["facts"])
        print(f"{person_id}: {len(payload['facts'])} facts -> {path}")

    print(f"Extracted {total} facts from {len(person_ids)} person stories.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

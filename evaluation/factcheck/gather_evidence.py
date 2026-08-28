#!/usr/bin/env python3
"""Stage two: research a random sample of facts in the source materials.

Draws a reproducible sample from the fact files stage one wrote, and for each
fact searches the person's cached Wikipedia materials for passages that support
or contradict it. Every quote the model returns is then looked for in the source
text; a quote that is not there is kept and marked, because a fabricated quote
is a result of the evaluation rather than an accident to be swallowed.

The output is one bundle file, which is what the evaluator page loads.

Usage:
    python -m evaluation.factcheck.gather_evidence --sample 40 --seed 7 \
        --name round-1 alan_turing ada_lovelace
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .evidence import (
    DEFAULT_BUDGET,
    DEFAULT_MAX_EXCERPTS,
    MaterialIndex,
    build_input,
    search_query,
    verify_quotes,
)
from .materials import MaterialsMissing, describe, require_materials
from .models import EvidenceOutput
from .paths import BUNDLES_DIR, FACTS_DIR, ensure_out_dirs
from .sampling import stratified_sample
from .text import collapse, digest
from .units import display_name

from config import (
    DEFAULT_MODEL,
    DEFAULT_REASONING_EFFORT,
    enable_utf8_console,
)  # noqa: E402
from utils.model_calls import MissingApiKey, get_client, parse_structured  # noqa: E402

SCHEMA = "life-ds-factcheck-bundle/1"
DEFAULT_APP_URL = "http://localhost:5173/"


def load_fact_files(
    facts_dir: Path, person_ids: List[str]
) -> Dict[str, Dict[str, Any]]:
    """The fact files to sample from, keyed by person id."""
    if person_ids:
        paths = [facts_dir / f"{person_id}.json" for person_id in person_ids]
        missing = [path for path in paths if not path.exists()]
        if missing:
            raise SystemExit(
                "No fact file for: "
                + ", ".join(path.stem for path in missing)
                + ". Run extract_facts.py for them first."
            )
    else:
        paths = sorted(facts_dir.glob("*.json"))
        if not paths:
            raise SystemExit(
                f"No fact files in {facts_dir}. Run extract_facts.py first."
            )

    files: Dict[str, Dict[str, Any]] = {}
    for path in paths:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        files[payload["person_id"]] = payload
    return files


def story_link(app_url: str, fact: Dict[str, Any]) -> str:
    """A deep link to the slide the claim is on, for the evaluator page."""
    context = fact.get("context") or {}
    base = app_url.rstrip("/") + "/"
    href = f"{base}#/en/story/{fact['person_id']}"
    index = context.get("event_index")
    if isinstance(index, int):
        href += f"?event={index}"
    return href


def research_fact(
    fact: Dict[str, Any],
    index: MaterialIndex,
    *,
    model: str,
    reasoning_effort: str,
    budget: int,
    max_excerpts: int,
) -> Dict[str, Any]:
    """The evidence record for one fact."""
    chunks = index.select(search_query(fact), budget=budget, max_excerpts=max_excerpts)
    excerpts = index.excerpt_payload(chunks)

    parsed = parse_structured(
        get_client(),
        model=model,
        reasoning_effort=reasoning_effort,
        input=build_input(str(fact.get("person_name") or ""), fact, excerpts),
        text_format=EvidenceOutput,
        label=f"Evidence search ({fact['id']})",
    )
    if parsed is None:
        return {
            "status": "error",
            "notes": "The evidence call returned nothing usable.",
            "quotes": [],
            "excerpts_searched": len(excerpts),
            "materials_searched": sorted({chunk.material_id for chunk in chunks}),
        }

    quotes = verify_quotes(index, parsed, [excerpt["id"] for excerpt in excerpts])
    return {
        "status": parsed.status,
        "notes": parsed.notes,
        "quotes": quotes,
        "excerpts_searched": len(excerpts),
        "characters_searched": sum(len(excerpt["text"]) for excerpt in excerpts),
        "materials_searched": sorted({chunk.material_id for chunk in chunks}),
    }


def build_bundle(
    *,
    name: str,
    sample: List[Dict[str, Any]],
    fact_files: Dict[str, Dict[str, Any]],
    seed: int,
    sample_size: int,
    checkable_only: bool,
    model: str,
    reasoning_effort: str,
    budget: int,
    max_excerpts: int,
    workers: int,
    app_url: str,
) -> Dict[str, Any]:
    """Research every sampled fact and assemble the evaluation bundle."""
    persons: Dict[str, Dict[str, Any]] = {}
    indexes: Dict[str, MaterialIndex] = {}
    for person_id in sorted({fact["person_id"] for fact in sample}):
        materials = require_materials(person_id)
        print(f"{person_id}: {describe(materials)}")
        indexes[person_id] = MaterialIndex(materials)
        source = fact_files[person_id]
        persons[person_id] = {
            "id": person_id,
            "name": source.get("person_name") or display_name({}, person_id),
            "dataset_fingerprint": source.get("dataset_fingerprint"),
            "extracted_on": source.get("extracted_on"),
            "extraction_model": source.get("model"),
            "fact_count": len(source.get("facts") or []),
            "materials": [material.as_index_entry() for material in materials],
        }

    def run(fact: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        return fact, research_fact(
            fact,
            indexes[fact["person_id"]],
            model=model,
            reasoning_effort=reasoning_effort,
            budget=budget,
            max_excerpts=max_excerpts,
        )

    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            researched = list(pool.map(run, sample))
    else:
        researched = [run(fact) for fact in sample]

    items: List[Dict[str, Any]] = []
    for fact, evidence in researched:
        item = dict(fact)
        item["evidence"] = evidence
        item["story_link"] = story_link(app_url, fact)
        items.append(item)
        verified = sum(1 for quote in evidence["quotes"] if quote["verified"])
        print(
            f"  {fact['id']:<26} {evidence['status']:<12} "
            f"{verified}/{len(evidence['quotes'])} quotes verified  "
            f"{collapse(fact['claim'], 70)}"
        )

    items.sort(key=lambda item: item["id"])
    population = {
        person_id: len(payload.get("facts") or [])
        for person_id, payload in sorted(fact_files.items())
    }

    return {
        "schema": SCHEMA,
        "bundle_id": digest(name, str(seed), *[item["id"] for item in items]),
        "name": name,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": seed,
        "requested_sample": sample_size,
        "checkable_only": checkable_only,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "excerpt_budget": budget,
        "max_excerpts": max_excerpts,
        "app_url": app_url,
        "population": {
            "facts_total": sum(population.values()),
            "per_person": population,
        },
        "persons": persons,
        "items": items,
    }


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sample facts and research supporting evidence for them."
    )
    parser.add_argument(
        "person_ids",
        nargs="*",
        help="People to sample from (default: every fact file present).",
    )
    parser.add_argument(
        "--sample", type=int, default=30, help="How many facts to check (default: 30)."
    )
    parser.add_argument(
        "--seed", type=int, default=1, help="Sampling seed (default: 1)."
    )
    parser.add_argument(
        "--name", help="Bundle name (default: derived from the sample)."
    )
    parser.add_argument(
        "--checkable-only",
        action="store_true",
        help="Exclude claims stage one marked as interpretation rather than fact.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"({DEFAULT_MODEL})")
    parser.add_argument(
        "--reasoning-effort",
        default=DEFAULT_REASONING_EFFORT,
        help=f"({DEFAULT_REASONING_EFFORT})",
    )
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET)
    parser.add_argument("--max-excerpts", type=int, default=DEFAULT_MAX_EXCERPTS)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--facts-dir", type=Path, default=FACTS_DIR)
    parser.add_argument("--out-dir", type=Path, default=BUNDLES_DIR)
    parser.add_argument(
        "--app-url",
        default=DEFAULT_APP_URL,
        help=f"Base URL the story links point at (default: {DEFAULT_APP_URL}).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    enable_utf8_console()
    args = parse_args(argv)
    ensure_out_dirs()

    fact_files = load_fact_files(args.facts_dir, args.person_ids)
    facts_by_person = {
        person_id: [
            fact
            for fact in payload.get("facts") or []
            if fact.get("checkable", True) or not args.checkable_only
        ]
        for person_id, payload in fact_files.items()
    }
    available = sum(len(facts) for facts in facts_by_person.values())
    if available == 0:
        print("No facts to sample from.", file=sys.stderr)
        return 1

    sample = stratified_sample(facts_by_person, args.sample, args.seed)
    print(
        f"Sampled {len(sample)} of {available} facts "
        f"from {len(facts_by_person)} people (seed {args.seed})."
    )

    try:
        get_client()
    except MissingApiKey as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    name = args.name or f"sample-{len(sample)}-seed-{args.seed}"
    try:
        bundle = build_bundle(
            name=name,
            sample=sample,
            fact_files=fact_files,
            seed=args.seed,
            sample_size=args.sample,
            checkable_only=args.checkable_only,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            budget=args.budget,
            max_excerpts=args.max_excerpts,
            workers=max(1, args.workers),
            app_url=args.app_url,
        )
    except MaterialsMissing as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / f"{name}.json"
    with open(path, "w", encoding="utf-8", newline="") as handle:
        json.dump(bundle, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    quotes = [quote for item in bundle["items"] for quote in item["evidence"]["quotes"]]
    verified = sum(1 for quote in quotes if quote["verified"])
    print(
        f"Bundle {bundle['bundle_id']} -> {path}\n"
        f"{len(bundle['items'])} facts, {len(quotes)} quotes, "
        f"{verified} of them found verbatim in the sources."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

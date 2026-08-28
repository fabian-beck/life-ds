#!/usr/bin/env python3
"""Stage four: merge the evaluators' result files into one report.

Each evaluator downloads a result file from the page; this joins them on the
fact id, resolves a verdict per fact, measures how far the evaluators agreed,
and writes a self-contained HTML report next to the merged data.

Result files that name a different bundle are refused rather than merged.
Judgments of the same fact id from different bundles would look joinable and
are not: the sample, the evidence, and often the extraction differ, so the
agreement between them would be a number about nothing.

Usage:
    python -m evaluation.factcheck.merge_results \
        evaluation/out/results/*.json --bundle evaluation/out/bundles/round-1.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, cast

from .agreement import (
    build_rating_table,
    collapse_to_problem,
    disagreements,
    krippendorff_alpha,
    majority,
    pairwise_agreement,
)
from .models import PROBLEM_VERDICTS
from .paths import BUNDLES_DIR, REPORTS_DIR, RESULTS_DIR, ensure_out_dirs
from .report import write_report

from config import enable_utf8_console  # noqa: E402

RESULT_SCHEMA = "life-ds-factcheck-results/1"


def read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return cast(Any, json.load(handle))


def load_results(paths: Sequence[Path]) -> List[Dict[str, Any]]:
    """Read result files, rejecting anything that is not one."""
    results = []
    for path in paths:
        payload = read_json(path)
        if payload.get("schema") != RESULT_SCHEMA:
            raise SystemExit(f"{path} is not a fact-check result file.")
        payload["_path"] = str(path)
        results.append(payload)
    return results


def check_one_bundle(
    results: Sequence[Dict[str, Any]], bundle_id: Optional[str]
) -> str:
    """Confirm every result judges the same bundle, and say which."""
    ids = {str(result["bundle_id"]) for result in results}
    if bundle_id:
        ids.add(bundle_id)
    if len(ids) > 1:
        listing = "\n".join(
            f"  {result['_path']}: {result['bundle_id']}" for result in results
        )
        raise SystemExit(
            "These result files judge different bundles, so they cannot be "
            f"merged:\n{listing}"
        )
    return str(ids.pop())


def judgments_by_evaluator(
    results: Sequence[Mapping[str, Any]],
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """``{evaluator: {fact_id: judgment}}``, keeping only decided facts.

    Two files from the same evaluator are merged, later file winning per fact:
    an evaluator who finished a round in two sittings, or re-downloaded after
    revising, should count once.
    """
    merged: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    for result in sorted(results, key=lambda payload: payload.get("updated") or ""):
        name = str(result.get("evaluator") or "anonymous")
        for judgment in result.get("judgments") or []:
            if not judgment.get("verdict"):
                continue
            merged[name][str(judgment["fact_id"])] = judgment
    return dict(merged)


def summarize(
    bundle: Mapping[str, Any], results: Sequence[Mapping[str, Any]]
) -> Dict[str, Any]:
    """Everything the report needs, computed once."""
    items = {item["id"]: item for item in bundle["items"]}
    per_evaluator = judgments_by_evaluator(results)
    verdict_by_evaluator = {
        name: {fact_id: judgment["verdict"] for fact_id, judgment in judgments.items()}
        for name, judgments in per_evaluator.items()
    }

    unknown = {
        fact_id
        for judgments in verdict_by_evaluator.values()
        for fact_id in judgments
        if fact_id not in items
    }
    if unknown:
        print(
            f"warning: {len(unknown)} judged facts are not in the bundle and are "
            "ignored (a result file from an older extraction).",
            file=sys.stderr,
        )

    fact_ids = list(items)
    table = build_rating_table(
        {
            name: {
                fact_id: verdict
                for fact_id, verdict in judgments.items()
                if fact_id in items
            }
            for name, judgments in verdict_by_evaluator.items()
        },
        fact_ids,
    )

    consensus: Dict[str, Optional[str]] = {}
    for fact_id in fact_ids:
        values = list(table.get(fact_id, {}).values())
        if not values:
            consensus[fact_id] = None
            continue
        winner, _ = majority(values)
        consensus[fact_id] = winner or "contested"

    counts = Counter(value for value in consensus.values() if value)
    by_person: Dict[str, Counter] = defaultdict(Counter)
    by_scope: Dict[str, Counter] = defaultdict(Counter)
    by_claim_type: Dict[str, Counter] = defaultdict(Counter)
    status_counts: Counter = Counter()
    status_vs_verdict: Dict[str, Counter] = defaultdict(Counter)
    quotes_total = 0
    quotes_verified = 0

    persons = bundle.get("persons") or {}
    for fact_id, item in items.items():
        evidence = item.get("evidence") or {}
        status_counts[evidence.get("status", "unknown")] += 1
        quotes = evidence.get("quotes") or []
        quotes_total += len(quotes)
        quotes_verified += sum(1 for quote in quotes if quote.get("verified"))
        verdict = consensus.get(fact_id)
        if not verdict:
            continue
        person_name = (persons.get(item["person_id"]) or {}).get(
            "name", item["person_id"]
        )
        by_person[person_name][verdict] += 1
        by_scope[item.get("scope", "unknown")][verdict] += 1
        by_claim_type[item.get("claim_type", "unknown")][verdict] += 1
        status_vs_verdict[evidence.get("status", "unknown")][verdict] += 1

    quality_counts: Counter = Counter()
    severity_counts: Counter = Counter()
    confidence_counts: Counter = Counter()
    for judgments in per_evaluator.values():
        for judgment in judgments.values():
            if judgment.get("evidence_quality"):
                quality_counts[judgment["evidence_quality"]] += 1
            if judgment.get("severity"):
                severity_counts[judgment["severity"]] += 1
            if judgment.get("confidence"):
                confidence_counts[judgment["confidence"]] += 1

    pairwise, pairs = pairwise_agreement(table)
    problem_table = {
        fact_id: {
            name: collapse_to_problem(verdict, PROBLEM_VERDICTS)
            for name, verdict in values.items()
        }
        for fact_id, values in table.items()
    }

    facts: List[Dict[str, Any]] = []
    problems: List[Dict[str, Any]] = []
    for fact_id in sorted(fact_ids, key=lambda key: items[key]["claim"]):
        item = items[fact_id]
        verdict = consensus.get(fact_id)
        notes = [
            judgment["note"].strip()
            for judgments in per_evaluator.values()
            for judgment in [judgments.get(fact_id)]
            if judgment and (judgment.get("note") or "").strip()
        ]
        severities = [
            judgments[fact_id]["severity"]
            for judgments in per_evaluator.values()
            if fact_id in judgments and judgments[fact_id].get("severity")
        ]
        entry = {
            "id": fact_id,
            "claim": item["claim"],
            "claim_type": item.get("claim_type"),
            "person": (persons.get(item["person_id"]) or {}).get(
                "name", item["person_id"]
            ),
            "unit_label": item.get("unit_label"),
            "scope": item.get("scope"),
            "evidence_status": (item.get("evidence") or {}).get("status"),
            "verdict": verdict,
            "verdicts": table.get(fact_id, {}),
            "notes": notes,
            "severity": majority(severities)[0] if severities else None,
        }
        facts.append(entry)
        if verdict in PROBLEM_VERDICTS or verdict == "contested":
            problems.append(
                dict(entry, quotes=(item.get("evidence") or {}).get("quotes") or [])
            )

    evaluators = []
    for name, judgments in sorted(per_evaluator.items()):
        times = [
            float(judgment.get("seconds") or 0)
            for judgment in judgments.values()
            if judgment.get("seconds")
        ]
        latest = max(
            (
                result.get("updated") or ""
                for result in results
                if str(result.get("evaluator") or "anonymous") == name
            ),
            default="",
        )
        evaluators.append(
            {
                "name": name,
                "judged": len(judgments),
                "median_seconds": statistics.median(times) if times else 0.0,
                "updated": latest,
            }
        )

    resolved = sum(count for verdict, count in counts.items() if verdict != "contested")

    return {
        "bundle": {
            key: bundle.get(key)
            for key in (
                "bundle_id",
                "name",
                "created",
                "seed",
                "model",
                "reasoning_effort",
                "excerpt_budget",
                "max_excerpts",
                "population",
                "persons",
            )
        },
        "coverage": {
            "facts": len(items),
            "judged_by_any": len(table),
            "judged_by_all": sum(
                1 for values in table.values() if len(values) == len(per_evaluator)
            ),
        },
        "evaluators": evaluators,
        "verdicts": {
            "consensus": dict(counts),
            "by_person": {key: dict(value) for key, value in by_person.items()},
            "by_scope": {key: dict(value) for key, value in by_scope.items()},
            "by_claim_type": {key: dict(value) for key, value in by_claim_type.items()},
        },
        "resolved_count": resolved,
        "problem_count": sum(counts.get(verdict, 0) for verdict in PROBLEM_VERDICTS),
        "agreement": {
            "pairwise": pairwise,
            "pairs": [
                {
                    "first": first,
                    "second": second,
                    "agreed": hits,
                    "compared": total,
                }
                for (first, second), (hits, total) in sorted(pairs.items())
            ],
            "alpha_full": krippendorff_alpha(table),
            "alpha_problem": krippendorff_alpha(problem_table),
        },
        "evidence": {
            "status_counts": dict(status_counts),
            "status_vs_verdict": {
                key: dict(value) for key, value in status_vs_verdict.items()
            },
            "quotes_total": quotes_total,
            "quotes_verified": quotes_verified,
            "quality_counts": dict(quality_counts),
        },
        "severity_counts": dict(severity_counts),
        "confidence_counts": dict(confidence_counts),
        "disagreements": [
            {
                "id": fact_id,
                "claim": items[fact_id]["claim"],
                "person": (persons.get(items[fact_id]["person_id"]) or {}).get(
                    "name", items[fact_id]["person_id"]
                ),
                "verdicts": values,
            }
            for fact_id, values in disagreements(table)
        ],
        "problems": problems,
        "facts": facts,
    }


def find_bundle(bundle_id: str, explicit: Optional[Path]) -> Dict[str, Any]:
    """The bundle the results judge: named on the command line, or looked up."""
    if explicit:
        bundle: Dict[str, Any] = read_json(explicit)
        if bundle.get("bundle_id") != bundle_id:
            raise SystemExit(
                f"{explicit} is bundle {bundle.get('bundle_id')}, but the results "
                f"judge {bundle_id}."
            )
        return bundle
    for path in sorted(BUNDLES_DIR.glob("*.json")):
        candidate: Dict[str, Any] = read_json(path)
        if candidate.get("bundle_id") == bundle_id:
            print(f"Using bundle {path}")
            return candidate
    raise SystemExit(
        f"No bundle with id {bundle_id} in {BUNDLES_DIR}. Name one with --bundle."
    )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge evaluator results into one HTML report."
    )
    parser.add_argument(
        "results",
        nargs="*",
        type=Path,
        help="Result files (default: every JSON in evaluation/out/results).",
    )
    parser.add_argument("--bundle", type=Path, help="The bundle the results judge.")
    parser.add_argument(
        "--out",
        type=Path,
        help="Report path (default: evaluation/out/reports/<bundle name>.html).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    enable_utf8_console()
    args = parse_args(argv)
    ensure_out_dirs()

    paths = args.results or sorted(RESULTS_DIR.glob("*.json"))
    if not paths:
        print(f"No result files given, and none in {RESULTS_DIR}.", file=sys.stderr)
        return 2

    results = load_results(paths)
    bundle_id = check_one_bundle(results, None)
    bundle = find_bundle(bundle_id, args.bundle)
    summary = summarize(bundle, results)

    out = args.out or REPORTS_DIR / f"{bundle.get('name', bundle_id)}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_report(summary, out)

    print(
        f"Merged {len(results)} result files from "
        f"{len(summary['evaluators'])} evaluators.\n"
        f"{summary['coverage']['judged_by_any']} of {summary['coverage']['facts']} "
        f"facts judged, {summary['problem_count']} with a problem.\n"
        f"Report -> {out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""The shared frame around a per-person dataset check.

Each validator contributes a predicate — person id and parsed dataset in,
findings out — and this runner supplies everything around it: the argument
parsing, the corpus walk, the ERROR lines, the closing count, and the exit
code. Three validators carried byte-identical copies of that frame before it
lived here.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Callable, Dict, List, Optional

from utils.datasets import dataset_paths
from utils.json_io import read_json


def run_dataset_check(
    check_person: Callable[[str, Dict[str, Any]], List[Any]],
    *,
    description: Optional[str],
    argv: Optional[List[str]] = None,
    report_only: bool = False,
) -> int:
    """Run a per-person check over the corpus and report its findings.

    Findings only need a ``__str__`` that names the person and the defect.
    Returns 1 when anything was found, so the scripts compose with CI. A
    ``report_only`` validator instead gains a ``--check`` flag and fails only
    under it: that is the shape for a rule the shipped corpus still breaks,
    whose count says whether a generator change worked until it reads zero.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "person_ids", nargs="*", help="Specific person ids to check (default: all)"
    )
    parser.add_argument("--verbose", action="store_true")
    if report_only:
        parser.add_argument(
            "--check", action="store_true", help="Exit 1 when anything was found"
        )
    args = parser.parse_args(argv)

    findings: List[Any] = []
    checked = 0
    for path in dataset_paths(args.person_ids):
        if not path.exists():
            print(f"warning: {path} not found", file=sys.stderr)
            continue
        person_id = path.parent.name
        data = read_json(path)
        person_findings = check_person(person_id, data)
        checked += 1
        if args.verbose and not person_findings:
            print(f"{person_id}: OK")
        findings.extend(person_findings)

    for finding in findings:
        print(f"ERROR: {finding}")

    print(f"\nChecked {checked} person dataset(s), {len(findings)} finding(s).")
    if report_only and not args.check:
        return 0
    return 1 if findings else 0

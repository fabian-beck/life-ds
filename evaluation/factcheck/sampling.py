#!/usr/bin/env python3
"""Draw the sample of facts an evaluation round checks.

A sample is worth the evaluators' time only if it is reproducible and unbiased.
Reproducible: the same fact files, size, and seed always yield the same facts,
so a round can be rebuilt after a crash and two people can be sent the identical
set. Unbiased: people are represented in proportion to how many claims their
story makes, rather than by whichever fact file happened to be read first, and
within a person every fact is equally likely.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Mapping, Sequence, Tuple


def allocate(counts: Mapping[str, int], sample_size: int) -> Dict[str, int]:
    """How many facts to draw from each person, proportional to their share.

    Largest remainder, so the allocations sum to the requested size exactly
    rather than to whatever rounding leaves. Ties in the remainder are broken by
    person id, which keeps the result independent of dictionary order.
    """
    total = sum(counts.values())
    if total <= 0 or sample_size <= 0:
        return {person_id: 0 for person_id in counts}
    if sample_size >= total:
        return dict(counts)

    exact = {
        person_id: sample_size * count / total for person_id, count in counts.items()
    }
    allocation = {person_id: int(value) for person_id, value in exact.items()}
    remaining = sample_size - sum(allocation.values())

    order: List[Tuple[float, str]] = sorted(
        (
            (-(exact[person_id] - allocation[person_id]), person_id)
            for person_id in exact
        )
    )
    for _, person_id in order:
        if remaining <= 0:
            break
        if allocation[person_id] < counts[person_id]:
            allocation[person_id] += 1
            remaining -= 1

    # A person whose share exceeded their fact count leaves places over; give
    # them to whoever still has facts, in id order, so the size is met.
    while remaining > 0:
        progressed = False
        for person_id in sorted(counts):
            if remaining <= 0:
                break
            if allocation[person_id] < counts[person_id]:
                allocation[person_id] += 1
                remaining -= 1
                progressed = True
        if not progressed:
            break
    return allocation


def stratified_sample(
    facts_by_person: Mapping[str, Sequence[Dict[str, Any]]],
    sample_size: int,
    seed: int,
) -> List[Dict[str, Any]]:
    """A reproducible sample across people, sorted by fact id.

    Each person is drawn with their own seeded generator derived from the run
    seed and the person id, so adding a person to the round does not reshuffle
    everybody else's draw.
    """
    counts = {
        person_id: len(facts) for person_id, facts in facts_by_person.items() if facts
    }
    allocation = allocate(counts, sample_size)

    drawn: List[Dict[str, Any]] = []
    for person_id in sorted(allocation):
        take = allocation[person_id]
        if take <= 0:
            continue
        population = sorted(facts_by_person[person_id], key=lambda fact: fact["id"])
        generator = random.Random(f"{seed}:{person_id}")
        drawn.extend(generator.sample(population, min(take, len(population))))

    return sorted(drawn, key=lambda fact: fact["id"])

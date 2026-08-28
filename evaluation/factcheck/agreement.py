#!/usr/bin/env python3
"""How far the evaluators agree, and what the round concluded per fact.

Two numbers, because each answers a question the other cannot. Pairwise percent
agreement says how often two people picked the same verdict, which is what a
reader wants to know and which flatters a round where one verdict dominates:
if nine facts in ten are supported, two evaluators who never look at the
evidence still agree nine times in ten. Krippendorff's alpha corrects for that
by discounting the agreement chance alone would produce, and it tolerates the
missing judgments a round always has, since evaluators stop at different points.

Alpha is reported for the full seven-way scale and again for the collapsed
question — is anything wrong with this claim — because a round can disagree
about the shade while agreeing completely about the substance, and only the
second number tells a maintainer whether to trust the problem count.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from typing import DefaultDict, Dict, List, Optional, Sequence, Tuple


def krippendorff_alpha(ratings: Dict[str, Dict[str, str]]) -> Optional[float]:
    """Nominal alpha over ``{unit: {coder: value}}``, or None when undefined.

    Units rated by fewer than two coders carry no information about agreement
    and are excluded, which is exactly how alpha handles missing data. The value
    is undefined when no unit has two ratings, or when every rating in the round
    is the same value: there is then no disagreement to explain and no expected
    disagreement to compare it against.
    """
    coincidence: DefaultDict[Tuple[str, str], float] = defaultdict(float)
    for values in ratings.values():
        observed = list(values.values())
        pairable = len(observed)
        if pairable < 2:
            continue
        counts = Counter(observed)
        for first in counts:
            for second in counts:
                if first == second:
                    pairs = counts[first] * (counts[first] - 1)
                else:
                    pairs = counts[first] * counts[second]
                coincidence[(first, second)] += pairs / (pairable - 1)

    if not coincidence:
        return None

    categories = sorted({value for pair in coincidence for value in pair})
    totals = {
        category: sum(coincidence[(category, other)] for other in categories)
        for category in categories
    }
    grand = sum(totals.values())
    if grand <= 1:
        return None

    observed_disagreement = sum(
        coincidence[(first, second)]
        for first in categories
        for second in categories
        if first != second
    )
    expected_disagreement = sum(
        totals[first] * totals[second]
        for first in categories
        for second in categories
        if first != second
    )
    if expected_disagreement == 0:
        return None
    return 1.0 - (grand - 1) * observed_disagreement / expected_disagreement


def pairwise_agreement(
    ratings: Dict[str, Dict[str, str]],
) -> Tuple[Optional[float], Dict[Tuple[str, str], Tuple[int, int]]]:
    """Overall percent agreement, and the count per pair of evaluators."""
    per_pair: Dict[Tuple[str, str], Tuple[int, int]] = {}
    agreed = 0
    compared = 0
    for values in ratings.values():
        for first, second in combinations(sorted(values), 2):
            key = (first, second)
            hits, total = per_pair.get(key, (0, 0))
            same = values[first] == values[second]
            per_pair[key] = (hits + (1 if same else 0), total + 1)
            agreed += 1 if same else 0
            compared += 1
    if compared == 0:
        return None, per_pair
    return agreed / compared, per_pair


def majority(values: Sequence[str]) -> Tuple[Optional[str], bool]:
    """The verdict most evaluators gave, and whether it was unanimous.

    A tie has no majority: the fact is reported as contested rather than
    resolved by whichever verdict sorts first, because the tie is the finding.
    """
    if not values:
        return None, False
    counts = Counter(values)
    ranked = counts.most_common()
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None, False
    return ranked[0][0], len(counts) == 1


def collapse_to_problem(verdict: str, problem_verdicts: Sequence[str]) -> str:
    """The binary question behind the scale: is something wrong with this claim.

    'Cannot decide' stays its own value rather than being folded into either
    side, since counting an undecided fact as sound would overstate the story
    and counting it as broken would overstate the defect rate.
    """
    if verdict in problem_verdicts:
        return "problem"
    if verdict == "unclear":
        return "unclear"
    return "sound"


def build_rating_table(
    judgments_by_evaluator: Dict[str, Dict[str, str]],
    fact_ids: Sequence[str],
) -> Dict[str, Dict[str, str]]:
    """``{fact: {evaluator: verdict}}`` for the facts anyone judged."""
    table: Dict[str, Dict[str, str]] = {}
    for fact_id in fact_ids:
        row = {
            evaluator: judgments[fact_id]
            for evaluator, judgments in judgments_by_evaluator.items()
            if fact_id in judgments
        }
        if row:
            table[fact_id] = row
    return table


def disagreements(
    table: Dict[str, Dict[str, str]],
) -> List[Tuple[str, Dict[str, str]]]:
    """Facts on which the evaluators who judged them did not all agree."""
    return [
        (fact_id, values)
        for fact_id, values in table.items()
        if len(set(values.values())) > 1
    ]

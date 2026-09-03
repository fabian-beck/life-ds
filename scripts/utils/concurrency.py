"""Running the independent calls of one step side by side.

A person's run is a chain of roughly forty model calls and as many HTTP
requests, and until now every one of them waited for the one before it. Most
of that order is not an argument: the research of one event does not read the
research of another, a chapter's illustration is drawn from its own concept,
and a Commons query does not care which query ran before it. Their wall clock
was the sum of their latencies because nothing said otherwise.

:func:`map_concurrently` is that something. It takes the items of one step,
runs the same function over each in a small thread pool, and returns the
results in the items' own order, so a caller reads them exactly as it did
from the loop this replaces. Threads rather than asyncio, because the SDK
client, ``requests``, and every phase are synchronous, and the wait is on the
network rather than on the interpreter.

What stays serial is what has to: the geocoder, whose usage policy allows one
request a second, and the phases that read each other's output. The number
of workers is one setting for the whole pipeline (``LIFE_DS_WORKERS``), and
``1`` restores the old order call for call, which is the first thing to try
when the provider starts answering 429.

An exception in one item ends the map, as it ended the loop: the function
each step passes in already turns a failed call into that step's own
fallback, so what reaches here is a defect, not a degraded call.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable, List, Optional, TypeVar

from config import WORKERS

ItemT = TypeVar("ItemT")
ResultT = TypeVar("ResultT")


def worker_count(workers: Optional[int] = None) -> int:
    """The pool size to use: the argument, else the configured default.

    Never below one. A zero or a negative number in the environment reads as
    a request for the serial order rather than as an error.
    """
    chosen = WORKERS if workers is None else workers
    return max(1, int(chosen))


def map_concurrently(
    items: Iterable[ItemT],
    function: Callable[[ItemT], ResultT],
    *,
    workers: Optional[int] = None,
) -> List[ResultT]:
    """``[function(item) for item in items]``, computed side by side.

    Results come back in the order of ``items`` whatever order they finished
    in. With one worker the function is called inline, in order, so a run
    that sets ``LIFE_DS_WORKERS=1`` behaves and prints exactly as the loop
    did.
    """
    sequence = list(items)
    if not sequence:
        return []
    pool_size = min(worker_count(workers), len(sequence))
    if pool_size == 1:
        return [function(item) for item in sequence]
    with ThreadPoolExecutor(max_workers=pool_size) as pool:
        return list(pool.map(function, sequence))

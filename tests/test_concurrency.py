"""The thread pool the steps share, and the ledger it writes into.

Running a step's calls side by side changes nothing a reader of the output
should notice: the results come back in the items' order, a step with one
worker is the loop it replaced, and the ledger counts every call whichever
thread made it. Each of those is a promise the callers rely on without
checking, so they are checked here. No network is involved.
"""

from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from events.images import assign, sources  # noqa: E402
from utils import concurrency, usage  # noqa: E402


class MapConcurrentlyTests(unittest.TestCase):
    def test_results_keep_the_order_of_the_items(self) -> None:
        # The first item is the slowest, so a pool that returned results in
        # completion order would put it last.
        def slow_first(item: int) -> int:
            time.sleep(0.05 if item == 0 else 0)
            return item * 10

        self.assertEqual(
            concurrency.map_concurrently(range(5), slow_first, workers=4),
            [0, 10, 20, 30, 40],
        )

    def test_the_items_really_run_side_by_side(self) -> None:
        seen_together = 0
        active = 0
        lock = threading.Lock()

        def hold(item: int) -> int:
            nonlocal active, seen_together
            with lock:
                active += 1
                seen_together = max(seen_together, active)
            time.sleep(0.05)
            with lock:
                active -= 1
            return item

        concurrency.map_concurrently(range(4), hold, workers=4)
        self.assertGreater(seen_together, 1)

    def test_one_worker_runs_inline_and_in_order(self) -> None:
        threads: List[int] = []
        order: List[int] = []

        def note(item: int) -> int:
            threads.append(threading.get_ident())
            order.append(item)
            return item

        concurrency.map_concurrently([3, 1, 2], note, workers=1)
        self.assertEqual(order, [3, 1, 2])
        self.assertEqual(set(threads), {threading.get_ident()})

    def test_an_empty_input_asks_nothing(self) -> None:
        function = mock.Mock()
        self.assertEqual(concurrency.map_concurrently([], function), [])
        function.assert_not_called()

    def test_a_failure_in_one_item_ends_the_map(self) -> None:
        def fail_on_two(item: int) -> int:
            if item == 2:
                raise ValueError("two")
            return item

        with self.assertRaises(ValueError):
            concurrency.map_concurrently([1, 2, 3], fail_on_two, workers=2)

    def test_the_worker_count_never_drops_below_one(self) -> None:
        self.assertEqual(concurrency.worker_count(0), 1)
        self.assertEqual(concurrency.worker_count(-3), 1)
        self.assertEqual(concurrency.worker_count(6), 6)
        with mock.patch.object(concurrency, "WORKERS", 0):
            self.assertEqual(concurrency.worker_count(), 1)


class LedgerUnderThreadsTests(unittest.TestCase):
    """Every call is counted, whichever thread made it."""

    def setUp(self) -> None:
        usage.reset()

    def test_records_from_many_threads_are_all_kept(self) -> None:
        usage.begin_step("Life events")

        def record(item: int) -> int:
            response = SimpleNamespace(
                usage=SimpleNamespace(input_tokens=1, output_tokens=1)
            )
            usage.record_response("model-a", response, label=f"call {item}")
            return item

        concurrency.map_concurrently(range(64), record, workers=8)
        rows = {row.step: row for row in usage.by_step()}
        self.assertEqual(rows["Life events"].calls, 64)
        self.assertEqual(rows["Life events"].input_tokens, 64)


class BatchSearchUnderThreadsTests(unittest.TestCase):
    """The merged result is the serial one, whatever order the answers came in."""

    def test_the_first_sighting_is_decided_by_query_order(self) -> None:
        def commons(query: str, limit: int = 10) -> List[Dict[str, Any]]:
            # The later query answers first; the earlier one must still win.
            time.sleep(0 if query == "later" else 0.05)
            return [{"url": "https://example.org/same.jpg", "filename": query}]

        with (
            mock.patch.object(sources, "search_wikimedia_commons", commons),
            mock.patch.object(sources, "search_openverse", lambda q, limit=10: []),
            mock.patch.object(concurrency, "WORKERS", 4),
        ):
            images = assign.execute_batch_image_search(["earlier", "later"])

        self.assertEqual([img["filename"] for img in images], ["earlier"])


if __name__ == "__main__":
    unittest.main()

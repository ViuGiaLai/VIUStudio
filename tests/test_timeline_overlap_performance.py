import importlib.util
import os
import sys
import time
import unittest
from types import SimpleNamespace


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
UI_ROOT = os.path.join(ROOT, "ui")
if UI_ROOT not in sys.path:
    sys.path.insert(0, UI_ROOT)

TIMELINE_PATH = os.path.join(ROOT, "ui", "views", "editor", "timeline.py")
SPEC = importlib.util.spec_from_file_location("test_overlap_performance_timeline", TIMELINE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
EditorTimeline = MODULE.EditorTimeline


class TimelineOverlapPerformanceTests(unittest.TestCase):
    def _owner(self):
        return SimpleNamespace(_overlap_row_assignments={}, _drag_state={})

    def test_thousands_of_sequential_cues_stay_on_one_row(self):
        layers = [
            SimpleNamespace(
                id=f"cue-{index}",
                start=index * 0.75,
                end=index * 0.75 + 0.7,
                metadata={},
            )
            for index in range(5_000)
        ]
        owner = self._owner()
        started = time.perf_counter()
        rows, row_count = EditorTimeline._compute_overlap_rows(owner, layers, "TS1")
        elapsed = time.perf_counter() - started

        self.assertEqual(row_count, 1)
        self.assertTrue(all(row == 0 for row in rows))
        # This guards against accidentally restoring the previous quadratic
        # interval scan. The threshold is deliberately generous for CI.
        self.assertLess(elapsed, 2.0)

    def test_overlapping_cues_are_still_stacked(self):
        layers = [
            SimpleNamespace(id="a", start=0.0, end=2.0, metadata={}),
            SimpleNamespace(id="b", start=1.0, end=3.0, metadata={}),
            SimpleNamespace(id="c", start=3.0, end=4.0, metadata={}),
        ]
        rows, row_count = EditorTimeline._compute_overlap_rows(self._owner(), layers, "TS1")

        self.assertEqual(row_count, 2)
        self.assertEqual(rows, [0, 1, 0])


if __name__ == "__main__":
    unittest.main()

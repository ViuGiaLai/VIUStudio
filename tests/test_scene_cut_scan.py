import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path[:0] = [os.path.join(ROOT, "app")]

from app.services.auto_recap_engine import AutoRecapEngine


class SceneCutScanTests(unittest.TestCase):
    def _scan(self, stdout: str, **kwargs):
        calls = []

        def fake_run(command, **_run_kwargs):
            calls.append(command)
            return SimpleNamespace(stdout=stdout, returncode=0)

        with patch("app.services.auto_recap_engine.subprocess.run", side_effect=fake_run), \
             patch("app.services.auto_recap_engine.os.path.exists", return_value=True):
            cuts = AutoRecapEngine().detect_scene_cuts("movie.mp4", **kwargs)
        return cuts, calls

    def test_scan_covers_only_the_window_and_offsets_results_to_absolute_time(self):
        cuts, calls = self._scan(
            "frame:0 pts_time:5.0\nframe:1 pts_time:9.5\n",
            start=100.0,
            end=700.0,
            chunk_seconds=300.0,
        )

        # 100-400 and 400-700: the 0-100 and 700+ regions are never decoded.
        self.assertEqual(cuts, [105.0, 109.5, 405.0, 409.5])
        self.assertEqual(len(calls), 2)
        self.assertIn("100.000", calls[0])
        self.assertIn("400.000", calls[1])
        for command in calls:
            self.assertNotIn("-skip_frame", command)
            self.assertNotIn("nokey", command)
            self.assertIn("fps=5,scale=192:-2,select='gt(scene,0.3)',metadata=print:file=-", command)
            self.assertIn("-ss", command)

    def test_scan_without_explicit_end_runs_one_bounded_pass(self):
        cuts, calls = self._scan("frame:0 pts_time:2.0\n", start=10.0)

        self.assertEqual(cuts, [12.0])
        self.assertEqual(len(calls), 1)
        self.assertNotIn("-t", calls[0])

    def test_missing_video_and_empty_window_never_reach_ffmpeg(self):
        engine = AutoRecapEngine()
        self.assertEqual(engine.detect_scene_cuts("", 0.0, 10.0), [])
        with patch("app.services.auto_recap_engine.subprocess.run") as run:
            self.assertEqual(engine.detect_scene_cuts("movie.mp4", 10.0, 10.0), [])
            run.assert_not_called()

    def test_chunk_failure_keeps_the_cuts_found_earlier(self):
        responses = [
            SimpleNamespace(stdout="frame:0 pts_time:5.0\n", returncode=0),
            OSError("decoder died"),
        ]

        def fake_run(command, **_run_kwargs):
            response = responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response

        with patch("app.services.auto_recap_engine.subprocess.run", side_effect=fake_run), \
             patch("app.services.auto_recap_engine.os.path.exists", return_value=True):
            cuts = AutoRecapEngine().detect_scene_cuts(
                "movie.mp4", 100.0, 700.0, chunk_seconds=300.0
            )

        self.assertEqual(cuts, [105.0])


if __name__ == "__main__":
    unittest.main()

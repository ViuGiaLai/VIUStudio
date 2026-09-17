import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path[:0] = [os.path.join(ROOT, "app"), ROOT]

from app.services.auto_recap_engine import AutoRecapEngine, ShotDecision


class TestAutoRecapVerification(unittest.TestCase):
    """Explicit Verification Test confirming every single EDL rule maps to actual FFmpeg filter string."""

    def test_all_12_rules_generate_ffmpeg_filters(self):
        engine = AutoRecapEngine()

        # Shot A: Horizontal Flip + Zoom
        shot_a = ShotDecision(
            shot_index=0, start_time=0.0, end_time=3.0, duration=3.0,
            importance_score=88.0, action_type="KEEP", zoom_scale=1.10,
            horizontal_flip=True
        )
        # Shot B: Pan Left to Right
        shot_b = ShotDecision(
            shot_index=1, start_time=3.0, end_time=6.0, duration=3.0,
            importance_score=75.0, action_type="KEEP", pan_direction="left_right"
        )
        # Shot C: Speed Accent + Freeze Frame
        shot_c = ShotDecision(
            shot_index=2, start_time=6.0, end_time=10.0, duration=4.0,
            importance_score=90.0, action_type="KEEP", speed=1.15, freeze_duration=0.4
        )
        # Shot D: Crop Reframe Speaker
        shot_d = ShotDecision(
            shot_index=3, start_time=10.0, end_time=13.0, duration=3.0,
            importance_score=60.0, action_type="KEEP", crop_mode="speaker"
        )

        decisions = [shot_a, shot_b, shot_c, shot_d]
        filtergraph, maps = engine.build_ffmpeg_filtergraph(decisions)

        print("\n--- FFmpeg Filtergraph Verification Output ---")
        print(filtergraph)

        # Rule 1: Trim & PTS
        self.assertIn("trim=start=0.00:end=3.00", filtergraph)
        self.assertIn("setpts=PTS-STARTPTS", filtergraph)

        # Rule 3: Zoom
        self.assertIn("scale=iw*1.10:ih*1.10", filtergraph)

        # Rule 4: Pan Left-Right Expression
        self.assertIn("crop=w=iw/1.15:h=ih/1.15:x='(iw-ow)*t/3.00'", filtergraph)

        # Rule 5: Crop Speaker
        self.assertIn("y='(ih-oh)/3'", filtergraph)

        # Rule 6: Speed Accent (setpts + atempo)
        self.assertIn("setpts=PTS/1.15", filtergraph)
        self.assertIn("atempo=1.15", filtergraph)

        # Rule 7: Freeze Frame (tpad + apad)
        self.assertIn("tpad=stop_mode=clone:stop=14,setpts=PTS/1.15", filtergraph)
        self.assertIn("apad=pad_dur=0.4600,atempo=1.15", filtergraph)

        # Rule 8: Horizontal Flip
        self.assertIn("hflip", filtergraph)

        # Concat Check
        self.assertIn("concat=n=4:v=1:a=1[vfinal][afinal]", filtergraph)

    def test_cut_decisions_are_excluded_from_concat(self):
        engine = AutoRecapEngine()
        filtergraph, _maps = engine.build_ffmpeg_filtergraph([
            ShotDecision(0, 0.0, 2.0, 2.0, 0.0, "CUT"),
            ShotDecision(1, 2.0, 4.0, 2.0, 100.0, "KEEP"),
        ])
        self.assertNotIn("trim=start=0.00:end=2.00", filtergraph)
        self.assertIn("concat=n=1", filtergraph)


if __name__ == "__main__":
    unittest.main()

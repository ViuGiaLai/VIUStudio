import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path[:0] = [os.path.join(ROOT, "app"), os.path.join(ROOT, "ui"), ROOT]

from helpers.srt_helpers import normalize_subtitle_timing


class SubtitleTimingNormalizationTests(unittest.TestCase):
    def test_duplicate_shifted_cue_is_removed(self):
        segments = [
            {"start": 160.0, "end": 163.0, "text": "Đạo hữu vừa rồi liên chiến với hai vị Thiên Vương"},
            {"start": 161.0, "end": 164.0, "text": "Đạo hữu vừa rồi liên chiến với hai vị Thiên Vương,"},
        ]

        result = normalize_subtitle_timing(segments)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["start"], 160.0)

    def test_different_overlapping_cues_become_one_lane(self):
        segments = [
            {
                "start": 1.0,
                "end": 3.0,
                "text": "first",
                "speaker": "A",
                "_audio_end": 3.5,
                "words": [
                    {"start": 1.0, "end": 1.5, "word": "first"},
                    {"start": 2.2, "end": 2.6, "word": "stale"},
                ],
            },
            {"start": 2.0, "end": 4.0, "text": "second", "speaker": "B"},
        ]

        result = normalize_subtitle_timing(segments)

        self.assertEqual([item["text"] for item in result], ["first", "second"])
        self.assertAlmostEqual(result[0]["end"], 1.96, delta=0.001)
        self.assertGreaterEqual(result[1]["start"], result[0]["end"])
        self.assertNotIn("_audio_end", result[0])
        self.assertEqual([word["word"] for word in result[0]["words"]], ["first"])

    def test_same_text_later_in_video_is_not_removed(self):
        segments = [
            {"start": 1.0, "end": 2.0, "text": "Dừng tay"},
            {"start": 8.0, "end": 9.0, "text": "Dừng tay"},
        ]

        result = normalize_subtitle_timing(segments)

        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()

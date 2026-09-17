import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "app")]

from app.services.segment_regroup_service import SegmentRegroupService


class SegmentRegroupServiceTests(unittest.TestCase):
    def setUp(self):
        SegmentRegroupService._QUOTA_EXHAUSTED_UNTIL = 0.0
        SegmentRegroupService._AI_SHORTEN_CACHE.clear()

    def test_long_chinese_cue_without_word_timing_is_split(self):
        service = SegmentRegroupService()
        result = service.regroup(
            [{
                "start": 10.0,
                "end": 22.0,
                "text": "你不要以为我们怕了你如今你气血消耗巨大你以为你还能斗得过我们父子二人不成",
            }],
            max_duration_seconds=5.0,
        )
        self.assertEqual(len(result), 3)
        self.assertEqual("".join(item["text"] for item in result), "你不要以为我们怕了你如今你气血消耗巨大你以为你还能斗得过我们父子二人不成")
        self.assertAlmostEqual(result[0]["start"], 10.0)
        self.assertAlmostEqual(result[-1]["end"], 22.0)
        self.assertTrue(all(item["end"] - item["start"] <= 5.01 for item in result))

    def test_word_timestamps_define_split_boundaries(self):
        service = SegmentRegroupService()
        result = service.regroup(
            [{
                "start": 0.0,
                "end": 6.0,
                "text": "Wait here. I will return.",
                "words": [
                    {"start": 0.0, "end": 1.0, "text": "Wait"},
                    {"start": 1.0, "end": 2.0, "text": "here."},
                    {"start": 3.0, "end": 4.0, "text": "I"},
                    {"start": 4.0, "end": 5.0, "text": "will"},
                    {"start": 5.0, "end": 6.0, "text": "return."},
                ],
            }],
            max_duration_seconds=4.0,
        )
        self.assertEqual([item["text"] for item in result], ["Wait here.", "I will return."])
        self.assertEqual(result[0]["end"], 2.0)
        self.assertEqual(result[1]["start"], 3.0)

    def test_short_cue_is_preserved(self):
        source = {"start": 1.0, "end": 2.0, "text": "等一下", "speaker": "SPEAKER_01"}
        result = SegmentRegroupService().regroup([source], max_duration_seconds=5.0)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "等一下")
        self.assertEqual(result[0]["speaker"], "SPEAKER_01")

    def test_absorbs_tiny_trailing_fragment_after_longer_cue(self):
        result = SegmentRegroupService.deduplicate_and_clamp_timeline([
            {
                "start": 47.52,
                "end": 48.385,
                "text": "操縱層是你打的",
                "words": [{"start": 47.55, "end": 47.80, "text": "操"}, {"start": 48.2, "end": 48.38, "text": "的"}],
            },
            {
                "start": 48.385,
                "end": 48.485,
                "text": "草重层",
                "words": [{"start": 48.40, "end": 48.47, "text": "层"}],
            },
        ])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "操縱層是你打的")
        self.assertAlmostEqual(result[0]["end"], 48.485)
        self.assertEqual(len(result[0]["words"]), 3)

    def test_absorbs_tiny_trailing_fragment_after_short_cue(self):
        result = SegmentRegroupService.deduplicate_and_clamp_timeline([
            {"start": 347.12, "end": 347.73, "text": "血胜值"},
            {"start": 347.73, "end": 347.94, "text": "先盛職"},
        ])

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "血胜值")
        self.assertAlmostEqual(result[0]["end"], 347.94)

    def test_does_not_absorb_genuine_adjacent_short_dialogue(self):
        # ``你没死`` lasts 0.5s - a real reply, not a sub-second echo.
        result = SegmentRegroupService.deduplicate_and_clamp_timeline([
            {"start": 241.295, "end": 242.030, "text": "父亲"},
            {"start": 242.030, "end": 242.530, "text": "你没死"},
        ])
        self.assertEqual(len(result), 2)
        self.assertEqual([item["text"] for item in result], ["父亲", "你没死"])

        # Two full-length fight callouts must stay separate.
        result = SegmentRegroupService.deduplicate_and_clamp_timeline([
            {"start": 83.761, "end": 84.984, "text": "猛虎啸山"},
            {"start": 84.984, "end": 85.940, "text": "给我死"},
        ])
        self.assertEqual(len(result), 2)
        self.assertEqual([item["text"] for item in result], ["猛虎啸山", "给我死"])

    def test_does_not_absorb_short_reply_when_window_is_wide(self):
        # A 0.25s reply after a 1.2s line leaves a 1.45s combined window.
        result = SegmentRegroupService.deduplicate_and_clamp_timeline([
            {"start": 10.0, "end": 11.2, "text": "我可是他的父亲"},
            {"start": 11.2, "end": 11.45, "text": "滚"},
        ])
        self.assertEqual(len(result), 2)
        self.assertEqual([item["text"] for item in result], ["我可是他的父亲", "滚"])


    def test_clamps_large_timeline_overlap_cleanly(self):
        result = SegmentRegroupService.deduplicate_and_clamp_timeline([
            {"start": 10.0, "end": 14.0, "text": "第一句话"},
            {"start": 13.0, "end": 16.0, "text": "第二句话"},
        ])
        self.assertEqual(len(result), 2)
        self.assertLessEqual(result[0]["end"], result[1]["start"])

    def test_orders_imported_cues_before_deduplication(self):
        result = SegmentRegroupService.deduplicate_and_clamp_timeline([
            {"start": 2.0, "end": 3.0, "text": "第二句"},
            {"start": 0.0, "end": 1.0, "text": "第一句"},
            {"start": "bad", "end": 4.0, "text": "忽略"},
        ])
        self.assertEqual([item["text"] for item in result], ["第一句", "第二句"])
    def test_short_cue_followed_by_silence_expands_into_gap(self):
        # Truncated 0.42s Chinese cue followed by 1.35s gap before next cue
        service = SegmentRegroupService()
        result = service.expand_short_cues_into_gaps([
            {
                "start": 53.839,
                "end": 54.261,
                "text": "你倒是挺大方的",
                "dubbing_vi": "Anh hào phóng thật đấy.",
            },
            {
                "start": 55.606,
                "end": 57.241,
                "text": "拿着吧 赶紧趁热吃",
                "dubbing_vi": "Cầm lấy, ăn nóng đi cháu.",
            },
        ])
        self.assertEqual(len(result), 2)
        # Subtitle timeline is strictly IMMUTABLE (preserves video sync)
        self.assertEqual(result[0]["start"], 53.839)
        self.assertEqual(result[0]["end"], 54.261)
        self.assertEqual(result[0]["sub_start"], 53.839)
        self.assertEqual(result[0]["sub_end"], 54.261)

        # Voice speech window expands into the gap to provide comfortable speech duration
        self.assertGreater(result[0]["voice_end"], 55.0)
        # But must not collide with Cue 2 onset (safe margin 0.08s)
        self.assertLessEqual(result[0]["voice_end"], 55.606 - 0.08)
        self.assertAlmostEqual(result[1]["start"], 55.606)

    def test_short_cue_without_gap_is_not_expanded_over_next_cue(self):
        service = SegmentRegroupService()
        result = service.expand_short_cues_into_gaps([
            {"start": 1.0, "end": 1.4, "text": "Đợi đã"},
            {"start": 1.45, "end": 2.5, "text": "Tôi tới ngay"},
        ])
        self.assertEqual(len(result), 2)
        # Gap is only 0.05s (< safe_gap 0.08s), cue 1 must not overshoot cue 2
        self.assertLessEqual(result[0]["end"], 1.45)

    def test_ai_shorten_text_for_tts_mocked(self):
        from unittest.mock import MagicMock, patch
        SegmentRegroupService._AI_SHORTEN_CACHE.clear()

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "Hôm nay tôi rất vui vẻ."
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        with patch("openai.OpenAI", return_value=mock_client), \
             patch.dict("os.environ", {"GOOGLE_AI_STUDIO_API_KEY": "fake_test_key", "GOOGLE_AI_STUDIO_MODEL": "gemini-3.6-flash"}):
            shortened = SegmentRegroupService.ai_shorten_text_for_tts(
                "Hôm nay tôi cảm thấy thực sự vô cùng rất là vui vẻ và hạnh phúc.",
                available_duration=1.2,
                context_prev="Chào bạn,",
            )
            self.assertEqual(shortened, "Hôm nay tôi rất vui vẻ.")
            self.assertTrue(mock_client.chat.completions.create.called)
            call_kwargs = mock_client.chat.completions.create.call_args[1]
            self.assertEqual(call_kwargs["model"], "gemini-3.6-flash")
            # Verify prompt mentions context and constraints
            prompt_content = call_kwargs["messages"][0]["content"]
            self.assertIn("Chào bạn,", prompt_content)
            self.assertIn("rút gọn", prompt_content.lower())

    def test_ai_shorten_text_for_tts_rejects_dropping_negation(self):
        from unittest.mock import MagicMock, patch
        SegmentRegroupService._AI_SHORTEN_CACHE.clear()

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        # AI hallucinated and dropped "không"
        mock_choice.message.content = "Tôi đồng ý với việc này."
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        with patch("openai.OpenAI", return_value=mock_client), \
             patch.dict("os.environ", {"GOOGLE_AI_STUDIO_API_KEY": "fake_test_key"}):
            original = "Tôi không đồng ý với việc này đâu."
            result = SegmentRegroupService.ai_shorten_text_for_tts(original, available_duration=1.0)
            # Must reject and return original to protect semantics
            self.assertEqual(result, original)

    def test_ai_shorten_text_for_tts_rejects_longer_output(self):
        from unittest.mock import MagicMock, patch
        SegmentRegroupService._AI_SHORTEN_CACHE.clear()

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        # AI generated a longer sentence
        mock_choice.message.content = "Tôi đang cảm thấy vô cùng háo hức và mong chờ từng giây phút một."
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        with patch("openai.OpenAI", return_value=mock_client), \
             patch.dict("os.environ", {"GOOGLE_AI_STUDIO_API_KEY": "fake_test_key"}):
            original = "Tôi đang rất háo hức."
            result = SegmentRegroupService.ai_shorten_text_for_tts(original, available_duration=0.8)
            self.assertEqual(result, original)

    def test_expand_short_cues_uses_ai_shortening_on_overflow(self):
        from unittest.mock import patch
        SegmentRegroupService._AI_SHORTEN_CACHE.clear()

        # Mock ai_shorten_text_for_tts to return a succinct sentence
        with patch.object(
            SegmentRegroupService,
            "ai_shorten_text_for_tts",
            return_value="Đừng đi lung tung.",
        ) as mock_ai:
            segments = [
                {
                    "start": 10.0,
                    "end": 10.8,
                    "text": "Tuyệt đối không được phép chạy lung tung khắp mọi nơi như vậy.",
                }
            ]
            result = SegmentRegroupService.expand_short_cues_into_gaps(segments, enable_ai=True)
            self.assertEqual(len(result), 1)
            # The AI candidate should be used for dubbing_vi and tts_text
            self.assertEqual(result[0]["dubbing_vi"], "Đừng đi lung tung.")
            self.assertEqual(result[0]["tts_text"], "Đừng đi lung tung.")
            self.assertTrue(mock_ai.called)

    def test_expand_short_cues_skips_ai_when_enable_ai_false(self):
        from unittest.mock import patch
        SegmentRegroupService._AI_SHORTEN_CACHE.clear()

        with patch.object(SegmentRegroupService, "ai_shorten_text_for_tts") as mock_ai:
            segments = [
                {
                    "start": 10.0,
                    "end": 10.8,
                    "text": "Tuyệt đối không được phép chạy lung tung khắp mọi nơi như vậy.",
                }
            ]
            # Default enable_ai is False (used during UI timeline / project loading)
            result = SegmentRegroupService.expand_short_cues_into_gaps(segments, enable_ai=False)
            self.assertEqual(len(result), 1)
            # Must NOT call AI to prevent blocking the UI thread
            self.assertFalse(mock_ai.called)

    def test_ai_shorten_circuit_breaker_on_429(self):
        from unittest.mock import MagicMock, patch
        SegmentRegroupService._AI_SHORTEN_CACHE.clear()
        SegmentRegroupService._QUOTA_EXHAUSTED_UNTIL = 0.0

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("429 RESOURCE_EXHAUSTED: Quota exceeded")

        with patch("openai.OpenAI", return_value=mock_client), \
             patch.dict("os.environ", {"GOOGLE_AI_STUDIO_API_KEY": "fake_test_key"}):
            original = "Hôm nay tôi rất vui vẻ và hạnh phúc."
            # First call triggers 429
            res1 = SegmentRegroupService.ai_shorten_text_for_tts(original, available_duration=1.0)
            self.assertEqual(res1, original)
            self.assertTrue(SegmentRegroupService._QUOTA_EXHAUSTED_UNTIL > 0.0)

            # Second call should be intercepted by circuit breaker instantly without calling API
            mock_client.chat.completions.create.reset_mock()
            res2 = SegmentRegroupService.ai_shorten_text_for_tts("Một câu khác nữa", available_duration=1.0)
            self.assertEqual(res2, "Một câu khác nữa")
            self.assertFalse(mock_client.chat.completions.create.called)


if __name__ == "__main__":
    unittest.main()


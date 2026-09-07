import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "app")]

from services.asr_vocalization_filter_service import AsrVocalizationFilterService
from services.asr_ocr_reconciliation_service import AsrOcrReconciliationService


class AsrVocalizationFilterTests(unittest.TestCase):
    def test_removes_unsupported_standalone_fillers_across_languages(self):
        source = [
            {"start": index, "end": index + 0.4, "text": text, "speech_gate": "silero_vad"}
            for index, text in enumerate(
                ("嗯", "唉。", "哼!", "呃", "哦", "哇", "呀", "哟", "um...", "hmm", "ừm.")
            )
        ]

        filtered, removed = AsrVocalizationFilterService.filter_generated_segments(source)

        self.assertEqual(filtered, [])
        self.assertEqual(removed, len(source))

    def test_keeps_vocalization_inside_real_dialogue_and_short_commands(self):
        source = [
            {"start": 0.0, "end": 1.0, "text": "嗯，我知道了"},
            {"start": 1.0, "end": 1.5, "text": "走"},
            {"start": 1.5, "end": 2.0, "text": "好"},
            {"start": 2.0, "end": 2.5, "text": "不"},
        ]

        filtered, removed = AsrVocalizationFilterService.filter_generated_segments(source)

        self.assertEqual(filtered, source)
        self.assertEqual(removed, 0)

    def test_stable_source_subtitle_can_preserve_real_interjection(self):
        source = [{
            "start": 4.0,
            "end": 4.8,
            "text": "嗯",
            "ocr_text": "嗯",
            "ocr_consensus_frames": 2,
            "text_source": "ocr_reconciled",
        }]

        filtered, removed = AsrVocalizationFilterService.filter_generated_segments(source)

        self.assertEqual(filtered, source)
        self.assertEqual(removed, 0)

    def test_one_unstable_ocr_frame_does_not_preserve_filler(self):
        filtered, removed = AsrVocalizationFilterService.filter_generated_segments([{
            "start": 4.0,
            "end": 4.8,
            "text": "嗯",
            "ocr_text": "嗯",
            "ocr_consensus_frames": 1,
        }])

        self.assertEqual(filtered, [])
        self.assertEqual(removed, 1)

    def test_removes_single_latin_decoder_fragments_from_cjk_transcript(self):
        source = [
            {"start": 0.0, "end": 0.2, "text": "A"},
            {"start": 0.2, "end": 0.4, "text": "K."},
            {"start": 0.4, "end": 1.2, "text": "我知道了"},
        ]

        filtered, removed = AsrVocalizationFilterService.filter_generated_segments(
            source, source_language="zh"
        )

        self.assertEqual([item["text"] for item in filtered], ["我知道了"])
        self.assertEqual(removed, 2)

    def test_does_not_remove_spoken_letters_from_latin_language(self):
        source = [{"start": 0.0, "end": 0.3, "text": "A"}]

        filtered, removed = AsrVocalizationFilterService.filter_generated_segments(
            source, source_language="en"
        )

        self.assertEqual(filtered, source)
        self.assertEqual(removed, 0)

    def test_removes_bracketed_non_speech_annotations(self):
        source = [
            {"start": 0.0, "end": 1.0, "text": "[Music]"},
            {"start": 1.0, "end": 2.0, "text": "（掌声）"},
            {"start": 2.0, "end": 3.0, "text": "[real dialogue]"},
        ]

        filtered, removed = AsrVocalizationFilterService.filter_generated_segments(source)

        self.assertEqual([item["text"] for item in filtered], ["[real dialogue]"])
        self.assertEqual(removed, 2)

    def test_tts_defense_filters_stale_generated_filler_but_keeps_manual_voice(self):
        source = [
            {"original_text": "嗯", "text": "Ừm."},
            {"original_text": "嗯", "text": "Được.", "voice_edited": True},
            {"original_text": "我知道了", "text": "Tôi biết rồi."},
        ]

        filtered, removed = AsrVocalizationFilterService.filter_tts_segments(source)

        self.assertEqual([item["text"] for item in filtered], ["Được.", "Tôi biết rồi."])
        self.assertEqual(removed, 1)

    def test_removes_physically_implausible_short_decode_without_ocr(self):
        source = [
            {"start": 10.0, "end": 10.1, "text": "是父亲"},
            {"start": 11.0, "end": 11.13, "text": "要要"},
            {"start": 12.0, "end": 12.3, "text": "快跑"},
        ]

        filtered, removed = AsrVocalizationFilterService.filter_generated_segments(
            source, source_language="zh"
        )

        self.assertEqual([item["text"] for item in filtered], ["快跑"])
        self.assertEqual(removed, 2)

    def test_stable_ocr_preserves_short_source_caption(self):
        source = [{
            "start": 10.0,
            "end": 10.1,
            "text": "全部",
            "text_source": "ocr_timing_aligned",
        }]

        filtered, removed = AsrVocalizationFilterService.filter_generated_segments(source)

        self.assertEqual(filtered, source)
        self.assertEqual(removed, 0)

    def test_rejection_report_explains_each_removed_cue(self):
        filtered, removed, report = (
            AsrVocalizationFilterService.filter_generated_segments_with_report([
                {"start": 1.0, "end": 1.4, "text": "嗯"},
                {"start": 2.0, "end": 2.1, "text": "A"},
            ], source_language="zh")
        )

        self.assertEqual(filtered, [])
        self.assertEqual(removed, 2)
        self.assertEqual([item["reason"] for item in report], [
            "standalone_vocalization", "cross_script_fragment",
        ])

    def test_exact_stable_ocr_agreement_preserves_real_short_vocalization(self):
        reconciled, _count = AsrOcrReconciliationService.reconcile(
            [{"start": 5.0, "end": 5.5, "text": "嗯", "speech_detected": True}],
            [{
                "start": 5.0,
                "end": 5.5,
                "text": "嗯",
                "ocr_consensus_frames": 2,
            }],
            source_language="zh",
        )

        filtered, removed = AsrVocalizationFilterService.filter_generated_segments(
            reconciled, source_language="zh"
        )

        self.assertEqual(removed, 0)
        self.assertEqual(filtered[0]["text_source"], "ocr_verified")


if __name__ == "__main__":
    unittest.main()

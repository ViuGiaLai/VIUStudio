import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "app")]

from services.asr_ocr_reconciliation_service import AsrOcrReconciliationService
import ocr_processor
from translation.quality_guard import apply_translation_quality_guard
from sensevoice_processor import (
    _lang_code,
    _pad_and_merge_vad_segments,
    requires_multilingual_whisper,
    supports_language,
)


class AsrOcrReconciliationTests(unittest.TestCase):
    def test_restores_truncated_chinese_cue_at_same_time(self):
        asr = [{"start": 81.464, "end": 82.272, "text": "下"}]
        ocr = [{"start": 81.25, "end": 82.50, "text": "等一下"}]

        repaired, count = AsrOcrReconciliationService.reconcile(asr, ocr)

        self.assertEqual(count, 1)
        self.assertEqual(repaired[0]["text"], "等一下")
        self.assertEqual(repaired[0]["asr_text_original"], "下")
        self.assertEqual(repaired[0]["text_source"], "ocr_reconciled")
        self.assertEqual(repaired[0]["start"], 81.464)
        self.assertEqual(repaired[0]["end"], 82.272)

    def test_keeps_complete_asr_text(self):
        asr = [{"start": 1.0, "end": 2.0, "text": "等一下"}]
        ocr = [{"start": 1.0, "end": 2.0, "text": "等一下"}]

        repaired, count = AsrOcrReconciliationService.reconcile(asr, ocr)

        self.assertEqual(count, 0)
        self.assertEqual(repaired[0]["text"], "等一下")
        self.assertEqual(repaired[0]["ocr_text"], "等一下")
        self.assertEqual(repaired[0]["text_source"], "ocr_verified")
        self.assertEqual(repaired[0]["ocr_consensus_frames"], 2)

    def test_does_not_copy_unrelated_title_or_non_overlapping_text(self):
        asr = [{"start": 10.0, "end": 10.7, "text": "下"}]
        ocr = [
            {"start": 10.0, "end": 10.7, "text": "修仙传奇"},
            {"start": 20.0, "end": 21.0, "text": "等一下"},
        ]

        repaired, count = AsrOcrReconciliationService.reconcile(asr, ocr)

        self.assertEqual(count, 0)
        self.assertEqual(repaired[0]["text"], "下")

    def test_rejects_preview_card_even_when_it_contains_the_short_asr_text(self):
        repaired, count = AsrOcrReconciliationService.reconcile(
            [{"start": 10.0, "end": 10.7, "text": "下", "speech_detected": True}],
            [{"start": 10.0, "end": 10.7, "text": "下集预告"}],
            source_language="zh",
        )
        self.assertEqual(count, 0)
        self.assertEqual(repaired[0]["text"], "下")

    def test_stable_source_subtitle_repairs_arbitrary_short_asr_error(self):
        repaired, count = AsrOcrReconciliationService.reconcile(
            [{"start": 124.863, "end": 126.356, "text": "助手", "speech_detected": True}],
            [{"start": 124.8, "end": 126.4, "text": "住手", "ocr_consensus_frames": 2}],
            source_language="zh",
        )
        self.assertEqual(count, 1)
        self.assertEqual(repaired[0]["text"], "住手")

        corrected, corrected_count = AsrOcrReconciliationService.reconcile(
            [{"start": 124.863, "end": 126.356, "text": "助手", "speech_detected": True}],
            [{"start": 124.8, "end": 126.4, "text": "天地", "ocr_consensus_frames": 2}],
            source_language="zh",
        )
        self.assertEqual(corrected_count, 1)
        self.assertEqual(corrected[0]["text"], "天地")

        # One OCR frame is never authoritative for an arbitrary mismatch.
        unstable, unstable_count = AsrOcrReconciliationService.reconcile(
            [{"start": 124.863, "end": 126.356, "text": "助手", "speech_detected": True}],
            [{"start": 124.8, "end": 126.4, "text": "天地", "ocr_consensus_frames": 1}],
            source_language="zh",
        )
        self.assertEqual(unstable_count, 0)
        self.assertEqual(unstable[0]["text"], "助手")

    def test_explicit_no_speech_never_requests_or_accepts_ocr(self):
        asr = [{"start": 1.0, "end": 2.0, "text": "下", "speech_detected": False}]
        self.assertFalse(AsrOcrReconciliationService.should_scan(asr, "zh"))
        self.assertEqual(
            AsrOcrReconciliationService.suspicious_cue_requests(
                asr, source_language="zh"
            ),
            [],
        )
        repaired, count = AsrOcrReconciliationService.reconcile(
            asr,
            [{"start": 1.0, "end": 2.0, "text": "等一下"}],
            source_language="zh",
        )
        self.assertEqual(count, 0)
        self.assertEqual(repaired, asr)

    def test_confirmed_speech_is_kept_when_source_has_no_burned_in_subtitle(self):
        asr = [{
            "start": 30.0,
            "end": 31.2,
            "text": "我明白了",
            "speech_detected": True,
            "speech_gate": "silero_vad",
        }]
        repaired, count = AsrOcrReconciliationService.reconcile(
            asr, [], source_language="zh",
        )
        self.assertEqual(count, 0)
        self.assertEqual(repaired, asr)

    def test_scan_gate_does_not_use_chinese_signs_for_other_languages(self):
        segments = [{"start": 0.0, "end": 1.0, "text": "下"}]
        self.assertTrue(AsrOcrReconciliationService.should_scan(segments, "zh"))
        self.assertTrue(AsrOcrReconciliationService.should_scan(segments, "auto"))
        self.assertFalse(AsrOcrReconciliationService.should_scan(segments, "en"))

    def test_repairs_supported_writing_systems_without_cross_script_replacement(self):
        examples = [
            ("ja", "て", "待って"),
            ("ko", "려", "기다려"),
            ("en", "wait", "Wait a moment"),
            ("vi", "đã", "Đợi đã"),
            ("ru", "жди", "Подожди"),
            ("ar", "قف", "توقف"),
            ("th", "รอ", "รอก่อน"),
        ]
        for language, partial, complete in examples:
            with self.subTest(language=language):
                repaired, count = AsrOcrReconciliationService.reconcile(
                    [{"start": 3.0, "end": 3.7, "text": partial}],
                    [{"start": 2.9, "end": 3.8, "text": complete}],
                    source_language=language,
                )
                self.assertEqual(count, 1)
                self.assertEqual(repaired[0]["text"], complete)

                cross_script, cross_count = AsrOcrReconciliationService.reconcile(
                    [{"start": 3.0, "end": 3.7, "text": partial}],
                    [{"start": 2.9, "end": 3.8, "text": "等一下"}],
                    source_language=language,
                )
                self.assertEqual(cross_count, 0)
                self.assertEqual(cross_script[0]["text"], partial)

    def test_latin_matching_uses_complete_words_not_substrings(self):
        repaired, count = AsrOcrReconciliationService.reconcile(
            [{"start": 1.0, "end": 1.5, "text": "he"}],
            [{"start": 1.0, "end": 1.5, "text": "The hero returns"}],
            source_language="en",
        )
        self.assertEqual(count, 0)
        self.assertEqual(repaired[0]["text"], "he")

    def test_only_suspicious_cue_windows_are_requested_for_ocr(self):
        ranges = AsrOcrReconciliationService.suspicious_time_ranges([
            {"start": 20.0, "end": 20.4, "text": "完整句子"},
            {"start": 10.0, "end": 10.4, "text": "下"},
            {"start": 11.0, "end": 11.2, "text": "走"},
        ])
        self.assertEqual(ranges, [(9.25, 11.95), (19.25, 21.15)])

    def test_requests_authoritative_short_and_sequence_long_verification(self):
        requests = AsrOcrReconciliationService.suspicious_cue_requests([
            {"start": 4.752, "end": 5.866, "text": "内 曹兄", "speech_detected": True},
            {"start": 33.446, "end": 36.500, "text": "样简单还我三的命啊", "speech_detected": True},
        ], source_language="zh")
        self.assertEqual([item["scan_mode"] for item in requests], ["authoritative", "sequence"])
        self.assertEqual((requests[1]["start"], requests[1]["end"]), (33.446, 36.5))

    def test_long_project_does_not_stop_ocr_verification_after_512_cues(self):
        source = [
            {
                "start": float(index),
                "end": float(index) + 0.6,
                "text": "需要核对字幕",
                "speech_detected": True,
            }
            for index in range(600)
        ]

        requests = AsrOcrReconciliationService.suspicious_cue_requests(
            source, source_language="zh"
        )

        self.assertEqual(len(requests), 600)
        self.assertAlmostEqual(requests[-1]["start"], 598.85)
        self.assertAlmostEqual(requests[-1]["end"], 599.75)

    def test_normal_length_hardsub_dialogue_is_verified_for_names_and_timing(self):
        requests = AsrOcrReconciliationService.suspicious_cue_requests([
            {"start": 45.436, "end": 47.572, "text": "你就是那个韩念川曹仲曾", "speech_detected": True},
            {"start": 47.612, "end": 49.804, "text": "草中层是你打的", "speech_detected": True},
        ], source_language="zh")

        self.assertEqual(len(requests), 2)
        self.assertEqual([item["scan_mode"] for item in requests], ["sequence", "sequence"])

    def test_two_second_cue_uses_dense_sequence_checkpoints(self):
        pairs = ocr_processor._representative_ocr_pairs(45.436, 47.572, scan_mode="sequence")
        self.assertGreaterEqual(len(pairs), 4)
        centers = [(pair[0] + pair[-1]) * 0.5 for pair in pairs]
        self.assertLessEqual(max(b - a for a, b in zip(centers, centers[1:])), 0.56)

    def test_exact_stable_ocr_aligns_early_asr_timing(self):
        asr = [{
            "start": 199.704,
            "end": 203.755,
            "text": "韩念川是吧",
            "speech_detected": True,
            "tts_group_start": 199.704,
            "tts_group_end": 203.755,
            "_audio_end": 201.2,
        }]
        ocr = [{
            "start": 199.704,
            "end": 202.229,
            "text": "金面金",
            "ocr_consensus_frames": 2,
            "ocr_scan_mode": "sequence",
        }, {
            "start": 202.229,
            "end": 203.207,
            "text": "韩念川是吧",
            "ocr_consensus_frames": 2,
            "ocr_scan_mode": "sequence",
        }]

        repaired, count = AsrOcrReconciliationService.reconcile(
            asr, ocr, source_language="zh"
        )

        self.assertEqual(count, 1)
        self.assertAlmostEqual(repaired[0]["start"], 202.229)
        self.assertAlmostEqual(repaired[0]["end"], 203.207)
        self.assertEqual(repaired[0]["text_source"], "ocr_timing_aligned")
        self.assertAlmostEqual(repaired[0]["asr_start_original"], 199.704)
        self.assertAlmostEqual(repaired[0]["tts_group_start"], 202.229)
        self.assertAlmostEqual(repaired[0]["tts_group_end"], 203.207)
        self.assertNotIn("_audio_end", repaired[0])

    def test_reconciliation_merges_flicker_duplicate_and_embedded_fragment(self):
        source = [
            {"start": 54.520, "end": 55.384, "text": "打了我的人还敢主动接我带队的任务"},
            {"start": 56.408, "end": 57.786, "text": "打了我的人还敢主动接我带队的任务"},
            {"start": 209.032, "end": 209.165, "text": "二人不成"},
            {"start": 209.165, "end": 212.344, "text": "你以为你还能斗得过我们父子二人不成"},
        ]

        normalized, changes = AsrOcrReconciliationService._normalize_reconciled_timeline(source)

        self.assertEqual(changes, 2)
        self.assertEqual(len(normalized), 2)
        self.assertEqual(normalized[0]["start"], 54.520)
        self.assertEqual(normalized[0]["end"], 57.786)
        self.assertEqual(normalized[1]["start"], 209.032)
        self.assertEqual(normalized[1]["text"], "你以为你还能斗得过我们父子二人不成")

    def test_reconciliation_merges_consecutive_ocr_spelling_variants(self):
        normalized, changes = AsrOcrReconciliationService._normalize_reconciled_timeline([
            {
                "start": 110.717,
                "end": 112.109,
                "text": "以极度暴力的手段暴虐悬镜使",
                "text_source": "ocr_reconciled_split",
            },
            {
                "start": 112.109,
                "end": 112.995,
                "text": "以概度最力的手段學信悬機使",
                "text_source": "ocr_reconciled_split",
            },
        ])

        self.assertEqual(changes, 1)
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["text"], "以极度暴力的手段暴虐悬镜使")
        self.assertEqual(normalized[0]["end"], 112.995)

    def test_reconciliation_merges_noisy_re_reads_of_one_caption_across_vad_pause(self):
        # One burned-in caption stayed on screen ~87.5-92.3s. The sequence scan
        # re-read it four times and each read garbled different glyphs
        # (``妙小不理``/``妙小不雅``/``莎小不延``/``沙小不延``). VAD split the
        # speech into two cues separated by a 0.27s pause, so the old gap <= 0.08
        # rule missed merging the 88.8 -> 89.07 boundary (text similarity 0.82).
        normalized, changes = AsrOcrReconciliationService._normalize_reconciled_timeline([
            {
                "start": 87.532,
                "end": 88.8,
                "text": "就这你的法相妙小不理",
                "text_source": "ocr_reconciled",
            },
            {
                "start": 89.068,
                "end": 90.42,
                "text": "就这你的法相莎小不延",
                "text_source": "ocr_reconciled",
            },
        ])

        self.assertEqual(changes, 1)
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["start"], 87.532)
        self.assertEqual(normalized[0]["end"], 90.42)
        self.assertEqual(normalized[0]["text"], "就这你的法相妙小不理")

    def test_reconciliation_keeps_distinct_ocr_captions_that_are_not_re_reads(self):
        normalized, changes = AsrOcrReconciliationService._normalize_reconciled_timeline([
            {
                "start": 100.0,
                "end": 101.5,
                "text": "以极度暴力的手段暴虐悬镜使",
                "text_source": "ocr_reconciled",
            },
            {
                "start": 101.8,
                "end": 103.2,
                "text": "他竟敢如此狂妄挑衅悬镜司",
                "text_source": "ocr_reconciled",
            },
        ])

        self.assertEqual(changes, 0)
        self.assertEqual(len(normalized), 2)

    def test_reconciled_timeline_has_no_overlapping_cues(self):
        normalized, changes = AsrOcrReconciliationService._normalize_reconciled_timeline([
            {"start": 154.492, "end": 156.492, "text": "在下赤炼刀宗宗主段赤炎"},
            {"start": 155.704, "end": 157.842, "text": "这位是犬子段炼"},
        ])

        self.assertEqual(changes, 1)
        self.assertEqual(normalized[0]["end"], normalized[1]["start"])

    def test_fuzzy_sequence_correction_uses_confirmed_ocr_timing(self):
        repaired, count = AsrOcrReconciliationService.reconcile(
            [{
                "start": 198.947,
                "end": 202.414,
                "text": "神兵韩念穿是吧你不",
                "speech_detected": True,
            }],
            [
                {"start": 200.130, "end": 201.304, "text": "金面金", "ocr_consensus_frames": 2, "ocr_scan_mode": "sequence"},
                {"start": 201.987, "end": 202.414, "text": "韩念川是吧", "ocr_consensus_frames": 2, "ocr_scan_mode": "sequence"},
            ],
            source_language="zh",
        )

        self.assertEqual(count, 1)
        self.assertEqual(repaired[0]["text"], "韩念川是吧")
        self.assertAlmostEqual(repaired[0]["start"], 201.987)
        self.assertAlmostEqual(repaired[0]["end"], 202.414)

    def test_sequence_ocr_does_not_shift_timing_when_text_differs(self):
        repaired, count = AsrOcrReconciliationService.reconcile(
            [{
                "start": 10.0,
                "end": 14.0,
                "text": "今天的天气真是不错啊",
                "speech_detected": True,
            }],
            [{
                "start": 10.5,
                "end": 11.5,
                "text": "客栈酒家",
                "ocr_consensus_frames": 2,
                "ocr_scan_mode": "sequence",
            }],
            source_language="zh",
        )
        self.assertEqual(count, 0)
        self.assertEqual(repaired[0]["text"], "今天的天气真是不错啊")
        self.assertEqual(repaired[0]["start"], 10.0)
        self.assertEqual(repaired[0]["end"], 14.0)

    def test_repairs_short_add_drop_and_homophone_examples(self):
        asr = [
            {"start": 4.752, "end": 5.866, "text": "内 曹兄", "speech_detected": True},
            {"start": 13.596, "end": 14.520, "text": "含羞可羞", "speech_detected": True},
            {"start": 64.476, "end": 65.017, "text": "爹", "speech_detected": True},
        ]
        ocr = [
            {"start": 4.6, "end": 6.0, "text": "曹兄", "ocr_consensus_frames": 2},
            {"start": 13.4, "end": 14.7, "text": "韩兄贺兄", "ocr_consensus_frames": 2},
            {"start": 64.3, "end": 65.2, "text": "地儿", "ocr_consensus_frames": 2},
        ]
        repaired, count = AsrOcrReconciliationService.reconcile(asr, ocr, source_language="zh")
        self.assertEqual(count, 3)
        self.assertEqual([item["text"] for item in repaired], ["曹兄", "韩兄贺兄", "地儿"])

    def test_splits_one_merged_asr_cue_from_stable_ocr_states(self):
        asr = [{
            "start": 68.156,
            "end": 72.500,
            "text": "你还有多余的儿子吗我一并杀给你看",
            "speech_detected": True,
        }]
        ocr = [
            {"start": 68.156, "end": 68.671, "text": "湖国", "ocr_consensus_frames": 2, "ocr_scan_mode": "sequence"},
            {"start": 68.156, "end": 70.328, "text": "你还有多余的儿子吗", "ocr_consensus_frames": 2, "ocr_scan_mode": "sequence"},
            {"start": 70.328, "end": 72.500, "text": "我一并杀给你看", "ocr_consensus_frames": 2, "ocr_scan_mode": "sequence"},
        ]
        repaired, count = AsrOcrReconciliationService.reconcile(asr, ocr, source_language="zh")
        self.assertEqual(count, 1)
        self.assertEqual([item["text"] for item in repaired], ["你还有多余的儿子吗", "我一并杀给你看"])
        self.assertEqual(repaired[0]["start"], 68.156)
        self.assertEqual(repaired[-1]["end"], 72.5)
        self.assertTrue(all(item["text_source"] == "ocr_reconciled_split" for item in repaired))

    def test_fast_ocr_keeps_one_tight_window_per_suspicious_cue(self):
        ranges = AsrOcrReconciliationService.suspicious_cue_ranges([
            {"start": 10.0, "end": 10.4, "text": "下"},
            {"start": 11.0, "end": 11.2, "text": "走"},
        ])
        self.assertEqual(ranges, [(9.85, 10.55), (10.85, 11.35)])

    def test_two_frame_consensus_rejects_disagreement_or_missing_text(self):
        self.assertEqual(
            ocr_processor._two_frame_ocr_consensus(["等一下", "等一下！"]),
            "等一下！",
        )
        self.assertEqual(
            ocr_processor._two_frame_ocr_consensus(["下", "等一下"]),
            "",
        )
        self.assertEqual(
            ocr_processor._two_frame_ocr_consensus(["等一下", ""]),
            "",
        )

    def test_spatial_filter_removes_corner_title_but_keeps_center_subtitle(self):
        class Result:
            txts = ("内", "曹兄")
            boxes = np.asarray([
                [[86, 0], [176, 0], [176, 89], [86, 89]],
                [[455, 74], [570, 72], [571, 144], [456, 146]],
            ], dtype=np.float32)

        self.assertEqual(
            ocr_processor._subtitle_lines_from_result(Result(), (173, 1024, 3)),
            ["曹兄"],
        )

    def test_sequence_sampling_adapts_to_cue_duration(self):
        pairs = ocr_processor._representative_ocr_pairs(33.446, 36.500, scan_mode="sequence")
        self.assertGreater(len(pairs), 4)
        self.assertTrue(all(len(pair) == 2 for pair in pairs))
        self.assertGreaterEqual(pairs[0][0], 33.446)
        self.assertLessEqual(pairs[-1][-1], 36.500)
        centers = [(pair[0] + pair[-1]) * 0.5 for pair in pairs]
        self.assertLessEqual(max(b - a for a, b in zip(centers, centers[1:])), 0.70)

    def test_long_vad_cue_samples_near_speech_onset_not_midpoint(self):
        positions = ocr_processor._representative_ocr_times(124.518, 129.410)
        self.assertEqual(len(positions), 2)
        self.assertLess(positions[0], 125.1)
        self.assertLess(positions[1], 125.4)

    def test_range_ocr_opens_video_once_and_returns_only_consensus(self):
        class FakeCapture:
            def __init__(self):
                self.read_count = 0
                self.released = False

            def get(self, prop):
                return 30.0

            def set(self, prop, value):
                return True

            def read(self):
                self.read_count += 1
                return True, np.ones((100, 200, 3), dtype=np.uint8) * 255

            def release(self):
                self.released = True

        capture = FakeCapture()
        progress = []
        with (
            patch.object(ocr_processor, "_open_video", return_value=capture) as open_video,
            patch.object(ocr_processor, "_load_ocr_engine", return_value=object()),
            patch.object(ocr_processor, "crop_subtitle_region", side_effect=lambda frame, region: frame),
            patch.object(ocr_processor, "_is_blank_region", return_value=False),
            patch.object(
                ocr_processor,
                "ocr_frame",
                side_effect=[["等一下"], ["等一下"], ["下"], ["等一下"]],
            ),
        ):
            result = ocr_processor.transcribe_video_ocr_ranges(
                "movie.mp4",
                [(1.0, 2.0), (3.0, 4.0)],
                progress_callback=lambda done, total: progress.append((done, total)),
            )

        open_video.assert_called_once_with("movie.mp4")
        self.assertTrue(capture.released)
        self.assertEqual(capture.read_count, 4)
        self.assertEqual(progress, [(1, 2), (2, 2)])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "等一下")
        self.assertEqual(result[0]["ocr_consensus_frames"], 2)

    def test_sequence_ocr_returns_three_dialogue_states_inside_one_vad_region(self):
        class FakeCapture:
            def __init__(self):
                self.position = 0

            def get(self, prop):
                return 30.0

            def set(self, prop, value):
                self.position = int(value)
                return True

            def read(self):
                return True, np.full((80, 160, 3), self.position, dtype=np.int32)

            def release(self):
                pass

        capture = FakeCapture()

        def fake_ocr(_engine, frame):
            frame_index = int(frame[0, 0, 0])
            if frame_index < 360:
                return ["你是谁"]
            if frame_index < 420:
                return ["我是谁与你无关"]
            return ["住手"]

        with (
            patch.object(ocr_processor, "_open_video", return_value=capture),
            patch.object(ocr_processor, "_load_ocr_engine", return_value=object()),
            patch.object(ocr_processor, "crop_subtitle_region", side_effect=lambda frame, region: frame),
            patch.object(ocr_processor, "_is_blank_region", return_value=False),
            patch.object(ocr_processor, "ocr_frame", side_effect=fake_ocr),
        ):
            result = ocr_processor.transcribe_video_ocr_ranges(
                "movie.mp4",
                [(10.0, 15.0)],
                expected_texts=["你是谁我是谁与你无关住手"],
                scan_modes=["sequence"],
            )

        self.assertEqual([item["text"] for item in result], [
            "你是谁", "我是谁与你无关", "住手",
        ])
        self.assertEqual(result[0]["start"], 10.0)
        self.assertEqual(result[-1]["end"], 15.0)

    def test_sequence_ocr_does_not_backdate_text_over_blank_checkpoints(self):
        class FakeCapture:
            def __init__(self):
                self.position = 0

            def get(self, prop):
                return 30.0

            def set(self, prop, value):
                self.position = int(value)
                return True

            def read(self):
                return True, np.full((80, 160, 3), self.position, dtype=np.int32)

            def release(self):
                pass

        capture = FakeCapture()

        def fake_ocr(_engine, frame):
            frame_index = int(frame[0, 0, 0])
            return ["韩念川是吧"] if 60 <= frame_index < 105 else []

        with (
            patch.object(ocr_processor, "_open_video", return_value=capture),
            patch.object(ocr_processor, "_load_ocr_engine", return_value=object()),
            patch.object(ocr_processor, "crop_subtitle_region", side_effect=lambda frame, region: frame),
            patch.object(ocr_processor, "_is_blank_region", return_value=False),
            patch.object(ocr_processor, "ocr_frame", side_effect=fake_ocr),
        ):
            result = ocr_processor.transcribe_video_ocr_ranges(
                "movie.mp4",
                [(0.0, 4.0)],
                expected_texts=["韩念川是吧"],
                scan_modes=["sequence"],
            )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "韩念川是吧")
        self.assertGreater(result[0]["start"], 1.0)
        self.assertLess(result[0]["end"], 4.0)


class SenseVoiceBoundaryTests(unittest.TestCase):
    def test_vad_boundaries_are_merged_and_padded(self):
        result = _pad_and_merge_vad_segments(
            [
                {"start": 1.00, "end": 1.30},
                {"start": 1.40, "end": 1.80},
                {"start": 3.00, "end": 3.20},
            ],
            4.0,
        )
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], {
            "start": 0.78, "end": 1.98,
            "speech_start": 1.0, "speech_end": 1.8,
        })
        self.assertEqual(result[1], {
            "start": 2.78, "end": 3.38,
            "speech_start": 3.0, "speech_end": 3.2,
        })

    def test_vietnamese_is_not_forced_through_chinese_decoder(self):
        self.assertEqual(_lang_code("vi"), "auto")
        self.assertEqual(_lang_code("zh-CN"), "zh")

    def test_only_native_sensevoice_languages_stay_on_sensevoice(self):
        for language in ("auto", "zh", "zh-CN", "yue", "en", "ja", "ko"):
            self.assertTrue(supports_language(language), language)
        for language in ("vi", "th", "id", "es", "fr", "de", "pt", "ru", "ar"):
            self.assertFalse(supports_language(language), language)
        for language in ("zh", "zh-CN", "yue", "en", "ja", "ko"):
            self.assertFalse(requires_multilingual_whisper(language), language)
        for language in ("auto", "vi", "th", "id", "es", "fr", "de", "pt", "ru", "ar"):
            self.assertTrue(requires_multilingual_whisper(language), language)

    def test_vietnamese_canonical_command_preserves_source_meaning(self):
        guarded, warnings = apply_translation_quality_guard(
            source_segments=[{"start": 1.0, "end": 2.0, "text": "住手"}],
            translated_texts=["Hãy dừng lại đi."],
            target_lang="vi",
        )
        self.assertEqual(guarded, ["Dừng tay!"])
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()

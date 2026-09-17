import os
import sys
import math
import struct
import tempfile
import unittest
import wave

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path[:0] = [os.path.join(ROOT, "app"), os.path.join(ROOT, "ui"), ROOT]

from app.services.segment_regroup_service import SegmentRegroupService
from ui.helpers.srt_helpers import (
    expand_short_cues_into_gaps,
    align_segments_to_video_start,
    segments_to_source_video_time,
)
from app.services.timeline_video_sequence import (
    clip_is_image,
    resolve_timeline_content_offset,
    is_already_timeline_relative,
    resolve_source_audio_position_ms,
    resolve_voice_export_delay_seconds,
)
from app.tts_processor import _insert_natural_prosody_pauses, normalize_text_for_tts
from app.ocr_processor import _subtitle_lines_from_result
from app.workflows.voice_workflow import predict_speed_ratios
from app.services.voice_timing_service import align_voice_clips, wav_duration
try:
    from app.engines.audio_mix_adapter import AudioMixAdapter
except ImportError:
    from engines.audio_mix_adapter import AudioMixAdapter


def _create_test_sine_wav(file_path: str, duration_sec: float = 1.0, sample_rate: int = 16000):
    num_samples = int(duration_sec * sample_rate)
    with wave.open(file_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for i in range(num_samples):
            val = int(32767.0 * 0.5 * math.sin(2.0 * math.pi * 440.0 * i / sample_rate))
            wf.writeframes(struct.pack("<h", val))


class TimingInvariantsTests(unittest.TestCase):

    def test_ripple_nudge_preserves_next_cue_duration_and_respects_gap(self):
        segments = [
            {"start": 10.0, "end": 10.4, "text": "你倒是挺大方的"},
            {"start": 10.48, "end": 11.68, "text": "好"},
            {"start": 14.0, "end": 15.0, "text": "第三句"},
        ]
        original_next_duration = round(segments[1]["end"] - segments[1]["start"], 3)
        res = SegmentRegroupService.expand_short_cues_into_gaps(segments, safe_gap_seconds=0.08)

        # Invariant 1: Cue 2 voice duration is strictly preserved
        after_next_duration = round(res[1]["voice_end"] - res[1]["voice_start"], 3)
        self.assertAlmostEqual(original_next_duration, after_next_duration, places=3)

        # Invariant 2: Cue 1 voice end does not collide with cue 2 voice start
        self.assertLessEqual(res[0]["voice_end"], res[1]["voice_start"])

        # Invariant 3: Cue 2 voice end does not collide with cue 3 sub start
        self.assertLessEqual(res[1]["voice_end"], res[2]["sub_start"])

        # Invariant 4: Subtitle timeline remains strictly immutable
        self.assertEqual(res[1]["start"], 10.48)
        self.assertEqual(res[1]["end"], 11.68)
        self.assertEqual(res[1]["sub_start"], 10.48)
        self.assertEqual(res[1]["sub_end"], 11.68)

        # Invariant 5: Voice shift is within available gap
        voice_shift = res[1]["voice_start"] - segments[1]["start"]
        self.assertGreater(voice_shift, 0.0)
        self.assertLessEqual(voice_shift, 14.0 - segments[1]["end"])

    def test_timing_invariants_hold_on_complex_stream(self):
        segments = [
            {"start": 0.2, "end": 0.5, "text": "Xin chào mọi người"},
            {"start": 0.55, "end": 0.9, "text": "Hôm nay thế nào"},
            {"start": 1.0, "end": 1.3, "text": "Tôi rất vui"},
            {"start": 3.0, "end": 3.4, "text": "Gặp lại các bạn sau chuỗi ngày dài"},
            {"start": 3.48, "end": 4.0, "text": "Thật tuyệt vời"},
            {"start": 6.0, "end": 6.3, "text": "Tạm biệt nhé"},
        ]
        res = SegmentRegroupService.expand_short_cues_into_gaps(segments, safe_gap_seconds=0.08)

        for i, cue in enumerate(res):
            self.assertGreaterEqual(cue["start"], 0.0, f"Cue {i} start must be >= 0")
            self.assertGreater(cue["end"], cue["start"], f"Cue {i} end must be > start")
            if i + 1 < len(res):
                self.assertLessEqual(
                    round(cue["end"], 3),
                    round(res[i + 1]["start"] + 0.001, 3),
                    f"Cue {i} end ({cue['end']}) must be <= Cue {i+1} start ({res[i+1]['start']})"
                )

    def test_intro_offset_applied_strictly_once(self):
        clips = [
            {"source": "intro.png", "timeline_start": 0.0, "timeline_end": 3.0},
            {"source": "main_video.mp4", "timeline_start": 3.0, "timeline_end": 15.0},
        ]
        content_offset = resolve_timeline_content_offset(clips)
        self.assertEqual(content_offset, 3.0)

        raw_cues = [
            {"start": 0.5, "end": 2.5, "text": "Lời thoại đầu tiên"},
            {"start": 3.0, "end": 5.0, "text": "Lời thoại thứ hai"},
        ]
        self.assertFalse(is_already_timeline_relative(raw_cues, content_offset))

        aligned = align_segments_to_video_start(raw_cues, first_video_start=content_offset)
        self.assertEqual(aligned[0]["start"], 3.5)
        self.assertEqual(aligned[0]["end"], 5.5)

        self.assertTrue(is_already_timeline_relative(aligned, content_offset))

        double_aligned = align_segments_to_video_start(aligned, first_video_start=content_offset)
        self.assertEqual(double_aligned[0]["start"], 3.5)
        self.assertEqual(double_aligned[0]["end"], 5.5)

    def test_content_offset_uses_dict_is_image_after_intro_trim(self):
        # Same shape as get_timeline_video_clips() → to_dict() after user trims 3s → 2s
        clips = [
            {
                "source": "intro.png",
                "timeline_start": 0.0,
                "timeline_end": 2.0,
                "is_image": True,
            },
            {
                "source": "main_video.mp4",
                "timeline_start": 2.0,
                "timeline_end": 14.0,
                "is_image": False,
            },
        ]
        self.assertTrue(clip_is_image(clips[0]))
        self.assertFalse(clip_is_image(clips[1]))
        self.assertEqual(resolve_timeline_content_offset(clips), 2.0)

        # getattr(dict, "is_image") is the production bug: it always looks like video.
        self.assertFalse(getattr(clips[0], "is_image", False))

        late_cues = [
            {"start": 5.0, "end": 7.0, "text": "First spoken line"},
        ]
        # Without force_offset the late first cue is mistaken for already-aligned.
        unforced = align_segments_to_video_start(late_cues, first_video_start=2.0)
        self.assertEqual(unforced[0]["start"], 5.0)

        imported = align_segments_to_video_start(late_cues, first_video_start=2.0, force_offset=True)
        self.assertEqual(imported[0]["start"], 7.0)
        self.assertEqual(imported[0]["end"], 9.0)
        self.assertTrue(imported[0].get("_timeline_relative"))

    def test_preview_sidecar_uses_local_time_after_intro_trim(self):
        """Voice WAV is source-video-relative. After trimming intro 3s → 2s,
        play at the first video frame must seek the sidecar to 0, not 2000/3000.
        """
        self.assertIsNone(
            resolve_source_audio_position_ms(800, baked_offset_ms=0, is_intro_image=True)
        )
        self.assertEqual(
            resolve_source_audio_position_ms(0, baked_offset_ms=0, is_intro_image=False),
            0,
        )
        self.assertEqual(
            resolve_source_audio_position_ms(1000, baked_offset_ms=0, is_intro_image=False),
            1000,
        )
        # Legacy WAV that still has a 3s intro baked in, current intro is 2s:
        # local 0 of the video should play WAV at 3000ms.
        self.assertEqual(
            resolve_source_audio_position_ms(0, baked_offset_ms=3000, is_intro_image=False),
            3000,
        )

        self.assertEqual(resolve_voice_export_delay_seconds(2.0, 0.0), 2.0)
        self.assertEqual(resolve_voice_export_delay_seconds(2.0, 2.0), 0.0)
        self.assertEqual(resolve_voice_export_delay_seconds(2.0, 3.0), -1.0)

        # Export delay must NOT be skipped just because the first spoken line
        # starts after the intro length (the old is_already_timeline_relative trap).
        late_cues = [{"start": 5.0, "end": 7.0, "text": "First spoken line"}]
        self.assertTrue(is_already_timeline_relative(late_cues, 2.0))
        self.assertEqual(resolve_voice_export_delay_seconds(2.0, 0.0), 2.0)

    def test_tts_mix_converts_timeline_cues_back_to_source_video_time(self):
        timeline_cues = [
            {
                "start": 2.32,
                "end": 4.50,
                "voice_start": 2.32,
                "voice_end": 4.50,
                "text": "Câu 1",
                "_timeline_relative": True,
            },
            {
                "start": 7.00,
                "end": 9.20,
                "voice_start": 7.00,
                "voice_end": 9.20,
                "text": "Câu muộn",
                "_timeline_relative": True,
            },
        ]
        mixed = segments_to_source_video_time(timeline_cues, 2.0)
        self.assertAlmostEqual(mixed[0]["start"], 0.32)
        self.assertAlmostEqual(mixed[0]["end"], 2.50)
        self.assertAlmostEqual(mixed[0]["voice_start"], 0.32)
        self.assertAlmostEqual(mixed[1]["start"], 5.00)
        self.assertAlmostEqual(mixed[1]["end"], 7.20)
        self.assertFalse(mixed[0].get("_timeline_relative"))
        # UI copy stays on the timeline clock.
        self.assertAlmostEqual(timeline_cues[0]["start"], 2.32)

    def test_prosody_pauses_rules(self):
        self.assertEqual(_insert_natural_prosody_pauses("bố và mẹ"), "bố và mẹ")
        self.assertEqual(_insert_natural_prosody_pauses("ăn để sống"), "ăn để sống")
        self.assertEqual(_insert_natural_prosody_pauses("cứ làm thì sẽ biết"), "cứ làm thì sẽ biết")

        long_sentence = "Anh ấy đã cố gắng hết sức mình trong suốt trận đấu nhưng kết quả cuối cùng vẫn không như mong đợi."
        result = _insert_natural_prosody_pauses(long_sentence)
        self.assertIn(", nhưng", result)

        compound_sent = "Hai người họ là bố và mẹ của đứa trẻ đang đứng khóc ở đằng kia từ sáng sớm hôm nay."
        res_compound = _insert_natural_prosody_pauses(compound_sent)
        self.assertNotIn(", và", res_compound)

    def test_ocr_preserves_two_line_subtitles_and_rejects_corner_watermarks(self):
        class MockResult:
            def __init__(self, txts, boxes):
                self.txts = txts
                self.boxes = boxes

        image_shape = (200, 1920, 3)
        mock_res = MockResult(
            txts=["第一行台词内容", "第二行台词内容", "LOGO"],
            boxes=[
                [[400, 20], [1520, 20], [1520, 50], [400, 50]],
                [[500, 120], [1420, 120], [1420, 150], [500, 150]],
                [[20, 10], [90, 10], [90, 40], [20, 40]],
            ]
        )
        lines = _subtitle_lines_from_result(mock_res, image_shape)
        self.assertIn("第一行台词内容", lines)
        self.assertIn("第二行台词内容", lines)
        self.assertNotIn("LOGO", lines)

    def test_chinese_to_vietnamese_short_cue_expansion_resolves_tts_rush(self):
        # Scenario: Cue 21 "你倒是挺大方的" -> "Anh hào phóng thật đấy."
        # Originally cut very short by VAD: 0.4s (10.0 to 10.4)
        raw_cues = [
            {"start": 8.0, "end": 9.4, "text": "Câu trước đó", "dubbing_vi": "Câu trước đó"},
            {"start": 10.0, "end": 10.4, "text": "你倒是挺大方的", "dubbing_vi": "Anh hào phóng thật đấy."},
            {"start": 10.5, "end": 11.5, "text": "好", "dubbing_vi": "Được rồi."},
            {"start": 13.0, "end": 14.5, "text": "Câu sau đó", "dubbing_vi": "Câu sau đó"},
        ]

        # Without expansion: 5 words in 0.4s -> extreme speed ratio
        raw_speed = predict_speed_ratios([dict(c) for c in raw_cues])
        self.assertGreater(raw_speed[1]["pre_speed_ratio"], 2.0)

        # With expansion (Leading + Ripple-nudge + Trailing):
        expanded = SegmentRegroupService.expand_short_cues_into_gaps(raw_cues, safe_gap_seconds=0.08)

        # Subtitle timeline remains strictly immutable
        self.assertEqual(expanded[1]["start"], 10.0)
        self.assertEqual(expanded[1]["end"], 10.4)
        self.assertEqual(expanded[1]["sub_start"], 10.0)
        self.assertEqual(expanded[1]["sub_end"], 10.4)

        # Voice window expands into silence
        exp_voice_duration = round(expanded[1]["voice_end"] - expanded[1]["voice_start"], 3)
        self.assertGreaterEqual(exp_voice_duration, 0.75)
        # Verify text was shortened for TTS to fit the duration:
        self.assertIn(expanded[1]["dubbing_vi"], ["Hào phóng ghê.", "Hào phóng thật.", "Hào phóng."])

        for c in expanded:
            c.pop("pre_speed_ratio", None)
        calculated = predict_speed_ratios(expanded)
        self.assertLessEqual(calculated[1]["pre_speed_ratio"], 1.15)

    def test_tight_boundary_does_not_force_expansion_and_shortens_text(self):
        tight_cues = [
            {"start": 8.0, "end": 9.95, "text": "Câu trước nói liên tục", "dubbing_vi": "Câu trước nói liên tục"},
            {"start": 10.0, "end": 10.422, "text": "你倒是挺大方的", "dubbing_vi": "Anh hào phóng thật đấy."},
            {"start": 10.48, "end": 12.0, "text": "Câu sau nói ngay lập tức", "dubbing_vi": "Câu sau nói ngay lập tức"},
        ]
        expanded = SegmentRegroupService.expand_short_cues_into_gaps(tight_cues, safe_gap_seconds=0.05)

        # 1. Must NOT force slot over adjacent dialogue
        self.assertLessEqual(expanded[1]["end"], 10.48)
        self.assertGreaterEqual(expanded[1]["start"], 9.95)

        # 2. Translation text for TTS must be shortened (e.g. to "Hào phóng ghê." or "Hào phóng quá!" or "Hào phóng.")
        shortened_tts = expanded[1]["dubbing_vi"]
        self.assertTrue(
            shortened_tts in ["Hào phóng ghê.", "Hào phóng thật.", "Hào phóng.", "Hào phóng quá!", "Hào phóng quá."]
            or len(shortened_tts.split()) < len("Anh hào phóng thật đấy.".split()),
            f"Expected shortened text, got: {shortened_tts}",
        )

        # 3. Subtitle text for visual display retains original source text
        self.assertEqual(expanded[1]["text"], "你倒是挺大方的")

    def test_subtitle_timeline_and_tts_speech_window_separation(self):
        cues = [
            {"start": 5.0, "end": 5.4, "text": "Lời thoại ngắn", "dubbing_vi": "Lời thoại ngắn"},
            {"start": 7.0, "end": 9.0, "text": "Lời thoại dài", "dubbing_vi": "Lời thoại dài"},
        ]
        expanded = SegmentRegroupService.expand_short_cues_into_gaps(cues, safe_gap_seconds=0.08)

        # Subtitle timeline retains original start on video (sub_start)
        self.assertEqual(expanded[0]["sub_start"], 5.0)
        self.assertEqual(expanded[0]["sub_end"], 5.4)
        self.assertEqual(expanded[0]["start"], 5.0)
        self.assertEqual(expanded[0]["end"], 5.4)

        # Voice window has expanded into the trailing silence gap
        self.assertGreaterEqual(expanded[0]["voice_end"], 5.8)
        self.assertLessEqual(expanded[0]["voice_end"], 7.0 - 0.08)

    # --- SPECIFIC UNIT TEST 1: Impossible short slot (0.422s) ---
    def test_impossible_short_slot_marks_timing_conflict_without_excessive_speed_or_truncation(self):
        """0.422s tight slot between adjacent dialogue.
        Cannot fit even 3-word phrase at <= 1.20x.
        Must set timing_conflict = True, fit_quality = 'overflow', and never exceed speed or truncate speech.
        """
        tight_cues = [
            {"start": 8.0, "end": 9.92, "text": "Câu trước nói liên tục", "dubbing_vi": "Câu trước nói liên tục"},
            {"start": 10.0, "end": 10.422, "text": "你倒是挺大方的", "dubbing_vi": "Anh hào phóng thật đấy."},
            {"start": 10.50, "end": 12.0, "text": "Câu sau nói ngay", "dubbing_vi": "Câu sau nói ngay"},
            {"start": 12.05, "end": 14.0, "text": "Khóa đuôi", "dubbing_vi": "Khóa đuôi"},
        ]
        expanded = SegmentRegroupService.expand_short_cues_into_gaps(tight_cues, safe_gap_seconds=0.08)
        cue = expanded[1]

        # 1. Subtitle timeline is strictly IMMUTABLE
        self.assertEqual(cue["start"], 10.0)
        self.assertEqual(cue["end"], 10.422)
        self.assertEqual(cue["sub_start"], 10.0)
        self.assertEqual(cue["sub_end"], 10.422)

        # 2. Text shortened to shortest viable candidate
        self.assertTrue(
            cue["dubbing_vi"] in ["Hào phóng ghê.", "Hào phóng thật.", "Hào phóng.", "Hào phóng quá!", "Hào phóng quá."]
            or len(cue["dubbing_vi"].split()) < len("Anh hào phóng thật đấy.".split()),
            f"Expected shortened text, got: {cue['dubbing_vi']}",
        )

        # 3. Because 0.422s cannot comfortably fit 3 words at <= 1.20x (requires ~1.54x),
        # it is marked as timing_conflict = True and overflow
        self.assertTrue(cue.get("timing_conflict"))
        self.assertEqual(cue.get("fit_quality"), "overflow")
        self.assertGreater(cue.get("overflow_seconds", 0.0), 0.0)

    # --- SPECIFIC UNIT TEST 2: Ripple chain drift limit across 10 cues ---
    def test_ripple_chain_prevents_cumulative_drift_across_many_cues(self):
        """10 chained cues cannot drift cumulatively beyond MAX_CUMULATIVE_DRIFT (0.20s)."""
        cues = []
        for i in range(10):
            s = i * 1.0
            e = s + 0.92
            cues.append({
                "start": s,
                "end": e,
                "text": f"Câu thứ {i+1} cần kéo dài",
                "dubbing_vi": f"Câu thứ {i+1} cần kéo dài hơn nữa nha",
            })
        cues.append({"start": 16.0, "end": 17.0, "text": "Xa tít", "dubbing_vi": "Xa tít"})

        expanded = SegmentRegroupService.expand_short_cues_into_gaps(cues, safe_gap_seconds=0.08)

        for i in range(10):
            cue = expanded[i]
            # Subtitle timeline is strictly invariant
            self.assertEqual(cue["start"], cues[i]["start"])
            self.assertEqual(cue["end"], cues[i]["end"])
            self.assertEqual(cue["sub_start"], cues[i]["start"])
            self.assertEqual(cue["sub_end"], cues[i]["end"])
            # Voice drift from subtitle onset must never exceed MAX_CUMULATIVE_DRIFT (0.20s)
            drift = round(cue["voice_start"] - cue["sub_start"], 3)
            self.assertLessEqual(
                drift,
                SegmentRegroupService.MAX_CUMULATIVE_DRIFT + 0.001,
                f"Cue {i} drift ({drift:.3f}s) exceeded MAX_CUMULATIVE_DRIFT",
            )

    # --- SPECIFIC UNIT TEST 3: Real synthesized audio duration and time stretch invariants ---
    def test_real_synthesized_duration_and_time_stretch_invariants(self):
        """When synthesized speech is 1.0s and slot is 0.70s (needs 1.43x):
        - Speed is clamped to HARD_MAX_SPEED (1.20x)
        - Output audio is NOT truncated by slicing wav[:samples] or fade-out cutting
        - _tts_overflow is flagged
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            wav_path = os.path.join(tmp_dir, "speech_1000ms.wav")
            _create_test_sine_wav(wav_path, duration_sec=1.0, sample_rate=16000)

            segments = [
                {
                    "voice_start": 1.0,
                    "voice_end": 1.70,  # 0.70s slot
                    "voice_file": wav_path,
                }
            ]
            engine = AudioMixAdapter()
            fitted = align_voice_clips(
                segments=segments,
                wavs=[wav_path],
                engine=engine,
                tmp_dir=tmp_dir,
                max_fit_speed=1.20,
            )

            # Stretched at max 1.20x: 1.0s / 1.20 = ~0.833s
            actual_dur = wav_duration(fitted[0])
            self.assertGreater(actual_dur, 0.75, "Audio must not be truncated to the 0.70s slot!")
            self.assertTrue(segments[0].get("_tts_overflow"), "Must flag _tts_overflow")
            self.assertGreater(segments[0].get("_tts_overflow_seconds", 0.0), 0.05)

    # --- SPECIFIC UNIT TEST 4: Semantic shortening safety (negations & digits) ---
    def test_semantic_shortening_preserves_negation_and_entities(self):
        """Negation words ('không', 'chưa', 'đừng', 'chẳng') and digits must never be dropped."""
        # 1. Negation dropped -> invalid
        self.assertFalse(SegmentRegroupService.is_semantic_shortening_safe("Tôi không bao giờ làm thế", "Tôi làm thế"))
        self.assertFalse(SegmentRegroupService.is_semantic_shortening_safe("Chưa từng thấy chuyện này", "Từng thấy chuyện này"))
        self.assertFalse(SegmentRegroupService.is_semantic_shortening_safe("Đừng đi vào đó", "Đi vào đó"))
        self.assertFalse(SegmentRegroupService.is_semantic_shortening_safe("Chẳng có việc gì đâu", "Có việc gì đâu"))

        # 2. Digits dropped -> invalid
        self.assertFalse(SegmentRegroupService.is_semantic_shortening_safe("Tôi có 500 nghìn", "Tôi có nghìn"))
        self.assertTrue(SegmentRegroupService.is_semantic_shortening_safe("Tôi có 500 nghìn", "Có 500 nghìn"))

        # 3. All generated candidates preserve safety
        cands = SegmentRegroupService.generate_shorten_candidates("Tôi không bao giờ làm điều này đâu nhé")
        for cand in cands:
            self.assertTrue(
                SegmentRegroupService.is_semantic_shortening_safe("Tôi không bao giờ làm điều này đâu nhé", cand),
                f"Candidate '{cand}' dropped negation from original",
            )

    # --- SPECIFIC UNIT TEST 5: Subtitle timeline strictly immutable ---
    def test_subtitle_timeline_strictly_immutable_after_voice_optimization(self):
        """sub_start, sub_end, start, end must be 100% invariant before and after optimization."""
        cues = [
            {"start": 0.0, "end": 0.4, "text": "Câu 1", "dubbing_vi": "Câu 1 dịch"},
            {"start": 0.48, "end": 1.2, "text": "Câu 2", "dubbing_vi": "Câu 2 dịch dài"},
            {"start": 3.0, "end": 3.3, "text": "Câu 3", "dubbing_vi": "Câu 3 dịch"},
            {"start": 5.0, "end": 5.5, "text": "Câu 4", "dubbing_vi": "Câu 4 dịch"},
        ]
        expanded = SegmentRegroupService.expand_short_cues_into_gaps(cues, safe_gap_seconds=0.08)

        for orig, exp in zip(cues, expanded):
            self.assertEqual(exp["start"], orig["start"])
            self.assertEqual(exp["end"], orig["end"])
            self.assertEqual(exp["sub_start"], orig["start"])
            self.assertEqual(exp["sub_end"], orig["end"])


    def test_full_sentence_is_never_truncated_to_fragments(self):
        """Even in an ultra-short slot (0.3s) with adjacent speech,
        the full sentence text must NEVER be butchered down to a 2-word fragment.
        All words must remain intact for TTS synthesis.
        """
        cues = [
            {"start": 0.0, "end": 0.9, "text": "Câu trước", "dubbing_vi": "Câu trước."},
            {"start": 0.95, "end": 1.25, "text": "1 tệ còn chẳng đủ tiền mì", "dubbing_vi": "1 tệ còn chẳng đủ tiền mì."},
            {"start": 1.30, "end": 2.5, "text": "Câu sau", "dubbing_vi": "Câu sau."},
        ]
        expanded = SegmentRegroupService.expand_short_cues_into_gaps(cues, safe_gap_seconds=0.04)
        target_cue = expanded[1]

        # The full sentence text must be preserved: "1 tệ còn chẳng đủ tiền mì."
        # It must NOT be chopped down to "1 tệ." or "1 tệ còn."
        self.assertEqual(target_cue["dubbing_vi"], "1 tệ còn chẳng đủ tiền mì.")
        self.assertEqual(target_cue["tts_text"], "1 tệ còn chẳng đủ tiền mì.")
        # Marked as overflow so audio mixer will accommodate full speech
        self.assertTrue(target_cue.get("timing_conflict"))
        self.assertEqual(target_cue.get("fit_quality"), "overflow")


if __name__ == "__main__":
    unittest.main()



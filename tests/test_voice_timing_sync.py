import os
import math
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "app")]

from app.audio_mixer import (
    build_voice_track_from_srt_segments,
    cap_wav_to_duration,
    fit_wav_to_duration,
    ffprobe_wav_duration,
    mute_voice_windows,
)
from app.workflows.voice_workflow import VoiceWorkflow
from app.services.voice_timing_service import align_voice_clips


def _make_silent_wav(path: str, duration: float, sample_rate: int = 16000) -> None:
    with wave.open(path, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(b"\x00\x00" * int(duration * sample_rate))


def _make_tone_wav(path: str, duration: float, sample_rate: int = 16000) -> None:
    frames = bytearray()
    for index in range(int(duration * sample_rate)):
        sample = int(8000 * math.sin(2.0 * math.pi * 440.0 * index / sample_rate))
        frames.extend(struct.pack("<h", sample))
    with wave.open(path, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(bytes(frames))


class VoiceTimingSyncTests(unittest.TestCase):
    def test_prepare_keeps_silent_rows_and_stable_source_identity_when_sorting(self):
        workflow = VoiceWorkflow(str(ROOT))
        prepared = workflow._prepare_segments_for_tts(
            [
                {"start": 2.0, "end": 3.0, "text": "Second", "original_text": "第二"},
                {"start": 0.0, "end": 1.0, "text": "[music]", "original_text": "[music]"},
            ],
            log=False,
        )

        self.assertEqual(len(prepared), 2)
        self.assertEqual([item["_voice_source_index"] for item in prepared], [1, 0])
        self.assertTrue(prepared[0]["tts_suppressed"])
        self.assertEqual(workflow._segment_tts_text(prepared[0]), "")

    def test_smart_mode_automatically_speeds_extreme_cue_without_queueing(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "long.wav")
            _make_tone_wav(source, 2.4)
            segments = [{"start": 4.0, "end": 5.0, "text": "A complete long sentence"}]
            workflow = VoiceWorkflow(str(ROOT))

            fitted = align_voice_clips(
                segments=segments,
                wavs=[source],
                engine=workflow.engine_runtime,
                tmp_dir=folder,
                mode="smart",
            )

            self.assertLessEqual(ffprobe_wav_duration(fitted[0]), 1.002)
            self.assertEqual(segments[0]["_audio_start"], 4.0)
            self.assertLessEqual(segments[0]["_audio_end"], 5.002)
            self.assertGreater(segments[0]["_tts_metrics"]["fit_speed_ratio"], 2.0)
            self.assertNotIn("voice_queue_delay", segments[0]["_tts_metrics"])

    def test_vietnamese_smart_fit_does_not_overcompress_short_syllables(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "vietnamese_source.wav")
            _make_tone_wav(source, 2.415)
            segments = [{
                "start": 707.6,
                "end": 709.7,
                "text": "Tao có đồ tốt cho mày! Chờ chút.",
                "_tts_metrics": {"duration_sec": 2.1, "speech_cost": 2, "attempt_count": 1},
            }]
            workflow = VoiceWorkflow(str(ROOT))

            fitted = workflow._apply_safe_timing_polish(
                segments=segments,
                wavs=[source],
                tmp_dir=folder,
                voice_speed=1.0,
                sync_mode="Smart",
            )

            # The previous 1.15x hard-coded fit reduced this exact cue to
            # about 2.10s and made Piper swallow Vietnamese final consonants.
            # Preserve at least the duration produced by the 1.10x safety cap.
            self.assertGreaterEqual(ffprobe_wav_duration(fitted[0]), 2.17)
            self.assertLessEqual(ffprobe_wav_duration(fitted[0]), 2.25)
            self.assertEqual(segments[0].get("action_taken"), "speed_light")

    def test_dense_english_run_is_uniformly_sped_up_before_queueing(self):
        with tempfile.TemporaryDirectory() as folder:
            wavs = []
            for index in range(3):
                path = os.path.join(folder, f"dense_{index}.wav")
                _make_tone_wav(path, 2.0)
                wavs.append(path)
            segments = [
                {"start": 0.0, "end": 1.5, "text": "First English sentence."},
                {"start": 1.5, "end": 3.0, "text": "Second English sentence."},
                {"start": 3.0, "end": 4.5, "text": "Third English sentence."},
            ]
            workflow = VoiceWorkflow(str(ROOT))

            fitted = workflow._fit_dense_english_voice_runs(
                segments=segments,
                wavs=wavs,
                tmp_dir=folder,
                sync_mode="Smart",
                voice_name="en_US-lessac-medium",
                requested_speed=1.0,
            )

            durations = [ffprobe_wav_duration(path) for path in fitted]
            self.assertTrue(all(duration < 1.55 for duration in durations))
            self.assertTrue(all(duration > 1.40 for duration in durations))
            self.assertTrue(all("dense_run_fit" in segment.get("action_taken", "") for segment in segments))
            self.assertTrue(all(segment.get("tts_duration", 0.0) < 1.55 for segment in segments))
            self.assertTrue(all("dense_run_speed_ratio" in segment.get("_tts_metrics", {}) for segment in segments))

    def test_dense_fit_does_not_change_non_english_voice(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "vietnamese.wav")
            _make_tone_wav(source, 2.0)
            segment = {"start": 0.0, "end": 1.0, "text": "Xin chào"}
            workflow = VoiceWorkflow(str(ROOT))

            fitted = workflow._fit_dense_english_voice_runs(
                segments=[segment],
                wavs=[source],
                tmp_dir=folder,
                sync_mode="Smart",
                voice_name="ngochuyen",
                requested_speed=1.0,
            )

            self.assertEqual(fitted, [source])
            self.assertNotIn("dense_run_fit", segment.get("action_taken", ""))

    def test_hard_duration_cap_uses_a_short_fade_and_hits_deadline(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "long.wav")
            capped = os.path.join(folder, "capped.wav")
            _make_tone_wav(source, 2.0)

            result = cap_wav_to_duration(
                input_wav_path=source,
                output_wav_path=capped,
                target_duration_seconds=1.0,
            )

            self.assertEqual(result, capped)
            self.assertAlmostEqual(ffprobe_wav_duration(capped), 1.0, delta=0.05)

    def test_voice_workflow_fits_each_cue_without_shifting_the_next_one(self):
        with tempfile.TemporaryDirectory() as folder:
            first = os.path.join(folder, "first.wav")
            second = os.path.join(folder, "second.wav")
            _make_tone_wav(first, 2.0)
            _make_tone_wav(second, 0.5)
            segments = [
                {"start": 0.0, "end": 0.8, "text": "First"},
                {"start": 1.0, "end": 1.5, "text": "Second"},
            ]
            workflow = VoiceWorkflow(str(ROOT))

            wavs = workflow._enforce_non_overlapping_voice_windows(
                segments=segments,
                wavs=[first, second],
                tmp_dir=folder,
            )

            self.assertLessEqual(ffprobe_wav_duration(wavs[0]), 0.802)
            self.assertAlmostEqual(segments[0]["_audio_start"], 0.0, delta=0.001)
            self.assertAlmostEqual(segments[1]["_audio_start"], 1.0, delta=0.001)
            self.assertNotIn("voice_queue", segments[1].get("action_taken", ""))

    def test_mixer_rejects_unfitted_dense_cues_instead_of_shifting_them(self):
        with tempfile.TemporaryDirectory() as folder:
            first = os.path.join(folder, "first.wav")
            second = os.path.join(folder, "second.wav")
            output = os.path.join(folder, "voice.wav")
            _make_tone_wav(first, 2.0)
            _make_tone_wav(second, 0.5)
            segments = [
                {"start": 0.0, "end": 0.8},
                {"start": 1.0, "end": 1.5},
            ]

            with self.assertRaisesRegex(ValueError, "exceeds subtitle end"):
                build_voice_track_from_srt_segments(
                    segments=segments,
                    tts_wav_paths=[first, second],
                    output_wav_path=output,
                )

    def test_editing_one_subtitle_mutes_only_that_voice_window(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "voice.wav")
            partial = os.path.join(folder, "partial.wav")
            _make_tone_wav(source, 3.0)
            result = mute_voice_windows(
                input_wav_path=source,
                segments=[
                    {"start": 0.0, "end": 1.0, "_audio_start": 0.0, "_audio_end": 1.0},
                    {"start": 1.0, "end": 2.0, "_audio_start": 1.0, "_audio_end": 2.0},
                    {"start": 2.0, "end": 3.0, "_audio_start": 2.0, "_audio_end": 3.0},
                ],
                changed_indices={1},
                output_wav_path=partial,
            )

            self.assertEqual(result, partial)
            self.assertAlmostEqual(ffprobe_wav_duration(partial), 3.0, delta=0.03)
            with wave.open(partial, "rb") as rendered:
                rate = rendered.getframerate()
                rendered.setpos(int(0.2 * rate))
                first = rendered.readframes(int(0.2 * rate))
                rendered.setpos(int(1.2 * rate))
                edited = rendered.readframes(int(0.2 * rate))
                rendered.setpos(int(2.2 * rate))
                third = rendered.readframes(int(0.2 * rate))
            self.assertGreater(max(abs(value) for value in struct.unpack(f"<{len(first) // 2}h", first)), 0)
            self.assertEqual(max(abs(value) for value in struct.unpack(f"<{len(edited) // 2}h", edited)), 0)
            self.assertGreater(max(abs(value) for value in struct.unpack(f"<{len(third) // 2}h", third)), 0)

    def test_smart_fit_really_slows_short_speech_to_subtitle_duration(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "short.wav")
            fitted = os.path.join(folder, "fitted.wav")
            _make_silent_wav(source, 1.6)

            result = fit_wav_to_duration(
                input_wav_path=source,
                output_wav_path=fitted,
                target_duration_seconds=2.0,
                mode="smart",
            )

            self.assertEqual(result, fitted)
            self.assertAlmostEqual(ffprobe_wav_duration(fitted), 2.0, delta=0.12)

    def test_smart_fit_speeds_long_speech_without_cutting_words(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "long.wav")
            fitted = os.path.join(folder, "fitted.wav")
            _make_silent_wav(source, 2.0)

            result = fit_wav_to_duration(
                input_wav_path=source,
                output_wav_path=fitted,
                target_duration_seconds=1.6,
                mode="smart",
            )

            self.assertEqual(result, fitted)
            self.assertAlmostEqual(ffprobe_wav_duration(fitted), 1.6, delta=0.12)

    def test_timeline_mode_keeps_extreme_overrun_for_safe_queueing(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "long.wav")
            fitted = os.path.join(folder, "timeline.wav")
            _make_tone_wav(source, 2.0)

            result = fit_wav_to_duration(
                input_wav_path=source,
                output_wav_path=fitted,
                target_duration_seconds=0.8,
                mode="timeline",
            )

            self.assertEqual(result, source)
            self.assertAlmostEqual(ffprobe_wav_duration(result), 2.0, delta=0.03)

    def test_very_short_speech_keeps_source_subtitle_window(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "very_short.wav")
            _make_silent_wav(source, 0.6)
            segments = [{"start": 1.0, "end": 3.0, "text": "A long subtitle"}]
            workflow = VoiceWorkflow(str(ROOT))

            workflow._extend_segment_ends_to_audio(
                segments=segments,
                wavs=[source],
                sync_mode="Smart",
            )

            self.assertAlmostEqual(segments[0]["_audio_end"], 1.6, delta=0.02)
            self.assertAlmostEqual(segments[0]["end"], 3.0, delta=0.03)
            self.assertNotIn("_original_end", segments[0])
            self.assertNotIn("subtitle_sync", segments[0].get("action_taken", ""))

    def test_unavoidably_long_speech_keeps_visual_window_and_tracks_audio_end(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "very_long.wav")
            _make_silent_wav(source, 3.0)
            segments = [{"start": 1.0, "end": 3.0, "text": "Long speech"}]
            workflow = VoiceWorkflow(str(ROOT))

            with self.assertRaisesRegex(ValueError, "must be aligned"):
                workflow._extend_segment_ends_to_audio(
                    segments=segments,
                    wavs=[source],
                    sync_mode="Smart",
                )
            self.assertAlmostEqual(segments[0]["end"], 3.0, delta=0.02)

    def test_long_speech_is_fitted_without_moving_visual_or_audio_cues(self):
        with tempfile.TemporaryDirectory() as folder:
            first = os.path.join(folder, "first_long.wav")
            second = os.path.join(folder, "second.wav")
            _make_silent_wav(first, 3.0)
            _make_silent_wav(second, 1.0)
            segments = [
                {"start": 1.0, "end": 2.0, "text": "First"},
                {"start": 2.2, "end": 3.2, "text": "Second"},
            ]
            workflow = VoiceWorkflow(str(ROOT))

            fitted = workflow._enforce_non_overlapping_voice_windows(
                segments=segments,
                wavs=[first, second],
                tmp_dir=folder,
            )
            workflow._extend_segment_ends_to_audio(
                segments=segments,
                wavs=fitted,
                sync_mode="Smart",
            )

            self.assertLessEqual(ffprobe_wav_duration(fitted[0]), 1.002)
            self.assertAlmostEqual(segments[0]["end"], 2.0, delta=0.02)
            self.assertAlmostEqual(segments[1]["start"], 2.2, delta=0.02)
            self.assertAlmostEqual(segments[0]["_audio_start"], 1.0, delta=0.002)
            self.assertAlmostEqual(segments[1]["_audio_start"], 2.2, delta=0.002)

    def test_requested_voice_speed_is_applied_before_final_smart_sync(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "speech.wav")
            _make_tone_wav(source, 2.0)
            segments = [{"start": 0.0, "end": 2.0, "text": "Test speech"}]
            workflow = VoiceWorkflow(str(ROOT))

            wavs = workflow._apply_safe_timing_polish(
                segments=segments,
                wavs=[source],
                tmp_dir=folder,
                voice_speed=1.2,
                sync_mode="Smart",
            )
            _, wavs = workflow._apply_deficit_timing_polish(
                segments=segments,
                wavs=wavs,
                tmp_dir=folder,
                sync_mode="Smart",
            )

            self.assertAlmostEqual(ffprobe_wav_duration(wavs[0]), 2.0, delta=0.15)


if __name__ == "__main__":
    unittest.main()

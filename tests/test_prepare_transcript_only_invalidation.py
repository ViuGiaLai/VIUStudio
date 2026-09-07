from __future__ import annotations

import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
if APP not in sys.path:
    sys.path.insert(0, APP)

from core.state import ProjectState
from workflows.prepare_workflow import PrepareWorkflow


class PrepareTranscriptOnlyInvalidationTests(unittest.TestCase):
    def test_audio_enhancement_signature_is_stable_until_input_changes(self):
        import tempfile

        from services.project_service import ProjectService

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = os.path.join(temp_dir, "audio.wav")
            with open(audio_path, "wb") as handle:
                handle.write(b"first audio payload")
            service = ProjectService(temp_dir)
            first = service.build_audio_enhancement_signature(
                audio_path, filter_chain="afftdn,loudnorm"
            )
            second = service.build_audio_enhancement_signature(
                audio_path, filter_chain="afftdn,loudnorm"
            )
            changed_recipe = service.build_audio_enhancement_signature(
                audio_path, filter_chain="loudnorm"
            )
            with open(audio_path, "ab") as handle:
                handle.write(b" changed")
            changed_audio = service.build_audio_enhancement_signature(
                audio_path, filter_chain="afftdn,loudnorm"
            )

        self.assertEqual(first, second)
        self.assertNotEqual(first, changed_recipe)
        self.assertNotEqual(first, changed_audio)

    def test_original_transcript_detaches_all_stale_downstream_output(self):
        state = ProjectState(
            project_id="example",
            project_root=os.path.join(ROOT, "temp", "example"),
            input_video="video.mp4",
        )
        for name in (
            "translation_raw",
            "translation_refined",
            "translation_final",
            "subtitle_translated_srt",
            "srt_translated",
            "voice_vi",
            "voice_segments",
            "mixed_vi",
            "preview_video",
            "preview_video_5s",
            "preview_frame",
            "final_video",
        ):
            state.artifacts[name] = f"old-{name}"
        state.artifacts["subtitle_original_srt"] = "current-original.srt"
        state.settings.update(
            translation_signature="old-translation",
            voice_signature="old-voice",
            export_signature="old-export",
            voice_track_partial=True,
        )
        state.steps.update(
            translate_raw="done",
            refine_translation="done",
            generate_tts="done",
            mix_audio="done",
            export="running",
            build_subtitle="done",
        )

        PrepareWorkflow._invalidate_downstream_after_original_transcript(state)

        self.assertEqual(state.artifacts, {"subtitle_original_srt": "current-original.srt"})
        self.assertNotIn("translation_signature", state.settings)
        self.assertNotIn("voice_signature", state.settings)
        self.assertNotIn("export_signature", state.settings)
        self.assertFalse(state.settings["voice_track_partial"])
        self.assertEqual(state.steps["translate_raw"], "skipped")
        self.assertEqual(state.steps["refine_translation"], "skipped")
        self.assertEqual(state.steps["generate_tts"], "pending")
        self.assertEqual(state.steps["mix_audio"], "pending")
        self.assertEqual(state.steps["export"], "pending")
        self.assertEqual(state.steps["build_subtitle"], "done")


if __name__ == "__main__":
    unittest.main()

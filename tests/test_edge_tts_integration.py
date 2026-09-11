import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "app"), str(ROOT / "ui"), str(ROOT)]

from runtime_paths import workspace_root
from services.resource_download_service import ResourceDownloadService
from services.voice_catalog_service import VoiceCatalogService
from ui.features.speaker_voice import SpeakerVoiceMixin
import tts_processor


class EdgeTTSIntegrationTests(unittest.TestCase):
    def test_catalog_exposes_vietnamese_and_curated_english_voices(self):
        voices = VoiceCatalogService(workspace_root()).load_catalog()
        edge_voices = [voice for voice in voices if voice.get("provider") == "edge"]

        self.assertEqual(len(edge_voices), 16)
        self.assertEqual({voice.get("language") for voice in edge_voices}, {"vi", "en"})
        self.assertIn("edge:vi-VN-HoaiMyNeural", {voice.get("id") for voice in edge_voices})
        self.assertIn("edge:en-US-AriaNeural", {voice.get("id") for voice in edge_voices})
        self.assertTrue(all("Edge Online" in str(voice.get("name")) for voice in edge_voices))

    def test_edge_runtime_validation_does_not_require_a_local_model(self):
        service = ResourceDownloadService(workspace_root())
        with patch("services.resource_download_service.importlib.util.find_spec", return_value=object()):
            self.assertEqual(service.validate_tts_voice_runtime("edge:vi-VN-HoaiMyNeural"), [])

    def test_edge_runtime_validation_reports_missing_python_package(self):
        service = ResourceDownloadService(workspace_root())
        with patch("services.resource_download_service.importlib.util.find_spec", return_value=None):
            issues = service.validate_tts_voice_runtime("edge:en-US-AriaNeural")
        self.assertEqual(issues[0][0], "tts:edge")

    def test_runtime_routes_dynamic_edge_voice_without_piper_fallback(self):
        progress = []
        with tempfile.TemporaryDirectory() as folder, patch.object(
            tts_processor,
            "edge_tts_to_wav_16k_mono",
            return_value=str(Path(folder) / "edge.wav"),
        ) as synthesize:
            result = tts_processor.synthesize_text_to_wav_16k_mono(
                text="Xin chào",
                wav_path=str(Path(folder) / "edge.wav"),
                voice="edge:vi-VN-HoaiMyNeural",
                speed=1.1,
                tmp_dir=folder,
                on_progress=progress.append,
            )

        self.assertTrue(result.endswith("edge.wav"))
        self.assertEqual(synthesize.call_args.kwargs["voice"], "vi-VN-HoaiMyNeural")
        self.assertEqual(synthesize.call_args.kwargs["rate"], "+10%")
        self.assertFalse(any("fallback" in str(message).lower() for message in progress))

    def test_unknown_voice_fails_instead_of_substituting_piper(self):
        with tempfile.TemporaryDirectory() as folder, self.assertRaisesRegex(
            ValueError, "will not substitute"
        ):
            tts_processor.synthesize_text_to_wav_16k_mono(
                text="This must not use another voice",
                wav_path=str(Path(folder) / "wrong.wav"),
                voice="missing-provider:missing-voice",
                tmp_dir=folder,
            )

    def test_speaker_override_cannot_cross_the_selected_engine(self):
        class Harness(SpeakerVoiceMixin):
            voice_catalog_entries = [
                {
                    "id": "edge:vi-VN-HoaiMyNeural",
                    "provider": "edge",
                    "provider_voice": "vi-VN-HoaiMyNeural",
                }
            ]

            @staticmethod
            def _speaker_voice_assignments():
                return {
                    "speaker_0": {"voice": "banmai"},
                    "speaker_1": {"voice": "edge:vi-VN-HoaiMyNeural"},
                }

            @staticmethod
            def _voice_catalog_data_value(entry):
                return f"edge:{entry['provider_voice']}"

        segments = Harness()._apply_speaker_voice_assignments(
            [
                {"speaker": "speaker_0", "text": "A", "voice_name": "banmai"},
                {"speaker": "speaker_1", "text": "B"},
            ]
        )
        self.assertNotIn("voice_name", segments[0])
        self.assertEqual(segments[1]["voice_name"], "edge:vi-VN-HoaiMyNeural")


if __name__ == "__main__":
    unittest.main()

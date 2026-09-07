import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "app"), str(ROOT / "ui"), str(ROOT)]

import kokoro_support
import tts_processor
from services.resource_download_service import ResourceDownloadService
from services.voice_catalog_service import VoiceCatalogService


class KokoroIntegrationTests(unittest.TestCase):
    def test_local_pt_voices_are_discovered_with_gender(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "kokoro"
            (root / "voices").mkdir(parents=True)
            (root / "voices" / "af_heart.pt").write_bytes(b"voice")
            (root / "voices" / "am_michael.pt").write_bytes(b"voice")
            with patch.object(kokoro_support, "models_path", return_value=str(root)):
                entries = kokoro_support.catalog_entries()
            self.assertEqual({entry["provider_voice"] for entry in entries}, {"af_heart", "am_michael"})
            self.assertEqual(
                {entry["provider_voice"]: entry["gender"] for entry in entries},
                {"af_heart": "female", "am_michael": "male"},
            )

    def test_catalog_service_exposes_kokoro_entries(self):
        fake_entry = {
            "id": "kokoro_af_heart",
            "name": "Heart",
            "provider": "kokoro",
            "provider_voice": "af_heart",
            "language": "en",
            "enabled": True,
        }
        with patch("services.voice_catalog_service.kokoro_catalog_entries", return_value=[fake_entry]):
            entries = VoiceCatalogService(str(ROOT)).load_catalog()
        self.assertIn("kokoro_af_heart", {entry.get("id") for entry in entries})

    def test_prefixed_voice_routes_to_kokoro_synthesizer(self):
        with tempfile.TemporaryDirectory() as folder:
            output = os.path.join(folder, "preview.wav")
            with patch.object(tts_processor, "kokoro_tts_to_wav_16k_mono", return_value=output) as synth:
                result = tts_processor.synthesize_text_to_wav_16k_mono(
                    text="Hello world.",
                    wav_path=output,
                    voice="kokoro:af_heart",
                )
        self.assertEqual(result, output)
        self.assertEqual(synth.call_args.kwargs["voice"], "af_heart")

    def test_resource_manager_marks_kokoro_as_installable(self):
        resource = next(
            item
            for item in ResourceDownloadService(str(ROOT)).list_resources()
            if item.get("id") == "tts:kokoro"
        )
        self.assertTrue(resource.get("auto_download_supported"))


if __name__ == "__main__":
    unittest.main()

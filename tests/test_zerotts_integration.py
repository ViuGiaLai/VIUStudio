import os
import sys
import tempfile
import types
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "app"), str(ROOT / "ui"), str(ROOT)]

from runtime_paths import workspace_root
from services.resource_download_service import ResourceDownloadService
from services.voice_catalog_service import VoiceCatalogService
import tts_processor


class _FakeZeroTTS:
    def synthesize(self, text, voice):
        if not text or voice != "maichi":
            raise AssertionError("ZeroTTS received the wrong text or voice")
        return b"fake-audio"

    def save_audio(self, _audio, path):
        with wave.open(path, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(24000)
            output.writeframes(b"\x00\x00" * 2400)


class ZeroTTSIntegrationTests(unittest.TestCase):
    def test_piper_runtime_finds_nested_english_voice_pack(self):
        with tempfile.TemporaryDirectory() as folder:
            models_root = Path(folder) / "models"
            nested_root = models_root / "piper-en" / "piper-en"
            nested_root.mkdir(parents=True)
            model_path = nested_root / "en_US-amy-medium.onnx"
            model_path.write_bytes(b"onnx")

            def fake_models_path(*parts):
                return str(models_root.joinpath(*parts))

            with patch.object(tts_processor, "models_path", side_effect=fake_models_path), \
                 patch.object(tts_processor, "bundle_root", return_value=str(Path(folder) / "bundle")):
                resolved = tts_processor._resolve_piper_model_path(
                    "models/piper-en/en_US-amy-medium.onnx"
                )

            self.assertEqual(Path(resolved), model_path)

    def test_catalog_exposes_all_builtin_vietnamese_voices(self):
        voices = VoiceCatalogService(workspace_root()).load_catalog()
        zero_voices = [voice for voice in voices if voice.get("provider") == "zerotts"]
        self.assertEqual(len(zero_voices), 8)
        self.assertEqual({voice.get("language") for voice in zero_voices}, {"vi"})
        self.assertIn("zerotts:maichi", {voice.get("id") for voice in zero_voices})

    def test_resource_manager_can_install_zerotts(self):
        resource = next(
            item
            for item in ResourceDownloadService(workspace_root()).list_resources()
            if item.get("id") == "tts:zerotts"
        )
        self.assertTrue(resource.get("auto_download_supported"))

    def test_installer_streams_stage_percentages_instead_of_false_success(self):
        service = ResourceDownloadService(workspace_root())
        process = Mock()
        process.stdout = iter(
            [
                "Collecting zerotts\n",
                "Downloading zerotts.whl\n",
                "Installing collected packages: zerotts\n",
                "Successfully installed zerotts-0.1.1\n",
            ]
        )
        process.wait.return_value = 0
        progress = []
        with patch.object(service, "_pip_runtime_usable", return_value=True), \
             patch("services.resource_download_service.subprocess.Popen", return_value=process):
            service._install_zerotts_runtime(lambda percent, message: progress.append((percent, message)))

        percentages = [percent for percent, _message in progress]
        self.assertEqual(percentages[0], 2)
        self.assertIn(15, percentages)
        self.assertIn(18, percentages)
        self.assertEqual(percentages[-1], 20)

    def test_zerotts_synthesis_outputs_16khz_mono_wav(self):
        previous_model = tts_processor._ZEROTTS_MODEL
        previous_module = sys.modules.get("zerotts")
        tts_processor._ZEROTTS_MODEL = _FakeZeroTTS()
        sys.modules["zerotts"] = types.SimpleNamespace(normalize_vi_text=lambda text: text)
        try:
            with tempfile.TemporaryDirectory() as folder:
                output_path = os.path.join(folder, "preview.wav")
                tts_processor.zerotts_tts_to_wav_16k_mono(
                    text="Xin chào",
                    wav_path=output_path,
                    voice="maichi",
                    tmp_dir=folder,
                )
                with wave.open(output_path, "rb") as result:
                    self.assertEqual(result.getframerate(), 16000)
                    self.assertEqual(result.getnchannels(), 1)
                    self.assertGreater(result.getnframes(), 0)
        finally:
            tts_processor._ZEROTTS_MODEL = previous_model
            if previous_module is None:
                sys.modules.pop("zerotts", None)
            else:
                sys.modules["zerotts"] = previous_module


if __name__ == "__main__":
    unittest.main()

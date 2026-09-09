import os
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path[:0] = [os.path.join(ROOT, "ui"), os.path.join(ROOT, "app"), ROOT]

from PySide6.QtWidgets import QApplication

from views.launcher import LauncherWindow
from views.srt_tts_window import SrtTtsWindow, _Mp3ExportWorker


class SrtTtsWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_launcher_action_selects_dedicated_workspace_without_files(self):
        with tempfile.TemporaryDirectory() as root, patch("views.launcher.workspace_root", return_value=root):
            launcher = LauncherWindow()
            with patch.object(launcher, "accept") as accept:
                launcher._on_srt_tts_project()
            self.assertEqual(launcher.selected_launch_mode, "srt_tts")
            self.assertEqual(launcher.selected_video, "")
            accept.assert_called_once_with()
            launcher.deleteLater()

    def test_imported_srt_timecodes_are_preserved_for_capcut(self):
        source_text = (
            "1\n00:00:03,100 --> 00:00:05,633\nXin chào\n\n"
            "2\n00:00:07,266 --> 00:00:08,200\nTạm biệt\n"
        )
        with tempfile.TemporaryDirectory() as root:
            source_srt = Path(root) / "source.srt"
            source_srt.write_text(source_text, encoding="utf-8")
            window = SrtTtsWindow(root)
            window.srt_path = str(source_srt)
            window.srt_text = source_text
            window.segments = [
                {"start": 3.1, "end": 5.633, "text": "Xin chào"},
                {"start": 7.266, "end": 8.2, "text": "Tạm biệt"},
            ]

            project_srt = Path(window._ensure_project())
            saved = project_srt.read_text(encoding="utf-8-sig")

            self.assertEqual(saved, source_text)
            self.assertEqual(window.state.input_video, "")
            self.assertEqual(window.state.mode, "voice")
            self.assertEqual(window.state.settings["launch_mode"], "srt_tts")
            window.close()

    def test_srt_enables_tts_and_mp3_waits_for_generated_voice(self):
        with tempfile.TemporaryDirectory() as root:
            window = SrtTtsWindow(root)
            window.srt_text = "1\n00:00:00,000 --> 00:00:01,000\nXin chào\n"
            window.source_segments = [{"start": 0.0, "end": 1.0, "text": "Xin chào"}]
            window.segments = list(window.source_segments)
            window._update_actions()

            self.assertTrue(window.generate_btn.isEnabled())
            self.assertFalse(window.export_btn.isEnabled())
            self.assertIn("tts", window.export_btn.toolTip().lower())
            window.close()

    def test_generated_voice_enables_mp3_without_video(self):
        with tempfile.TemporaryDirectory() as root:
            voice = Path(root) / "voice.wav"
            voice.touch()
            window = SrtTtsWindow(root)
            window.voice_path = str(voice)
            window._update_actions()
            self.assertTrue(window.export_btn.isEnabled())
            self.assertFalse(hasattr(window, "video_btn"))
            window.close()

    def test_mp3_worker_converts_generated_timeline_audio(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "voice.wav"
            output = Path(root) / "voice.mp3"
            with wave.open(str(source), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(16000)
                handle.writeframes(b"\x00\x00" * 1600)

            worker = _Mp3ExportWorker(str(source), str(output))
            worker.run()

            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 0)

    def test_tts_setting_change_invalidates_old_voice(self):
        with tempfile.TemporaryDirectory() as root:
            voice = Path(root) / "voice.wav"
            voice.touch()
            window = SrtTtsWindow(root)
            window.voice_path = str(voice)
            window.speed_spin.setValue(1.05)

            self.assertEqual(window.voice_path, "")
            self.assertIn("tạo lại", window.status.text().lower())
            window.close()

    def test_aligned_result_does_not_replace_imported_timing_source(self):
        with tempfile.TemporaryDirectory() as root:
            voice = Path(root) / "voice.wav"
            voice.touch()
            window = SrtTtsWindow(root)
            original = [{"start": 3.1, "end": 5.633, "text": "Xin chào"}]
            aligned = [{"start": 3.1, "end": 4.2, "text": "Xin chào", "_audio_end": 4.2}]
            window.source_segments = list(original)

            window._voice_done(str(voice), aligned, "")

            self.assertEqual(window.source_segments, original)
            self.assertEqual(window.segments, aligned)
            window.close()

    def test_completed_callback_keeps_thread_until_finished_signal(self):
        class FinishedWorker:
            def __init__(self):
                self.deleted = False

            def isRunning(self):
                return False

            def deleteLater(self):
                self.deleted = True

        with tempfile.TemporaryDirectory() as root:
            voice = Path(root) / "voice.wav"
            voice.touch()
            window = SrtTtsWindow(root)
            worker = FinishedWorker()
            window.voice_worker = worker
            window._busy = True

            window._voice_done(str(voice), [], "")
            self.assertIs(window.voice_worker, worker)

            window._worker_finished("voice_worker", worker)
            self.assertIsNone(window.voice_worker)
            self.assertTrue(worker.deleted)
            self.assertFalse(window._busy)
            window.close()


if __name__ == "__main__":
    unittest.main()

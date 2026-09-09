import os
import shutil
import tempfile
import unittest
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "ui"), str(ROOT / "app"), str(ROOT)]

from ui.worker_adapters import VoiceExportWorker
from app.runtime_paths import bin_path


class TestVoiceExportWorker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        ffmpeg = bin_path("ffmpeg", "ffmpeg.exe")
        self.test_wav = os.path.join(self.temp_dir, "test_voice.wav")
        import subprocess
        subprocess.run(
            [ffmpeg, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "1", self.test_wav],
            capture_output=True,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_voice_export_to_mp3(self):
        output_mp3 = os.path.join(self.temp_dir, "output.mp3")
        worker = VoiceExportWorker(self.test_wav, output_mp3, bitrate="192k")
        results = []

        def on_finished(success, path, err):
            results.append((success, path, err))

        worker.finished.connect(on_finished)
        worker.run()

        self.assertEqual(len(results), 1)
        success, path, err = results[0]
        self.assertTrue(success, f"Export failed with: {err}")
        self.assertEqual(path, output_mp3)
        self.assertTrue(os.path.exists(output_mp3))
        self.assertGreater(os.path.getsize(output_mp3), 0)

    def test_voice_export_to_wav(self):
        output_wav = os.path.join(self.temp_dir, "output_copy.wav")
        worker = VoiceExportWorker(self.test_wav, output_wav)
        results = []

        def on_finished(success, path, err):
            results.append((success, path, err))

        worker.finished.connect(on_finished)
        worker.run()

        self.assertEqual(len(results), 1)
        success, path, err = results[0]
        self.assertTrue(success)
        self.assertEqual(path, output_wav)
        self.assertTrue(os.path.exists(output_wav))
        self.assertEqual(os.path.getsize(output_wav), os.path.getsize(self.test_wav))

    def test_voice_export_missing_input(self):
        output_mp3 = os.path.join(self.temp_dir, "output_missing.mp3")
        worker = VoiceExportWorker("non_existent_file.wav", output_mp3)
        results = []

        def on_finished(success, path, err):
            results.append((success, path, err))

        worker.finished.connect(on_finished)
        worker.run()

        self.assertEqual(len(results), 1)
        success, path, err = results[0]
        self.assertFalse(success)
        self.assertIn("not found", err.lower())


class TestVoiceExportUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def test_more_menu_has_export_voice_action(self):
        from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QToolButton
        from ui.views.main_window import _build_header_bar

        class DummyWindow(QWidget):
            def __init__(self):
                super().__init__()
                self.titlebar_layout = QHBoxLayout()
                self.window_title = QPushButton("Title")
                self.run_all_btn = QToolButton()
                self.export_btn = QPushButton("Export")
                self.preview_5s_btn = QPushButton("5s")
                self.toggle_panel_btn = QPushButton("Toggle")
                self.toggle_controls_panel = lambda: None
                self.clean_current_project = lambda: None
                self.exit_to_launcher = lambda: None
                self.open_model_settings_dialog = lambda: None
                self.open_normalizer_dict_dialog = lambda: None
                self.rename_current_project = lambda: None
                self.import_translated_srt = lambda: None
                self.import_original_srt = lambda: None
                self.download_subtitle = lambda: None
                self.download_original_script = lambda: None
                self.export_voice_audio = lambda: None

        win = DummyWindow()
        _build_header_bar(win)

        self.assertTrue(hasattr(win, "export_voice_action"))
        self.assertEqual(win.export_voice_action.text(), "Export Voice Audio (MP3)…")

    def test_refresh_ui_state_enables_export_and_generate_when_translated_text_present(self):
        from PySide6.QtWidgets import QWidget, QTextEdit, QLineEdit, QPushButton, QToolButton
        from PySide6.QtGui import QAction
        from ui.features.workflow_actions import WorkflowActionsMixin

        class DummyWorkflowGUI(WorkflowActionsMixin, QWidget):
            def __init__(self):
                super().__init__()
                self._pipeline_active = False
                self.video_path_edit = QLineEdit("")
                self.audio_source_edit = QLineEdit("")
                self.translated_text = QTextEdit("")
                self.transcript_text = QTextEdit("")
                self.current_segments = []
                self.current_translated_segments = []
                self.last_voice_vi_path = ""
                self.run_all_btn = QToolButton()
                self.export_btn = QPushButton("Export")
                self.preview_frame_btn = QPushButton("Preview Frame")
                self.preview_5s_btn = QPushButton("Preview 5s")
                self.extract_btn = QPushButton("Extract")
                self.vocal_sep_btn = QPushButton("Vocal Sep")
                self.transcribe_btn = QPushButton("Transcribe")
                self.translate_btn = QPushButton("Translate")
                self.apply_translated_btn = QPushButton("Apply")
                self.export_voice_action = QAction("Export Voice Audio (MP3)…", self)
                self.run_all_pipeline = lambda: None
                self.import_translated_srt = lambda: None
                self.run_pipeline_to_stage = lambda s: None
                self.skip_tts_stage = lambda: None

            def _preview_is_playing(self):
                return False

            def resolve_canonical_video_path(self):
                return ""

            def _translation_phase_complete(self):
                return False

            def get_output_mode_key(self):
                return "voice"

            def get_active_segments(self):
                return []

            def update_workflow_stage_badges(self):
                pass

            def update_workflow_availability(self):
                pass

            def update_guidance_panel(self):
                pass

            def _update_ocr_overlay(self):
                pass

            def using_existing_audio_source(self):
                return False

            def is_filter_workflow_active(self):
                return False

            def _refresh_timeline_history_buttons(self):
                pass

        gui = DummyWorkflowGUI()
        gui.refresh_ui_state()

        # Initially empty: no video, no subtitles
        self.assertFalse(gui.run_all_btn.isEnabled())
        self.assertFalse(gui.export_voice_action.isEnabled())

        # When translated subtitles are loaded/imported:
        gui.translated_text.setText("1\n00:00:01,000 --> 00:00:02,000\nXin chào các bạn")
        gui.refresh_ui_state()

        # Generate (run_all_btn) and Export Voice should now be enabled!
        self.assertTrue(gui.run_all_btn.isEnabled())
        self.assertTrue(gui.export_voice_action.isEnabled())


if __name__ == "__main__":
    unittest.main()


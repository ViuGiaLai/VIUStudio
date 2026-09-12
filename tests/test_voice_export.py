import os
import json
import shutil
import tempfile
import unittest
import sys
import wave
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
            [ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=1", self.test_wav],
            capture_output=True,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_voice_export_to_mp3(self):
        output_mp3 = os.path.join(self.temp_dir, "output.mp3")
        provenance = {"voice_name": "edge:vi-VN-HoaiMyNeural", "cues": []}
        with open(self.test_wav + ".json", "w", encoding="utf-8") as handle:
            json.dump(provenance, handle)
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
        with open(output_mp3 + ".json", encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), provenance)

        # Decode the actual MP3 and compare it at sample zero. This catches
        # encoder-delay or padding mistakes that would move every spoken cue.
        decoded_wav = os.path.join(self.temp_dir, "decoded_voice.wav")
        ffmpeg = bin_path("ffmpeg", "ffmpeg.exe")
        import subprocess
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", output_mp3,
             "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", decoded_wav],
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with wave.open(self.test_wav, "rb") as source_stream:
            source_samples = source_stream.readframes(source_stream.getnframes())
        with wave.open(decoded_wav, "rb") as decoded_stream:
            decoded_samples = decoded_stream.readframes(decoded_stream.getnframes())
        import numpy as np
        source = np.frombuffer(source_samples, dtype=np.int16).astype(np.float64)
        decoded = np.frombuffer(decoded_samples, dtype=np.int16).astype(np.float64)
        self.assertEqual(len(decoded), len(source))
        self.assertGreater(float(np.corrcoef(source, decoded)[0, 1]), 0.99)

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
                self.import_voice_audio = lambda: None
                self.download_subtitle = lambda: None
                self.download_original_script = lambda: None
                self.export_voice_audio = lambda: None

        win = DummyWindow()
        _build_header_bar(win)

        self.assertTrue(hasattr(win, "export_voice_action"))
        self.assertEqual(win.export_voice_action.text(), "Export Voice Audio (MP3)…")
        self.assertTrue(hasattr(win, "import_voice_action"))
        self.assertEqual(win.import_voice_action.text(), "Import Voice Audio…")

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

    def test_import_voice_audio_success(self):
        from unittest.mock import patch, MagicMock
        from ui.features.voice_subtitle_preview import VoiceSubtitlePreviewMixin
        from PySide6.QtWidgets import QWidget

        class DummyVoiceGUI(VoiceSubtitlePreviewMixin, QWidget):
            def __init__(self):
                super().__init__()
                self.workspace_root = tempfile.mkdtemp()
                self.processed_artifacts = {}
                self.last_voice_vi_path = ""
                self.timeline = MagicMock()
                self.audio_tab_btn = MagicMock()
                self.current_translated_segments = []
                self.current_segments = []

            def ensure_current_project(self):
                return None

            def update_project_artifact(self, name, path):
                self.processed_artifacts[name] = path

            def update_project_step(self, name, status):
                pass

            def refresh_ui_state(self):
                pass

            def log(self, msg):
                pass

        gui = DummyVoiceGUI()
        sample_audio = os.path.join(gui.workspace_root, "test_voice.mp3")
        with open(sample_audio, "wb") as f:
            f.write(b"ID3" + b"\x00" * 100)

        with patch("ui.features.voice_subtitle_preview.QFileDialog.getOpenFileName", return_value=(sample_audio, "Audio Files (*.mp3)")):
            with patch("ui.features.voice_subtitle_preview.QMessageBox.information"):
                gui.import_voice_audio()

        self.assertEqual(gui.last_voice_vi_path, sample_audio)
        self.assertEqual(gui.processed_artifacts.get("voice_vi"), sample_audio)
        gui.timeline.sync_tts_track.assert_called_once()
        gui.audio_tab_btn.setEnabled.assert_called_with(True)
        shutil.rmtree(gui.workspace_root, ignore_errors=True)


class TestExportCancellation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def test_export_progress_dialog_ui_and_signals(self):
        from ui.widgets.progress_dialog import ExportProgressDialog

        dlg = ExportProgressDialog()
        self.assertEqual(dlg.windowTitle(), "Exporting Video")
        self.assertTrue(hasattr(dlg, "cancel_btn"))
        self.assertTrue(hasattr(dlg, "bg_btn"))
        self.assertEqual(dlg.cancel_btn.text(), "Cancel")
        self.assertEqual(dlg.bg_btn.text(), "Run in background")

        # Test value and range
        dlg.setRange(0, 100)
        dlg.setValue(45)
        self.assertEqual(dlg.value(), 45)
        self.assertEqual(dlg.maximum(), 100)

        # Test label update
        dlg.setLabelText("Burning subtitles into video (45%)")
        self.assertIn("45%", dlg.label.text())

        # Test cancel click triggers cancel_requested and changes button text
        cancel_called = []
        dlg.cancel_requested.connect(lambda: cancel_called.append(True))
        dlg.cancel_btn.click()

        self.assertEqual(len(cancel_called), 1)
        self.assertFalse(dlg.cancel_btn.isEnabled())
        self.assertEqual(dlg.cancel_btn.text(), "Cancelling...")
        self.assertIn("Cancelling export", dlg.label.text())

    def test_cancel_video_export_interrupts_worker(self):
        from unittest.mock import MagicMock
        from ui.features.workflow_actions import WorkflowActionsMixin
        from ui.widgets.progress_dialog import ExportProgressDialog
        from PySide6.QtWidgets import QWidget, QPushButton, QProgressBar

        class DummyGUI(WorkflowActionsMixin, QWidget):
            def __init__(self):
                super().__init__()
                self.export_progress_dialog = ExportProgressDialog(self)
                self.export_thread = MagicMock()
                self.export_thread.isRunning.return_value = True
                self.export_btn = QPushButton("Exporting...")
                self.progress_bar = QProgressBar()
                self._pipeline_active = True

            def log(self, msg):
                pass

            def update_project_step(self, step, status):
                pass

            def _unregister_progress_dialog(self, dlg):
                pass

        gui = DummyGUI()
        gui.cancel_video_export()

        gui.export_thread.requestInterruption.assert_called_once()
        self.assertEqual(gui.export_progress_dialog.cancel_btn.text(), "Cancelling...")

    def test_on_export_finished_handles_cancellation_gracefully(self):
        from unittest.mock import MagicMock
        from ui.controllers.preview_controller import PreviewController
        from PySide6.QtWidgets import QWidget, QPushButton, QProgressBar

        class DummyMainWindow(QWidget):
            def __init__(self):
                super().__init__()
                self.export_btn = QPushButton("Exporting...")
                self.progress_bar = QProgressBar()
                self.progress_bar.setValue(50)
                self.output_mode_combo = MagicMock()
                self.output_mode_combo.currentText.return_value = "voice"
                self.steps = {}
                self.logs = []
                self.export_progress_dialog = None

            def _close_export_progress_dialog(self):
                pass

            def on_output_mode_changed(self, mode):
                pass

            def update_project_step(self, step, status):
                self.steps[step] = status

            def log(self, msg):
                self.logs.append(msg)

            def refresh_ui_state(self):
                pass

            def show_error(self, title, msg, detail):
                raise AssertionError("show_error should NOT be called on cancellation!")

        gui = DummyMainWindow()
        controller = PreviewController(gui)

        controller.on_export_finished("", "Operation cancelled by user")

        self.assertEqual(gui.export_btn.text(), "Export")
        self.assertTrue(gui.export_btn.isEnabled())
        self.assertEqual(gui.progress_bar.value(), 0)
        self.assertEqual(gui.steps.get("export"), "pending")
        self.assertTrue(any("cancelled" in log.lower() for log in gui.logs))


if __name__ == "__main__":
    unittest.main()

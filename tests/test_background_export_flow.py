import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "ui"), str(ROOT / "app"), str(ROOT)]

from PySide6.QtCore import QObject, Signal, QThread
from PySide6.QtWidgets import QApplication

from utils.background_export_manager import BackgroundExportManager, ExportJob
from widgets.progress_dialog import ExportProgressDialog
from views.launcher import LauncherWindow, ProjectCard, _project_pipeline_status


class DummyWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(str, str)

    def __init__(self):
        super().__init__()
        self._interrupted = False

    def requestInterruption(self):
        self._interrupted = True

    def isRunning(self):
        return True


class BackgroundExportFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        # Reset singleton between tests
        BackgroundExportManager._instance = None
        self.mgr = BackgroundExportManager.get_instance()

    def test_background_export_manager_registration_and_query(self):
        worker = DummyWorker()
        job = self.mgr.register_job(
            project_id="proj_101",
            project_name="Project 101",
            project_state_path="/test/path/project.json",
            video_path="/test/path/source.mp4",
            output_path="/test/path/output.mp4",
            worker=worker,
        )

        self.assertTrue(job.is_active)
        self.assertEqual(job.percent, 0)
        self.assertEqual(len(self.mgr.get_active_jobs()), 1)

        # Emit progress from worker
        worker.progress.emit(45, "Encoding 5.7x")
        self.assertEqual(job.percent, 45)
        self.assertEqual(job.message, "Encoding 5.7x")

        # Query by project ID
        found = self.mgr.get_job_for_project("proj_101")
        self.assertIsNotNone(found)
        self.assertEqual(found.job_id, job.job_id)

        # Worker completion
        worker.finished.emit("/test/path/output.mp4", "")
        self.assertFalse(job.is_active)
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.percent, 100)

    def test_dialog_run_in_background_hides_and_sets_flag(self):
        dialog = ExportProgressDialog()
        dialog.show()
        self.assertFalse(dialog.is_backgrounded())

        bg_signal_received = []
        dialog.bg_requested.connect(lambda: bg_signal_received.append(True))

        # Click "Run in background"
        dialog.bg_btn.click()
        self.assertTrue(dialog.is_backgrounded())
        self.assertTrue(dialog.isHidden())
        self.assertEqual(len(bg_signal_received), 1)

        # X close button also sets background mode
        dialog.set_backgrounded(False)
        mock_event = MagicMock()
        dialog.closeEvent(mock_event)
        self.assertTrue(dialog.is_backgrounded())
        mock_event.ignore.assert_called_once()
        dialog.deleteLater()

    def test_launcher_status_shows_background_export(self):
        worker = DummyWorker()
        state_path = os.path.abspath("temp/mock_proj/project.json")
        video_path = os.path.abspath("temp/mock_proj/source.mp4")
        job = self.mgr.register_job(
            project_id="test_recap",
            project_name="Test Recap",
            project_state_path=state_path,
            video_path=video_path,
            output_path="/test/output.mp4",
            worker=worker,
        )
        worker.progress.emit(68, "Rendering recap...")

        status_text, status_color = _project_pipeline_status(video_path, state_path)
        self.assertIn("68%", status_text)
        self.assertIn("⚡", status_text)
        self.assertEqual(status_color, "#34d399")

        # Finish job
        worker.finished.emit("/test/output.mp4", "")
        self.assertFalse(self.mgr.has_active_exports())

    def test_multi_project_switch_preserves_background_worker(self):
        worker = DummyWorker()
        self.mgr.register_job(
            project_id="proj_A",
            project_name="Project A",
            project_state_path="/test/A/project.json",
            video_path="/test/A/video.mp4",
            output_path="/test/A/out.mp4",
            worker=worker,
        )
        self.assertTrue(self.mgr.is_worker_registered(worker))

        # Simulate _terminate_workers check in PipelineLifecycleMixin
        attrs = ["export_thread", "extraction_thread"]
        mock_gui = MagicMock()
        mock_gui.export_thread = worker

        for name in attrs:
            w = getattr(mock_gui, name, None)
            if w is not None:
                if name == "export_thread":
                    if self.mgr.is_worker_registered(w):
                        continue  # Protected!
                w.requestInterruption()

        # Verify background worker was NOT interrupted!
        self.assertFalse(worker._interrupted)

    def test_background_exports_dialog_cards_and_updates(self):
        from widgets.background_exports_dialog import BackgroundExportsDialog
        dlg = BackgroundExportsDialog()

        worker1 = DummyWorker()
        worker2 = DummyWorker()

        self.mgr.register_job(
            project_id="proj_1",
            project_name="Movie Recap 1",
            project_state_path="/test/1/project.json",
            video_path="/test/1/video.mp4",
            output_path="/test/1/out.mp4",
            worker=worker1,
        )
        self.mgr.register_job(
            project_id="proj_2",
            project_name="Short Story 2",
            project_state_path="/test/2/project.json",
            video_path="/test/2/video.mp4",
            output_path="/test/2/out.mp4",
            worker=worker2,
        )

        dlg.refresh_jobs()
        self.assertEqual(len(dlg._job_widgets), 2)
        self.assertFalse(dlg.empty_label.isVisible())

        # Progress update
        worker1.progress.emit(72, "Encoding H.264")
        w1 = dlg._job_widgets[list(dlg._job_widgets.keys())[0]]
        # At least one has 72%
        any_72 = any(w["pbar"].value() == 72 for w in dlg._job_widgets.values())
        self.assertTrue(any_72)

        # Worker completion
        worker1.finished.emit("/test/1/out.mp4", "")
        # Cancel second
        worker2.finished.emit("", "Cancelled by user")

        dlg.deleteLater()

    def test_header_badge_multi_project_listening(self):
        from features.workflow_actions import WorkflowActionsMixin
        from PySide6.QtWidgets import QPushButton, QWidget

        class DummyEditor(WorkflowActionsMixin, QWidget):
            def __init__(self):
                super().__init__()
                self.bg_export_badge = QPushButton("⚡ Exporting: 0%")
                self.current_project_state = MagicMock()
                self.current_project_state.project_id = "editor_proj"
                self.current_project_state.project_state_path = os.path.abspath("/editor/project.json")
                self._current_video_path = os.path.abspath("/editor/video.mp4")
                self._is_export_backgrounded = False
                self._logs = []

            def log(self, msg):
                self._logs.append(msg)

        editor = DummyEditor()
        editor._setup_background_export_listener()

        # Another project starts exporting in the background
        worker_other = DummyWorker()
        job_other = self.mgr.register_job(
            project_id="other_proj",
            project_name="Other Film",
            project_state_path="/other/project.json",
            video_path="/other/video.mp4",
            output_path="/other/output.mp4",
            worker=worker_other,
        )

        worker_other.progress.emit(35, "Encoding other film...")
        self.assertTrue(editor.bg_export_badge.isVisible())
        self.assertIn("Other Film", editor.bg_export_badge.text())
        self.assertIn("35%", editor.bg_export_badge.text())

        # Other project finishes
        worker_other.finished.emit("/other/output.mp4", "")
        self.assertIn("Other Film", editor.bg_export_badge.text())
        self.assertIn("Exported", editor.bg_export_badge.text())
        self.assertTrue(editor.bg_export_badge.text().startswith("✓"))

        editor.deleteLater()


if __name__ == "__main__":
    unittest.main()

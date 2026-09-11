import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "ui"), str(ROOT / "app")]

from PySide6.QtWidgets import QApplication
from views.launcher import LauncherWindow, ProjectCard


class LauncherLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_resize_reflows_cards_without_reloading_projects(self):
        with patch.object(LauncherWindow, "_detect_gpu_with_cuda", return_value=(False, "", False)), \
             patch.object(LauncherWindow, "_validate_resources_for_device"), \
             patch.object(LauncherWindow, "_load_recent") as load:
            window = LauncherWindow()
            try:
                window.show()
                self.app.processEvents()
                for i in range(5):
                    window.grid.addWidget(ProjectCard("", "", window, display_name=f"Project {i}"), i, 0)
                load.reset_mock()
                for width in (980, 1400, 980):
                    window.resize(width, 720)
                    self.app.processEvents()
                    window._reflow_project_cards()
                    self.app.processEvents()
                    self.assertEqual(window.grid.count(), 5)
                    self.assertEqual(window.project_scroll.horizontalScrollBar().maximum(), 0)
                    buttons = [window.new_btn, window.srt_tts_btn, window.split_btn, window.resource_btn]
                    for first, second in zip(buttons, buttons[1:]):
                        self.assertFalse(first.geometry().intersects(second.geometry()))
                load.assert_not_called()
            finally:
                window.close()
                window.deleteLater()


if __name__ == "__main__":
    unittest.main()

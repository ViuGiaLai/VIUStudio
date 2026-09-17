import os
import sys
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT_DIR = r"d:\all_my_project\CapCap"
for d in (ROOT_DIR, os.path.join(ROOT_DIR, "app"), os.path.join(ROOT_DIR, "ui")):
    if d not in sys.path:
        sys.path.insert(0, d)

from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor, QImage
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication

from ui.utils.media_backend import QtMediaPlayerBackend
from ui.widgets.video_view import VideoView
from app.services.timeline_video_sequence import is_image_file


class TestImagePlaybackBackend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.view = VideoView()
        self.backend = QtMediaPlayerBackend(self.view)

    def tearDown(self):
        self.backend.stop()

    def test_image_file_detection(self):
        self.assertTrue(is_image_file("sample.png"))
        self.assertTrue(is_image_file("photo.jpg"))
        self.assertTrue(is_image_file("banner.JPEG"))
        self.assertTrue(is_image_file("graphic.webp"))
        self.assertFalse(is_image_file("clip.mp4"))
        self.assertFalse(is_image_file("video.mkv"))

    def test_qt_backend_set_image_source(self):
        img_path = os.path.abspath(os.path.join(ROOT_DIR, "dummy_test_intro.png"))
        img = QImage(100, 100, QImage.Format_ARGB32)
        img.fill(QColor(255, 0, 0))
        img.save(img_path, "PNG")
        try:
            positions = []
            durations = []
            states = []
            self.backend.positionChanged.connect(positions.append)
            self.backend.durationChanged.connect(durations.append)
            self.backend.stateChanged.connect(states.append)

            self.backend.setSource(QUrl.fromLocalFile(img_path))

            self.assertTrue(self.backend._is_image)
            self.assertEqual(self.backend.position(), 0)
            self.assertGreater(self.backend.duration(), 0)
            self.assertEqual(self.backend._player.source(), QUrl())

            # Test play()
            self.backend.play()
            self.assertTrue(self.backend.is_playing())
            self.assertEqual(self.backend.playbackState(), QMediaPlayer.PlayingState)
            self.assertIn(int(QMediaPlayer.PlayingState.value), states)

            # Test ticking
            self.backend._on_image_tick()
            self.assertGreater(self.backend.position(), 0)
            self.assertIn(self.backend.position(), positions)

            # Test pause()
            self.backend.pause()
            self.assertFalse(self.backend.is_playing())
            self.assertEqual(self.backend.playbackState(), QMediaPlayer.PausedState)

            # Test setPosition()
            self.backend.setPosition(1500)
            self.assertEqual(self.backend.position(), 1500)

            # Test stop()
            self.backend.stop()
            self.assertEqual(self.backend.position(), 0)

            # Test switching back to video resets _is_image
            vid_path = os.path.abspath(os.path.join(ROOT_DIR, "dummy_video.mp4"))
            self.backend.setSource(QUrl.fromLocalFile(vid_path))
            self.assertFalse(self.backend._is_image)
        finally:
            if os.path.exists(img_path):
                os.remove(img_path)

    def test_audio_setters_reject_images(self):
        img_path = os.path.abspath(os.path.join(ROOT_DIR, "dummy_audio.png"))
        img = QImage(50, 50, QImage.Format_ARGB32)
        img.save(img_path, "PNG")
        try:
            self.backend.set_audio_file(img_path)
            self.assertEqual(self.backend._audio_path, "")
            self.assertEqual(self.backend._dubbed_loaded_path, "")

            self.backend.set_original_audio_file(img_path)
            self.assertEqual(self.backend._original_audio_path, "")
            self.assertEqual(self.backend._original_loaded_path, "")
        finally:
            if os.path.exists(img_path):
                os.remove(img_path)

    def test_video_view_image_source(self):
        img_path = os.path.abspath(os.path.join(ROOT_DIR, "dummy_view.png"))
        img = QImage(120, 80, QImage.Format_ARGB32)
        img.fill(QColor(0, 128, 255))
        img.save(img_path, "PNG")
        try:
            self.view.set_image_source(img_path)
            self.assertTrue(self.view.image_item.isVisible())
            self.assertFalse(self.view.video_item.isVisible())
            self.assertEqual(self.view.video_source_width, 120)
            self.assertEqual(self.view.video_source_height, 80)

            self.view.clear_image_source()
            self.assertFalse(self.view.image_item.isVisible())
            self.assertTrue(self.view.video_item.isVisible())
        finally:
            if os.path.exists(img_path):
                os.remove(img_path)

    def test_multi_video_sequence_transition_from_image_to_video(self):
        from ui.features.multi_video_timeline import MultiVideoTimelineMixin

        class DummyWindow(MultiVideoTimelineMixin):
            def __init__(self, media_player):
                self.media_player = media_player
                self._timeline_preview_source = ""
                self._timeline_global_position_ms = 0
                self.last_preview_video_path = ""
                self.timeline = MagicMock()
                self.timeline._is_playing = True
                self.seek_calls = []

            def get_timeline_video_clips(self, existing_only=True):
                return [
                    {
                        "source": r"C:\intro.png",
                        "timeline_start": 0.0,
                        "timeline_end": 3.0,
                        "timeline_duration": 3.0,
                        "source_start": 0.0,
                        "source_duration": 3.0,
                        "speed": 1.0,
                    },
                    {
                        "source": r"C:\main_video.mp4",
                        "timeline_start": 3.0,
                        "timeline_end": 20.0,
                        "timeline_duration": 17.0,
                        "source_start": 0.0,
                        "source_duration": 17.0,
                        "speed": 1.0,
                    },
                ]

            def update_duration_label(self, current, total):
                pass

            def refresh_timed_layer_preview(self, pos):
                pass

            def update_playback_subtitle_highlight(self, pos):
                pass

            def seek_timeline_video(self, global_seconds):
                self.seek_calls.append(global_seconds)

        win = DummyWindow(self.backend)
        self.backend._source_path = r"C:\intro.png"
        win._timeline_preview_source = r"C:\intro.png"

        # Position at 1.0s: still on image
        win.handle_sequence_position_changed(1000)
        self.assertEqual(len(win.seek_calls), 0)

        # Position at 2.90s (near end of 3.0s clip): should transition to next clip (3.0s)
        win.handle_sequence_position_changed(2900)
        self.assertEqual(len(win.seek_calls), 1)
        self.assertEqual(win.seek_calls[0], 3.0)


if __name__ == "__main__":
    unittest.main()

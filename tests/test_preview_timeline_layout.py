import os
import sys
import unittest

from PySide6.QtWidgets import QApplication


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path[:0] = [os.path.join(ROOT, "ui"), os.path.join(ROOT, "app"), ROOT]
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from widgets.video_view import VideoView
from views.editor.timeline import EditorTimeline
from app.layers.base import LayerType
from app.layers.timeline import Track


class TestPreviewTimelineLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_render_dimensions_hold_canvas_ratio_before_video_metadata(self):
        view = VideoView()
        view.resize(800, 300)
        view.set_subtitle_render_dimensions(1920, 1080)

        canvas = view.get_preview_canvas_rect()

        self.assertAlmostEqual(canvas.width() / canvas.height(), 16 / 9, places=3)
        self.assertLess(canvas.width(), view.width())
        self.assertAlmostEqual(canvas.height(), view.height(), delta=1)

    def test_bottom_custom_subtitle_stays_inside_preview_canvas(self):
        view = VideoView()
        view.resize(640, 360)
        view.set_subtitle_render_dimensions(1920, 1080)
        view.subtitle_item.set_style(font_size=24, background_box=True)
        view.subtitle_item.set_text("Phụ đề luôn nhìn thấy")
        view.subtitle_item.set_positioning(
            custom_position_enabled=True,
            custom_x_percent=50,
            custom_y_percent=100,
        )

        view.reposition_subtitle()
        canvas = view.get_preview_canvas_rect()
        subtitle_bottom = view.subtitle_item.pos().y() + view.subtitle_item.H

        self.assertLessEqual(subtitle_bottom, canvas.bottom() + 0.5)

    def test_editor_tracks_use_compact_capcut_density(self):
        timeline = EditorTimeline()
        default_heights = {
            track.type: timeline._compute_track_height(track)
            for track in timeline._timeline.tracks
        }
        subtitle = Track(name="TS1", type=LayerType.SUBTITLE, height=80)

        self.assertLessEqual(default_heights[LayerType.VIDEO], 60)
        self.assertLessEqual(default_heights[LayerType.AUDIO], 50)
        self.assertLessEqual(timeline._compute_track_height(subtitle), 40)


if __name__ == "__main__":
    unittest.main()

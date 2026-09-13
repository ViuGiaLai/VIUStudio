import importlib.util
import os
import sys
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
UI_ROOT = os.path.join(ROOT, "ui")
if UI_ROOT not in sys.path:
    sys.path.insert(0, UI_ROOT)
TIMELINE_PATH = os.path.join(ROOT, "ui", "views", "editor", "timeline.py")
SPEC = importlib.util.spec_from_file_location("test_subtitle_click_timeline", TIMELINE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
EditorTimeline = MODULE.EditorTimeline

TIMELINE_EDITING_PATH = os.path.join(ROOT, "ui", "features", "timeline_editing.py")
EDITING_SPEC = importlib.util.spec_from_file_location("test_timeline_editing_mixin", TIMELINE_EDITING_PATH)
EDITING_MODULE = importlib.util.module_from_spec(EDITING_SPEC)
EDITING_SPEC.loader.exec_module(EDITING_MODULE)
TimelineEditingMixin = EDITING_MODULE.TimelineEditingMixin


class TimelineSubtitleClickTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_plain_subtitle_click_selects_without_emitting_timing_change(self):
        widget = EditorTimeline()
        widget.set_duration_ms(10_000)
        widget.set_segments([
            {
                "start": 2.0,
                "end": 4.0,
                "text": "Translated subtitle",
                "tts_text": "Translated subtitle",
                "audio_path": "generated-voice.wav",
            }
        ])
        widget.resize(900, 360)
        widget._rebuild_track_heights()
        widget._redraw()
        widget.show()
        self.app.processEvents()

        selected_spy = QSignalSpy(widget.segmentSelected)
        edit_started_spy = QSignalSpy(widget.segmentTimingEditStarted)
        timing_changed_spy = QSignalSpy(widget.segmentTimingChanged)
        layer_changed_spy = QSignalSpy(widget.layerTimingChanged)

        # V1 and A1 occupy the first two rows; click the live centre of TS1
        # so the test follows the editor's compact track density.
        tracks = [
            track for track in widget._timeline.tracks
            if widget.is_track_shown_on_timeline(track)
        ]
        ts1_index = next(
            index for index, track in enumerate(tracks)
            if widget._is_subtitle_track(track)
        )
        preceding_height = sum(widget._track_display_height(track) for track in tracks[:ts1_index])
        ts1_height = widget._track_display_height(tracks[ts1_index])
        ts1_y = widget.RULER_HEIGHT + preceding_height + ts1_height // 2
        cue_x = widget.CONTENT_LEFT_PAD + int(3.0 * widget.pixels_per_second)
        QTest.mouseClick(
            widget.viewport(),
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(cue_x, ts1_y),
        )
        self.app.processEvents()

        self.assertEqual(selected_spy.count(), 1)
        self.assertEqual(edit_started_spy.count(), 0)
        self.assertEqual(timing_changed_spy.count(), 0)
        self.assertEqual(layer_changed_spy.count(), 0)

        widget.deleteLater()
        self.app.processEvents()

    def test_redundant_timing_update_does_not_invalidate_generated_voice(self):
        class Harness(TimelineEditingMixin):
            pass

        harness = Harness()
        harness.current_segments = [{"start": 2.0, "end": 4.0, "text": "source"}]
        harness.current_translated_segments = [
            {"start": 2.0, "end": 4.0, "text": "translated"}
        ]
        harness._commit_subtitle_mutation = MagicMock()

        harness.on_timeline_segment_timing_changed(0, 2.0, 4.0)

        harness._commit_subtitle_mutation.assert_not_called()


if __name__ == "__main__":
    unittest.main()

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_DIR = os.path.join(ROOT_DIR, "app")
UI_DIR = os.path.join(ROOT_DIR, "ui")
for p in (ROOT_DIR, APP_DIR, UI_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from PySide6.QtWidgets import QApplication, QMessageBox
from ui.helpers.srt_helpers import parse_timestamp, format_timestamp
from ui.features.voice_subtitle_preview import VoiceSubtitlePreviewMixin
from ui.features.multi_video_timeline import MultiVideoTimelineMixin
from ui.features.timeline_editing import TimelineEditingMixin
from ui.dialogs.subtitle_sync_dialog import SubtitleSyncDialog


class DummySyncHost(VoiceSubtitlePreviewMixin, MultiVideoTimelineMixin, TimelineEditingMixin):
    def __init__(self):
        self.workspace_root = "."
        self.srt_output_folder_edit = MagicMock()
        self.srt_output_folder_edit.text.return_value = ""
        self.current_segments = [
            {"start": 0.32, "end": 2.50, "text": "Câu 1"},
            {"start": 2.60, "end": 4.80, "text": "Câu 2"},
            {"start": 5.00, "end": 7.20, "text": "Câu 3"},
        ]
        self.current_translated_segments = [
            {"start": 0.32, "end": 2.50, "text": "Line 1"},
            {"start": 2.60, "end": 4.80, "text": "Line 2"},
            {"start": 5.00, "end": 7.20, "text": "Line 3"},
        ]
        self._selected_segment_index = 1
        self._timeline_global_position_ms = 3500
        self.timeline = MagicMock()
        self.timeline._timeline = MagicMock()
        self.timeline._timeline.tracks = []
        self.timeline.SEGMENT_GAP = 0.03
        self.timeline.duration = 20000
        self._timeline_timing_undo_stack = []
        self._timeline_timing_redo_stack = []

    def get_timeline_video_clips(self, existing_only=False):
        # Production returns dicts from TimelineVideoClip.to_dict(), not objects.
        # Intro image 0–2s, then main video 2–12s (after user trimmed 3s → 2s).
        return [
            {
                "source": "intro.png",
                "timeline_start": 0.0,
                "timeline_end": 2.0,
                "is_image": True,
            },
            {
                "source": "main_video.mp4",
                "timeline_start": 2.0,
                "timeline_end": 12.0,
                "is_image": False,
            },
        ]

    def timeline_position_ms(self):
        return self._timeline_global_position_ms

    def log(self, msg):
        pass

    def apply_segments_to_timeline(self):
        pass

    def refresh_ui_state(self):
        pass

    def _commit_subtitle_mutation(self, *args, **kwargs):
        pass

    def _dict_segments_to_models(self, segs, translated=False):
        return []

    def _sync_hidden_transcript_text_from_segments(self):
        pass

    def _sync_hidden_translated_text_from_segments(self):
        pass

    def _refresh_timeline_history_buttons(self):
        pass

    def set_selected_segment_index(self, idx, sync_ui=True):
        self._selected_segment_index = idx


class TestSubtitleSyncAndTimingEdit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_parse_timestamp_formats(self):
        # SRT format HH:MM:SS,mmm
        self.assertAlmostEqual(parse_timestamp("00:01:23,450"), 83.45)
        # Dot format HH:MM:SS.mmm
        self.assertAlmostEqual(parse_timestamp("00:00:02.320"), 2.32)
        # MM:SS.mmm
        self.assertAlmostEqual(parse_timestamp("01:30.500"), 90.5)
        # Seconds only
        self.assertAlmostEqual(parse_timestamp("12.75"), 12.75)
        self.assertAlmostEqual(parse_timestamp("5"), 5.0)
        # Numeric directly
        self.assertAlmostEqual(parse_timestamp(4.2), 4.2)
        # Invalid
        self.assertIsNone(parse_timestamp("invalid_text"))
        self.assertIsNone(parse_timestamp(""))
        self.assertIsNone(parse_timestamp(None))

    def test_auto_alignment_prompt_when_video_starts_after_intro(self):
        host = DummySyncHost()
        imported = [
            {"start": 0.32, "end": 2.50, "text": "Hello"},
            {"start": 2.60, "end": 4.80, "text": "World"},
        ]
        # Auto-aligns automatically without prompt to start with main video (+2.0s)
        aligned = host._check_and_prompt_subtitle_video_alignment(imported)

        # Main video starts at 2.0s, so imported should be shifted by +2.0s
        self.assertAlmostEqual(aligned[0]["start"], 2.32)
        self.assertAlmostEqual(aligned[0]["end"], 4.50)
        self.assertAlmostEqual(aligned[1]["start"], 4.60)
        self.assertAlmostEqual(aligned[1]["end"], 6.80)

    def test_import_treats_srt_as_source_video_time_even_when_first_cue_is_after_intro(self):
        host = DummySyncHost()
        # First speech is 2.50s into the original video — later than the 2.0s intro.
        # File import must still add the intro offset (2.50 → 4.50).
        imported = [
            {"start": 2.50, "end": 4.50, "text": "Hello"},
        ]
        aligned = host._check_and_prompt_subtitle_video_alignment(imported)

        self.assertAlmostEqual(aligned[0]["start"], 4.50)
        self.assertAlmostEqual(aligned[0]["end"], 6.50)

    def test_import_uses_trimmed_intro_duration_not_original_three_seconds(self):
        host = DummySyncHost()
        imported = [
            {"start": 5.00, "end": 7.20, "text": "Late first line"},
            {"start": 8.00, "end": 10.00, "text": "Second line"},
        ]
        aligned = host._check_and_prompt_subtitle_video_alignment(imported)

        # Intro was trimmed 3s → 2s, so offset is +2.0 not +3.0
        self.assertAlmostEqual(aligned[0]["start"], 7.00)
        self.assertAlmostEqual(aligned[0]["end"], 9.20)
        self.assertAlmostEqual(aligned[1]["start"], 10.00)
        self.assertAlmostEqual(aligned[1]["end"], 12.00)
        self.assertTrue(aligned[0].get("_timeline_relative"))

    def test_subtitle_sync_dialog_presets_and_apply_all(self):
        host = DummySyncHost()
        dialog = SubtitleSyncDialog(host, selected_index=0)

        # Video start is 2.0s, first sub starts at 0.32s -> delta is +1.68s (2.0 - 0.32)
        self.assertAlmostEqual(dialog.first_video_start, 2.0)
        dialog.btn_preset_video.click()
        self.assertAlmostEqual(dialog.spin_offset.value(), 1.68)

        # Select scope: All
        dialog.radio_all.setChecked(True)
        # Apply
        dialog._on_apply()

        # Both current_segments and current_translated_segments should be shifted by +1.68s
        self.assertAlmostEqual(host.current_segments[0]["start"], 2.00)
        self.assertAlmostEqual(host.current_translated_segments[0]["start"], 2.00)

    def test_subtitle_sync_dialog_ripple_from_selected(self):
        host = DummySyncHost()
        # Cue 0: 0.32 -> 2.50
        # Cue 1: 2.60 -> 4.80 (selected)
        # Cue 2: 5.00 -> 7.20
        dialog = SubtitleSyncDialog(host, selected_index=1)
        dialog.radio_ripple.setChecked(True)
        dialog.spin_offset.setValue(1.0)
        dialog.chk_shift_all.setChecked(False) # direct shift
        dialog._on_apply()

        # Cue 0 untouched
        self.assertAlmostEqual(host.current_translated_segments[0]["start"], 0.32)
        # Cue 1 shifted +1.0 -> 3.60
        self.assertAlmostEqual(host.current_translated_segments[1]["start"], 3.60)
        # Cue 2 shifted +1.0 -> 6.00
        self.assertAlmostEqual(host.current_translated_segments[2]["start"], 6.00)


if __name__ == "__main__":
    unittest.main()

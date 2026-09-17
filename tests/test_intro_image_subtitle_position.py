import os
import sys
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
UI_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ui"))
for p in (APP_DIR, UI_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from PySide6.QtWidgets import QApplication
from ui.features.multi_video_timeline import MultiVideoTimelineMixin
from ui.features.voice_subtitle_preview import VoiceSubtitlePreviewMixin
from ui.features.project_state import ProjectStateMixin


class DummyPlayer:
    def __init__(self, pos=0):
        self._pos = pos
        self._source_path = ""
    def position(self):
        return self._pos
    def setPosition(self, pos, global_pos=None):
        self._pos = pos


class DummyHost(MultiVideoTimelineMixin, VoiceSubtitlePreviewMixin, ProjectStateMixin):
    def __init__(self):
        self.media_player = DummyPlayer(1000)
        self.timeline = MagicMock()
        self._timeline_global_position_ms = 0
        self._timeline_preview_source = ""
        self.live_preview_segments = [
            {"start": 2.5, "end": 4.2, "text": "Lời thoại video gốc"}
        ]
        self.current_segments = list(self.live_preview_segments)
        self.current_translated_segments = list(self.live_preview_segments)
        self._selected_segment_index = -1
        self.last_preview_video_path = ""
        self.video_view = MagicMock()
        self._subtitle_track_preview_visible = True
        self._preview_video_has_burned_subtitles = False

    def _normalize_local_file_path(self, path):
        return str(path or "")

    def get_timeline_video_clips(self, existing_only=True):
        return [
            {
                "source": os.path.abspath("intro.png"),
                "source_start": 0.0,
                "source_duration": 2.0,
                "speed": 1.0,
                "timeline_start": 0.0,
                "timeline_end": 2.0,
            },
            {
                "source": os.path.abspath("main_video.mp4"),
                "source_start": 0.0,
                "source_duration": 10.0,
                "speed": 1.0,
                "timeline_start": 2.0,
                "timeline_end": 12.0,
            },
        ]

    def _preview_is_playing(self):
        return False


class TestIntroImageSubtitlePosition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_timeline_position_ms_calculates_global_time(self):
        host = DummyHost()
        # Active source is main_video.mp4, local player position is 1000ms (1.0s into video)
        host.media_player._source_path = os.path.abspath("main_video.mp4")
        host.media_player._pos = 1000

        global_pos = host.timeline_position_ms()
        # Intro is 2.0s (2000ms), so 1000ms into video = 3000ms global time
        self.assertEqual(global_pos, 3000)
        self.assertAlmostEqual(host.timeline_position_seconds(), 3.0)

    def test_active_subtitle_index_found_with_intro_image(self):
        host = DummyHost()
        host.media_player._source_path = os.path.abspath("main_video.mp4")
        host.media_player._pos = 1000  # local 1.0s into video -> global 3.0s

        # Subtitle cue is [2.5s, 4.2s] (2500ms to 4200ms)
        items = host.live_preview_segments
        indices = host._find_active_segment_indices(host.timeline_position_ms(), items)
        self.assertEqual(indices, [0])

    def test_project_state_mismatch_not_triggered_by_intro_image(self):
        canonical_video = os.path.abspath("main_video.mp4")
        intro_img = os.path.abspath("intro.png")
        state = MagicMock()
        state.input_video = canonical_video
        state.artifacts = {}
        state.settings = {
            "timeline_video_clips": [
                {"source": intro_img, "timeline_start": 0.0, "timeline_end": 2.0},
                {"source": canonical_video, "timeline_start": 2.0, "timeline_end": 12.0},
            ]
        }
        host = DummyHost()
        
        # Test lineage check logic directly
        st = state.settings
        lineage = list(st.get("timeline_video_clips") or [])
        lineage_sources = [
            os.path.normcase(os.path.abspath(str(item.get("source", "") or "")))
            for item in lineage if isinstance(item, dict) and item.get("source")
        ]
        canonical_source = os.path.normcase(os.path.abspath(str(state.input_video or "")))
        recap_source_for_lineage = ""
        from app.services.timeline_video_sequence import is_image_file
        first_video_in_lineage = next(
            (src for src in lineage_sources if not is_image_file(src)),
            lineage_sources[0] if lineage_sources else None
        )
        mismatch = (
            bool(lineage_sources)
            and lineage_sources[0] not in {canonical_source, recap_source_for_lineage}
            and first_video_in_lineage not in {canonical_source, recap_source_for_lineage}
        )
        self.assertFalse(mismatch)

    def test_video_view_caches_and_restores_video_dimensions_after_image(self):
        from ui.widgets.video_view import VideoView
        view = VideoView()
        # Set 1920x1080 video dimensions
        view.set_video_dimensions(1920, 1080)
        self.assertEqual(view.video_source_width, 1920)
        self.assertEqual(view.video_source_height, 1080)
        self.assertEqual(getattr(view, "_last_video_width", 0), 1920)
        self.assertEqual(getattr(view, "_last_video_height", 0), 1080)

        # Clear image source should maintain/restore video dimensions
        view.clear_image_source()
        self.assertEqual(view.video_source_width, 1920)
        self.assertEqual(view.video_source_height, 1080)
        view.deleteLater()

    def test_align_segments_to_video_start_offsets_relative_srt(self):
        from ui.helpers.srt_helpers import align_segments_to_video_start
        # Video starts at 2.0s after an intro image
        raw_srt_segments = [
            {"start": 0.5, "end": 2.5, "text": "Câu nói 1"},
            {"start": 3.0, "end": 5.0, "text": "Câu nói 2"},
        ]
        aligned = align_segments_to_video_start(raw_srt_segments, first_video_start=2.0)
        self.assertEqual(len(aligned), 2)
        # Cue 1 starts at 2.0 + 0.5 = 2.5s (matching video)
        self.assertAlmostEqual(aligned[0]["start"], 2.5)
        self.assertAlmostEqual(aligned[0]["end"], 4.5)
        # Cue 2 starts at 2.0 + 3.0 = 5.0s
        self.assertAlmostEqual(aligned[1]["start"], 5.0)
        self.assertAlmostEqual(aligned[1]["end"], 7.0)

    def test_align_segments_to_video_start_drops_intro_and_clamps_onset(self):
        from ui.helpers.srt_helpers import align_segments_to_video_start
        # Whisper VAD lookback into silence or speech during intro image [0, 2.0s]
        segments = [
            {"start": 0.1, "end": 1.8, "text": "Noise / intro filler"},
            {"start": 1.65, "end": 4.0, "text": "First real dialogue"},
        ]
        aligned = align_segments_to_video_start(segments, first_video_start=2.0, offset_if_relative=False)
        # First cue was entirely in the intro (end <= 2.0s), so dropped!
        # Second cue overlapped intro, so clamped to 2.0s!
        self.assertEqual(len(aligned), 1)
        self.assertEqual(aligned[0]["text"], "First real dialogue")
        self.assertAlmostEqual(aligned[0]["start"], 2.0)
        self.assertAlmostEqual(aligned[0]["end"], 4.0)

    def test_translation_srt_utils_align_segments_to_video_start(self):
        from translation.srt_utils import align_segments_to_video_start
        raw_segments = [
            {"start": 0.0, "end": 2.0, "text": "Intro speech"},
            {"start": 0.2, "end": 3.0, "text": "Main speech"},
        ]
        aligned = align_segments_to_video_start(raw_segments, first_video_start=3.5)
        # Shifted by +3.5s
        self.assertAlmostEqual(aligned[0]["start"], 3.5)
        self.assertAlmostEqual(aligned[0]["end"], 5.5)
        self.assertAlmostEqual(aligned[1]["start"], 3.7)


if __name__ == "__main__":
    unittest.main()


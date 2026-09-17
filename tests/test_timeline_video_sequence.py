import os
import subprocess
import tempfile
import unittest
import sys
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from app.layers.timeline import Timeline
from app.services.timeline_video_sequence import (
    append_video,
    insert_media,
    is_image_file,
    move_video,
    normalize_v1_sequence,
    remove_video,
    resolve_timeline_time,
    timeline_video_clips,
)


class TimelineVideoSequenceTests(unittest.TestCase):
    def test_restored_stale_duration_is_repaired_from_source(self):
        from PySide6.QtWidgets import QApplication
        from app.layers.base import LayerType
        from app.layers.blur import BlurLayer
        from ui.views.editor.timeline import EditorTimeline

        app = QApplication.instance() or QApplication([])
        widget = EditorTimeline()
        model = Timeline(duration=784.0)
        append_video(model, "episode.mp4", 784.0)
        blur_track = model.add_track("B1", LayerType.BLUR)
        blur_track.layers.append(BlurLayer(start=0.0, end=784.0))
        model.duration = 784.0
        widget._timeline = model
        widget._duration = 784.0

        with patch.object(EditorTimeline, "_probe_video_duration", return_value=362.0):
            widget.set_video_source("episode.mp4", 362.0)

        self.assertAlmostEqual(widget.duration / 1000.0, 362.0)
        self.assertAlmostEqual(model.duration, 362.0)
        self.assertAlmostEqual(blur_track.layers[0].end, 362.0)
        widget.deleteLater()
        app.processEvents()

    def test_refreshing_source_does_not_replace_multi_video_sequence(self):
        from app.layers.sync_bridge import ensure_v1_a1_tracks

        model = Timeline()
        append_video(model, "episode_1.mp4", 10.0)
        append_video(model, "episode_2.mp4", 20.0)
        ensure_v1_a1_tracks(model, "episode_2.mp4", 10.0)

        self.assertEqual(
            [os.path.basename(clip.source) for clip in timeline_video_clips(model)],
            ["episode_1.mp4", "episode_2.mp4"],
        )
        self.assertAlmostEqual(model.duration, 30.0)

    def test_append_reorder_remove_and_time_mapping(self):
        timeline = Timeline()
        first = append_video(timeline, "episode_1.mp4", 10.0)
        second = append_video(timeline, "episode_2.mp4", 20.0)
        clips = timeline_video_clips(timeline)
        self.assertEqual([clip.timeline_start for clip in clips], [0.0, 10.0])
        self.assertEqual(timeline.duration, 30.0)

        self.assertTrue(move_video(timeline, second.id, -1))
        clips = timeline_video_clips(timeline)
        self.assertEqual([os.path.basename(clip.source) for clip in clips], ["episode_2.mp4", "episode_1.mp4"])
        clip, local = resolve_timeline_time(timeline, 21.5)
        self.assertEqual(os.path.basename(clip.source), "episode_1.mp4")
        self.assertAlmostEqual(local, 1.5)

        self.assertTrue(remove_video(timeline, second.id))
        self.assertEqual(timeline.duration, 10.0)
        self.assertEqual(len(timeline_video_clips(timeline)), 1)
        audio_tracks = [track for track in timeline.tracks if track.name.startswith("A1")]
        self.assertEqual(len(audio_tracks[0].layers), 1)
        self.assertEqual(audio_tracks[0].layers[0].metadata["video_layer_id"], first.id)

    def test_normalize_preserves_trim_and_speed(self):
        timeline = Timeline()
        first = append_video(timeline, "one.mp4", 5.0)
        append_video(timeline, "two.mp4", 8.0)
        first.source_start = 2.0
        first.speed = 2.0
        first.end = 3.0
        normalize_v1_sequence(timeline)
        clips = timeline_video_clips(timeline)
        self.assertEqual(clips[0].source_start, 2.0)
        self.assertEqual(clips[0].source_duration, 6.0)
        self.assertEqual(clips[1].timeline_start, 3.0)
        self.assertEqual(timeline.duration, 11.0)

    def test_preview_seek_uses_actual_player_source_not_stale_cache(self):
        """A stale preview cache must never seek V1 using V2 local time."""
        from ui.features.multi_video_timeline import MultiVideoTimelineMixin

        class _Player:
            def __init__(self):
                self._source_path = ""
                self.position_ms = 0

            def setSource(self, url):
                self._source_path = url.toLocalFile()

            def setPosition(self, position):
                self.position_ms = int(position)

        class _TimelineWidget:
            def __init__(self, model):
                self._timeline = model
                self._playhead = 0.0

            def set_playhead(self, seconds):
                self._playhead = float(seconds)

            def set_position(self, position):
                self._playhead = float(position) / 1000.0

        class _Gui(MultiVideoTimelineMixin):
            def __init__(self, model):
                self.timeline = _TimelineWidget(model)
                self.media_player = _Player()
                self._timeline_preview_source = ""
                self._timeline_global_position_ms = 0

            def update_duration_label(self, *_args):
                pass

            def refresh_timed_layer_preview(self, *_args):
                pass

            def update_playback_subtitle_highlight(self, *_args):
                pass

        with tempfile.TemporaryDirectory() as temp_dir:
            first_path = os.path.join(temp_dir, "first.fixture")
            second_path = os.path.join(temp_dir, "second.fixture")
            for path in (first_path, second_path):
                with open(path, "wb"):
                    pass
            timeline = Timeline()
            append_video(timeline, first_path, 10.0)
            append_video(timeline, second_path, 10.0)
            gui = _Gui(timeline)
            gui._timeline_preview_source = second_path  # stale optimistic cache
            gui.media_player._source_path = first_path  # player was reset by another preview path

            gui.seek_timeline_video(12.5)

            self.assertEqual(os.path.abspath(gui.media_player._source_path), os.path.abspath(second_path))
            self.assertEqual(gui.media_player.position_ms, 2500)

    def test_single_video_playback_updates_resume_position(self):
        from ui.features.multi_video_timeline import MultiVideoTimelineMixin

        class _Player:
            def __init__(self, source):
                self._source_path = source

        class _TimelineWidget:
            def __init__(self, model):
                self._timeline = model
                self.position_ms = 0

            def set_position(self, position):
                self.position_ms = int(position)

        class _Gui(MultiVideoTimelineMixin):
            def __init__(self, model, source):
                self.timeline = _TimelineWidget(model)
                self.media_player = _Player(source)
                self._timeline_preview_source = source
                self._timeline_global_position_ms = 0
                self.last_preview_video_path = ""

            def update_duration_label(self, *_args):
                pass

            def refresh_timed_layer_preview(self, *_args):
                pass

            def update_playback_subtitle_highlight(self, *_args):
                pass

        with tempfile.TemporaryDirectory() as temp_dir:
            source = os.path.join(temp_dir, "episode.fixture")
            with open(source, "wb"):
                pass
            timeline = Timeline()
            append_video(timeline, source, 10.0)
            gui = _Gui(timeline, source)

            self.assertTrue(gui.handle_sequence_position_changed(4250))
            self.assertEqual(gui._timeline_global_position_ms, 4250)
            self.assertEqual(gui.timeline.position_ms, 4250)

    def test_video_clip_selection_does_not_seek_playhead(self):
        import importlib.util

        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication

        timeline_path = os.path.join(
            os.path.dirname(__file__), "..", "ui", "views", "editor", "timeline.py"
        )
        spec = importlib.util.spec_from_file_location("test_editor_timeline", timeline_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        EditorTimeline = module.EditorTimeline

        app = QApplication.instance() or QApplication([])
        widget = EditorTimeline()
        model = Timeline()
        append_video(model, "episode.mp4", 20.0)
        widget._timeline = model
        widget._duration = 20.0
        widget.resize(900, 300)
        widget._rebuild_track_heights()
        widget._redraw()
        widget.show()
        app.processEvents()
        requested = []
        widget.seekRequestedMs.connect(requested.append)

        clip_x = widget.CONTENT_LEFT_PAD + int(5.0 * widget.pixels_per_second)
        QTest.mouseClick(
            widget.viewport(), Qt.LeftButton, Qt.NoModifier,
            QPoint(clip_x, widget.RULER_HEIGHT + 20),
        )

        self.assertEqual(requested, [])
        self.assertAlmostEqual(widget._playhead, 0.0)

        ruler_x = widget.CONTENT_LEFT_PAD + int(8.0 * widget.pixels_per_second)
        QTest.mouseClick(
            widget.viewport(), Qt.LeftButton, Qt.NoModifier,
            QPoint(ruler_x, widget.RULER_HEIGHT // 2),
        )
        self.assertEqual(requested, [8000])
        self.assertAlmostEqual(widget._playhead, 8.0)
        widget.deleteLater()
        app.processEvents()


class TimelineSequenceExportTests(unittest.TestCase):
    def test_one_pass_export_joins_two_inputs(self):
        from app.runtime_paths import bin_path, subprocess_hidden_kwargs
        from app.services.timeline_sequence_export import export_timeline_sequence

        ffmpeg = str(bin_path("ffmpeg", "ffmpeg.exe"))
        ffprobe = str(bin_path("ffmpeg", "ffprobe.exe"))
        if not os.path.isfile(ffmpeg) or not os.path.isfile(ffprobe):
            self.skipTest("Bundled FFmpeg is unavailable")
        with tempfile.TemporaryDirectory() as temp_dir:
            sources = []
            for index, color in enumerate(("red", "blue")):
                path = os.path.join(temp_dir, f"source_{index}.mp4")
                command = [
                    ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", f"color=c={color}:s=320x180:d=0.6:r=24",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=0.6",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", path,
                ]
                subprocess.run(command, check=True, capture_output=True, **subprocess_hidden_kwargs())
                sources.append(path)
            clips = [
                {
                    "source": path,
                    "source_start": 0.0,
                    "source_duration": 0.5,
                    "timeline_start": index * 0.5,
                    "timeline_end": (index + 1) * 0.5,
                    "speed": 1.0,
                    "volume": 1.0,
                    "muted": False,
                }
                for index, path in enumerate(sources)
            ]
            output = os.path.join(temp_dir, "timeline.mp4")
            export_timeline_sequence(clips, output, output_fps=24)
            probe = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", output],
                check=True, capture_output=True, text=True, **subprocess_hidden_kwargs(),
            )
            self.assertTrue(os.path.isfile(output))
            self.assertAlmostEqual(float(probe.stdout.strip()), 1.0, delta=0.15)

            external_audio = os.path.join(temp_dir, "voice.wav")
            subprocess.run(
                [
                    ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "sine=frequency=660:duration=1.0",
                    "-c:a", "pcm_s16le", external_audio,
                ],
                check=True, capture_output=True, **subprocess_hidden_kwargs(),
            )
            voice_output = os.path.join(temp_dir, "timeline_voice.mp4")
            export_timeline_sequence(
                clips,
                voice_output,
                mode="voice",
                audio_path=external_audio,
                output_fps=24,
            )
            voice_probe = subprocess.run(
                [
                    ffprobe, "-v", "error", "-select_streams", "a:0",
                    "-show_entries", "stream=codec_name", "-of", "csv=p=0", voice_output,
                ],
                check=True, capture_output=True, text=True, **subprocess_hidden_kwargs(),
            )
            self.assertEqual(voice_probe.stdout.strip(), "aac")

            from workflows.prepare_workflow import PrepareWorkflow

            timeline_audio = os.path.join(temp_dir, "timeline_audio.wav")
            self.assertTrue(PrepareWorkflow(temp_dir)._extract_timeline_audio(clips, timeline_audio))
            audio_probe = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", timeline_audio],
                check=True, capture_output=True, text=True, **subprocess_hidden_kwargs(),
            )
            self.assertAlmostEqual(float(audio_probe.stdout.strip()), 1.0, delta=0.08)


    def test_insert_media_intro_image_and_properties(self):
        self.assertTrue(is_image_file("cover.PNG"))
        self.assertTrue(is_image_file("slide.jpg"))
        self.assertTrue(is_image_file("photo.webp"))
        self.assertFalse(is_image_file("clip.mp4"))

        timeline = Timeline()
        append_video(timeline, "main_video.mp4", 10.0)
        intro_layer = insert_media(timeline, "intro.png", 3.0, index=0)
        
        clips = timeline_video_clips(timeline)
        self.assertEqual(len(clips), 2)
        self.assertEqual(os.path.basename(clips[0].source), "intro.png")
        self.assertTrue(clips[0].is_image)
        self.assertAlmostEqual(clips[0].timeline_start, 0.0)
        self.assertAlmostEqual(clips[0].timeline_end, 3.0)

        self.assertEqual(os.path.basename(clips[1].source), "main_video.mp4")
        self.assertFalse(clips[1].is_image)
        self.assertAlmostEqual(clips[1].timeline_start, 3.0)
        self.assertAlmostEqual(clips[1].timeline_end, 13.0)
        self.assertAlmostEqual(timeline.duration, 13.0)

        # Check A1 audio track: image has NO audio layer, only video does
        audio_tracks = [track for track in timeline.tracks if track.name.startswith("A1")]
        self.assertTrue(len(audio_tracks) > 0)
        self.assertEqual(len(audio_tracks[0].layers), 1)
        video_audio = audio_tracks[0].layers[0]
        self.assertEqual(video_audio.volume, 1.0)
        self.assertFalse(video_audio.muted)
        self.assertAlmostEqual(video_audio.start, 3.0)
        self.assertAlmostEqual(video_audio.end, 13.0)

    def test_shift_timeline_timed_elements_keeps_subtitles_synced_with_video(self):
        from ui.features.multi_video_timeline import MultiVideoTimelineMixin

        class DummyGui(MultiVideoTimelineMixin):
            def __init__(self, timeline_model):
                self.timeline = type("Widget", (), {"_timeline": timeline_model, "set_duration": lambda *a: None, "_redraw": lambda *a: None})()
                self.current_segments = [{"start": 1.0, "end": 3.0, "text": "Hello"}]
                self.current_translated_segments = [{"start": 1.0, "end": 3.0, "text": "Xin chào"}]

        timeline = Timeline()
        vid = append_video(timeline, "vid.mp4", 10.0)
        gui = DummyGui(timeline)

        # 1. Insert 2.5s intro image at front
        first_vid_before = vid.start  # 0.0
        insert_media(timeline, "intro.png", 2.5, index=0)
        first_vid_after = vid.start   # 2.5
        shift = first_vid_after - first_vid_before
        gui.shift_timeline_timed_elements(shift)

        # Subtitle should be shifted by +2.5s
        self.assertAlmostEqual(gui.current_segments[0]["start"], 3.5)
        self.assertAlmostEqual(gui.current_segments[0]["end"], 5.5)
        # Relative offset to video start remains 1.0s (exact sync with speech)
        self.assertAlmostEqual(gui.current_segments[0]["start"] - vid.start, 1.0)

        # 2. User trims intro image down to 1.5s (delta = -1.0s)
        intro_layer = timeline.tracks[0].layers[0]
        intro_layer.end = 1.5
        first_vid_before = vid.start  # 2.5
        normalize_v1_sequence(timeline)
        first_vid_after = vid.start   # 1.5 (video rippled close, no gap!)
        self.assertAlmostEqual(vid.start, 1.5)
        self.assertAlmostEqual(intro_layer.end, 1.5)

        shift = first_vid_after - first_vid_before  # -1.0s
        gui.shift_timeline_timed_elements(shift)

        # Subtitle should be shifted to 2.5s
        self.assertAlmostEqual(gui.current_segments[0]["start"], 2.5)
        self.assertAlmostEqual(gui.current_segments[0]["end"], 4.5)
        # Relative offset to video start remains exactly 1.0s!
        self.assertAlmostEqual(gui.current_segments[0]["start"] - vid.start, 1.0)

    def test_export_timeline_with_intro_image(self):
        from app.services.timeline_sequence_export import export_timeline_sequence
        from runtime_paths import bin_path, subprocess_hidden_kwargs

        ffmpeg = bin_path("ffmpeg", "ffmpeg.exe")
        ffprobe = bin_path("ffmpeg", "ffprobe.exe")
        if not (os.path.isfile(ffmpeg) and os.path.isfile(ffprobe)):
            self.skipTest("ffmpeg binaries unavailable")

        with tempfile.TemporaryDirectory() as temp_dir:
            img_path = os.path.join(temp_dir, "intro.png")
            vid_path = os.path.join(temp_dir, "video.mp4")
            
            # Generate 1-frame image fixture
            subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                 "-f", "lavfi", "-i", "color=c=red:s=320x240:d=1",
                 "-frames:v", "1", img_path],
                check=True, capture_output=True, **subprocess_hidden_kwargs(),
            )
            # Generate 1-second video fixture with audio
            subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                 "-f", "lavfi", "-i", "testsrc=size=320x240:rate=24:duration=1.0",
                 "-f", "lavfi", "-i", "sine=frequency=440:duration=1.0",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", vid_path],
                check=True, capture_output=True, **subprocess_hidden_kwargs(),
            )

            timeline = Timeline()
            append_video(timeline, vid_path, 1.0)
            insert_media(timeline, img_path, 1.0, index=0)
            clips = [clip.to_dict() for clip in timeline_video_clips(timeline)]

            output = os.path.join(temp_dir, "intro_and_video.mp4")
            export_timeline_sequence(clips, output, output_fps=24)
            self.assertTrue(os.path.isfile(output))

            probe = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", output],
                check=True, capture_output=True, text=True, **subprocess_hidden_kwargs(),
            )
            self.assertAlmostEqual(float(probe.stdout.strip()), 2.0, delta=0.25)

if __name__ == "__main__":
    unittest.main()

import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QTextEdit

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path[:0] = [os.path.join(ROOT, "ui"), os.path.join(ROOT, "app"), ROOT]
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from app.layers.base import LayerType
from app.layers.blur import BlurLayer
from app.layers.text import TextLayer
from app.layers.timeline import Timeline, Track
from app.core.state import ProjectState
from app.services.timeline_video_sequence import append_video, timeline_video_clips
from app.services import GUIProjectBridge, ProjectService
from main_window import VideoTranslatorGUI


class TestStudioShellIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = VideoTranslatorGUI()

    def tearDown(self):
        for timer in self.window.findChildren(QTimer):
            timer.stop()
        self.window.hide()
        self.window.deleteLater()
        self.app.processEvents()

    def test_selected_blur_uses_the_real_editable_inspector(self):
        timeline = Timeline(duration=10.0)
        track = Track(name="B1", type=LayerType.BLUR, height=60)
        layer = BlurLayer(name="Blur 1", start=1.0, end=6.0)
        track.layers.append(layer)
        timeline.tracks.append(track)
        self.window.timeline._timeline = timeline
        self.window.timeline._duration = timeline.duration
        self.window.timeline._selected_layer_id = layer.id

        self.window.on_timeline_layer_selected(layer.id)
        QTest.qWait(1)

        self.assertEqual(self.window.inspector_stack.currentIndex(), 2)
        if hasattr(self.window, "blur_inspector_radius_slider"):
            self.window.blur_inspector_radius_slider.setValue(9)
            self.window.blur_inspector_start_spin.setValue(2.0)
            self.assertEqual(layer.blur_strength, 9)
            self.assertEqual(layer.start, 2.0)

    def test_blur_controls_update_selected_region_without_replacing_others(self):
        timeline = Timeline(duration=10.0)
        track = Track(name="B1", type=LayerType.BLUR, height=60)
        first = BlurLayer(name="Blur 1", start=0.0, end=10.0,
                          position_x=0.1, position_y=0.1, width=0.3, height=0.2)
        second = BlurLayer(name="Blur 2", start=0.0, end=10.0,
                           position_x=0.5, position_y=0.6, width=0.4, height=0.2)
        track.layers.extend([first, second])
        timeline.tracks.append(track)
        self.window.timeline._timeline = timeline
        self.window.timeline._duration = timeline.duration
        self.window.timeline._selected_layer_id = second.id
        self.window.video_view.set_blur_regions_normalized([
            {"x": first.position_x, "y": first.position_y,
             "width": first.width, "height": first.height},
            {"x": second.position_x, "y": second.position_y,
             "width": second.width, "height": second.height},
        ])

        self.window.on_timeline_layer_selected(second.id)
        self.window.blur_inspector_radius_slider.setValue(55)
        self.window.blur_inspector_opacity_slider.setValue(40)
        self.window.blur_inspector_pixelate_cb.setChecked(True)
        self.window.blur_inspector_pixel_size_slider.setValue(24)
        QTest.qWait(1)

        self.assertEqual(first.blur_strength, 36.0)
        self.assertEqual(second.blur_strength, 55)
        self.assertAlmostEqual(second.blur_opacity, 0.4)
        self.assertTrue(second.pixelate)
        self.assertEqual(second.pixelate_size, 24)
        regions = self.window.video_view.get_blur_region_normalized()
        self.assertIsInstance(regions, list)
        self.assertEqual(len(regions), 2)

    def test_blur_slider_recovers_when_preview_overlay_has_no_regions(self):
        timeline = Timeline(duration=10.0)
        track = Track(name="B1", type=LayerType.BLUR, height=60)
        layer = BlurLayer(name="Blur 1", start=0.0, end=10.0,
                          position_x=0.2, position_y=0.7, width=0.6, height=0.15)
        track.layers.append(layer)
        timeline.tracks.append(track)
        self.window.timeline._timeline = timeline
        self.window.timeline._duration = timeline.duration
        self.window.timeline._selected_layer_id = layer.id
        self.window._blur_inspector_layer_id = layer.id
        self.window.video_view.set_blur_regions_normalized([])
        applied = []
        self.window.apply_preview_blur_region = (
            lambda *, regions=None, force=False: applied.append((regions, force))
        )

        self.window._show_blur_inspector_for_track(track, layer)
        self.window.blur_inspector_radius_slider.setValue(61)
        QTest.qWait(1)

        regions = self.window.video_view.get_blur_region_normalized()
        self.assertEqual(layer.blur_strength, 61)
        self.assertIsInstance(regions, dict)
        self.assertEqual(int(applied[-1][0][0]["blur_strength"]), 61)
        self.assertTrue(applied[-1][1])

    def test_blur_drag_keeps_selected_layer_identity_for_followup_slider_edit(self):
        timeline = Timeline(duration=10.0)
        track = Track(name="B1", type=LayerType.BLUR, height=60)
        layer = BlurLayer(name="Blur 1", start=1.0, end=8.0,
                          position_x=0.1, position_y=0.7, width=0.5, height=0.15)
        track.layers.append(layer)
        timeline.tracks.append(track)
        self.window.timeline._timeline = timeline
        self.window.timeline._duration = timeline.duration
        self.window.timeline._selected_layer_id = layer.id
        self.window._blur_inspector_layer_id = layer.id
        self.window.video_view.set_blur_regions_normalized([{
            "x": 0.2, "y": 0.75, "width": 0.6, "height": 0.12,
            "blur_strength": 36, "blur_opacity": 1.0,
        }])

        self.window.on_preview_blur_region_changed()

        self.assertIs(track.layers[0], layer)
        self.assertEqual(track.layers[0].id, self.window.timeline._selected_layer_id)
        self.assertAlmostEqual(layer.position_x, 0.2)
        self.assertAlmostEqual(layer.start, 1.0)
        self.assertAlmostEqual(layer.end, 8.0)

    def test_add_text_enters_preview_edit_path_and_is_rendered(self):
        with tempfile.TemporaryDirectory() as folder:
            video_path = Path(folder) / "source.mp4"
            video_path.touch()
            timeline = Timeline(duration=10.0)
            self.window.timeline._timeline = timeline
            self.window.timeline._duration = timeline.duration

            with patch.object(self.window, "resolve_canonical_video_path", return_value=str(video_path)):
                self.window.on_add_timeline_layer("text")
            QTest.qWait(1)

            text_tracks = [track for track in timeline.tracks if track.type == LayerType.TEXT]
            self.assertEqual(len(text_tracks), 1)
            self.assertEqual(len(text_tracks[0].layers), 1)
            layer = text_tracks[0].layers[0]
            self.assertIsInstance(layer, TextLayer)
            self.assertEqual(self.window.timeline._selected_layer_id, layer.id)
            self.assertEqual(self.window._preview_edit_layer_id, layer.id)
            self.assertIsNotNone(self.window.video_view.text_overlay)
            self.assertEqual(self.window.video_view.text_overlay._items[0]["text"], "New text layer")
            self.assertEqual(self.window.video_view.text_overlay._active_id, layer.id)

    def test_open_blur_inspector_keeps_editing_region_after_timeline_selection_changes(self):
        timeline = Timeline(duration=10.0)
        track = Track(name="B1", type=LayerType.BLUR, height=60)
        layer = BlurLayer(name="Blur 1", start=0.0, end=10.0)
        track.layers.append(layer)
        timeline.tracks.append(track)
        self.window.timeline._timeline = timeline
        self.window.timeline._duration = timeline.duration
        self.window.timeline._selected_layer_id = layer.id
        self.window.video_view.set_blur_regions_normalized([{
            "x": layer.position_x, "y": layer.position_y,
            "width": layer.width, "height": layer.height,
        }])
        applied = []
        self.window.apply_preview_blur_region = (
            lambda *, regions=None, force=False: applied.append((regions, force))
        )

        self.window.on_timeline_layer_selected(layer.id)
        self.window.timeline._selected_layer_id = "subtitle-auto-selection"
        self.window.blur_inspector_radius_slider.setValue(60)
        QTest.qWait(1)

        self.assertEqual(layer.blur_strength, 60)
        self.assertEqual(
            self.window.blur_inspector_radius_value_label.text(),
            f"60 / {self.window.blur_inspector_radius_slider.maximum()}",
        )
        self.assertEqual(int(applied[-1][0][0]["blur_strength"]), 60)
        self.assertTrue(applied[-1][1])

    def test_track_label_click_selects_layer_and_opens_inspector(self):
        timeline = Timeline(duration=10.0)
        track = Track(name="B1", type=LayerType.BLUR, height=60)
        layer = BlurLayer(name="Blur 1", start=0.0, end=10.0)
        track.layers.append(layer)
        timeline.tracks.append(track)
        self.window.timeline._timeline = timeline
        self.window.timeline._duration = timeline.duration

        self.window.on_track_label_selected("B1")
        QTest.qWait(1)

        self.assertEqual(self.window.timeline._selected_layer_id, layer.id)
        self.assertEqual(self.window.inspector_stack.currentIndex(), 2)

    def test_layer_menu_is_available_for_any_loaded_video(self):
        with tempfile.TemporaryDirectory() as folder:
            video_path = Path(folder) / "source.mp4"
            video_path.touch()
            self.window.video_path_edit.setText(str(video_path))
            self.window.current_segments = []
            self.window.current_translated_segments = []

            self.window.refresh_ui_state()

            self.assertTrue(self.window.add_layer_btn.isEnabled())
            self.assertTrue(self.window.timeline_layers_btn.isEnabled())

    def test_more_menu_imports_srt_without_existing_subtitles(self):
        with tempfile.TemporaryDirectory() as folder:
            video_path = Path(folder) / "source.mp4"
            video_path.touch()
            srt_path = Path(folder) / "imported_vi.srt"
            srt_path.write_text(
                "1\n00:00:01,000 --> 00:00:02,500\nXin chào\n\n"
                "2\n00:00:03,000 --> 00:00:04,000\nTạm biệt\n",
                encoding="utf-8",
            )
            timeline = Timeline(duration=10.0)
            self.window.timeline._timeline = timeline
            self.window.timeline._duration = timeline.duration
            self.window.current_segments = []
            self.window.current_translated_segments = []

            with patch.object(self.window, "resolve_canonical_video_path", return_value=str(video_path)), \
                 patch("features.voice_subtitle_preview.QFileDialog.getOpenFileName", return_value=(str(srt_path), "Subtitle Files (*.srt)")), \
                 patch("features.voice_subtitle_preview.QMessageBox.information"), \
                 patch.object(self.window, "schedule_timeline_visual_refresh"), \
                 patch.object(self.window, "sync_live_subtitle_preview"), \
                 patch.object(self.window, "schedule_live_subtitle_preview_refresh"):
                self.window.refresh_ui_state()
                self.assertTrue(self.window.import_subtitle_action.isEnabled())
                self.window.import_subtitle_action.trigger()
                QTest.qWait(1)

            self.assertEqual(
                [segment["text"] for segment in self.window.current_translated_segments],
                ["Xin chào", "Tạm biệt"],
            )
            subtitle_tracks = [track for track in timeline.tracks if track.type == LayerType.DUB_SUBTITLE]
            self.assertEqual(len(subtitle_tracks), 1)
            self.assertEqual(len(subtitle_tracks[0].layers), 2)
            self.assertEqual(subtitle_tracks[0].layers[0].text, "Xin chào")

    def test_original_transcript_enables_translation_exchange_editor(self):
        self.window.current_segments = [
            {"start": 1.0, "end": 2.0, "text": "原文"},
        ]
        self.window.current_translated_segments = []

        self.window.refresh_ui_state()

        self.assertTrue(self.window.subtitle_editor_btn.isEnabled())

    @patch("ui.features.pipeline_lifecycle.QMessageBox.information")
    def test_editor_can_create_translation_from_original_only(self, _message):
        self.window.current_segments = [
            {"start": 1.0, "end": 2.0, "text": "原文"},
        ]
        self.window.current_translated_segments = []

        applied = self.window._apply_subtitle_editor_changes([
            {"text": "Bản dịch", "deleted": False},
        ])

        self.assertTrue(applied)
        self.assertEqual(self.window.current_segments[0]["text"], "原文")
        self.assertEqual(self.window.current_translated_segments[0]["text"], "Bản dịch")

    @patch("ui.features.timeline_editing.QMessageBox.question")
    def test_clear_ts1_removes_original_and_translated_canonical_data(self, question):
        from PySide6.QtWidgets import QMessageBox

        question.return_value = QMessageBox.Yes
        self.window.current_segments = [
            {"start": 1.0, "end": 2.0, "text": "原文"},
        ]
        self.window.current_translated_segments = [
            {"start": 1.0, "end": 2.0, "text": "Bản dịch"},
        ]
        self.window.apply_segments_to_timeline()

        self.window.clear_timeline_track("TS1")

        self.assertEqual(self.window.current_segments, [])
        self.assertEqual(self.window.current_translated_segments, [])
        subtitle_track = next(track for track in self.window.timeline._timeline.tracks if track.name == "TS1")
        self.assertEqual(subtitle_track.layers, [])

    @patch("ui.features.pipeline_lifecycle.QMessageBox.information")
    def test_editor_delete_all_does_not_fall_back_to_original_subtitles(self, _message):
        self.window.current_segments = [
            {"start": 1.0, "end": 2.0, "text": "原文"},
        ]
        self.window.current_translated_segments = [
            {"start": 1.0, "end": 2.0, "text": "Bản dịch"},
        ]
        self.window.apply_segments_to_timeline()

        applied = self.window._apply_subtitle_editor_changes([
            {"text": "Bản dịch", "deleted": True},
        ])

        self.assertTrue(applied)
        self.assertEqual(self.window.current_segments, [])
        self.assertEqual(self.window.current_translated_segments, [])
        self.assertEqual(self.window.get_active_segments(), [])

    def test_timing_edit_commits_both_tracks_and_invalidates_old_voice(self):
        self.window.current_segments = [
            {"start": 1.0, "end": 2.0, "text": "原文", "_audio_end": 2.4},
        ]
        self.window.current_translated_segments = [
            {"start": 1.0, "end": 2.0, "text": "Bản dịch", "_audio_end": 2.4},
        ]
        with patch.object(self.window, "_invalidate_dubbed_output_after_subtitle_edit") as invalidate, \
                patch.object(self.window, "persist_current_timeline_project_data"), \
                patch.object(self.window, "_regenerate_original_srt_from_segments") as original_srt, \
                patch.object(self.window, "_regenerate_translated_srt_from_segments") as translated_srt:
            self.window.on_timeline_segment_timing_changed(0, 3.0, 4.0)

        self.assertEqual(
            (self.window.current_segments[0]["start"], self.window.current_segments[0]["end"]),
            (3.0, 4.0),
        )
        self.assertEqual(
            (self.window.current_translated_segments[0]["start"], self.window.current_translated_segments[0]["end"]),
            (3.0, 4.0),
        )
        invalidate.assert_called_once()
        original_srt.assert_called_once()
        translated_srt.assert_called_once()

    def test_inline_translation_edit_clears_stale_tts_override(self):
        self.window.current_segments = [
            {"start": 1.0, "end": 2.0, "text": "原文"},
        ]
        self.window.current_translated_segments = [{
            "start": 1.0,
            "end": 2.0,
            "text": "Bản cũ",
            "tts_text": "Giọng cũ",
            "dubbing_vi": "Giọng cũ",
            "voice_edited": True,
        }]
        editor = QTextEdit()
        editor.setPlainText("Bản mới")

        with patch.object(self.window, "_commit_subtitle_mutation") as commit:
            self.window.on_segment_translation_edited(0, editor)

        segment = self.window.current_translated_segments[0]
        self.assertEqual(segment["text"], "Bản mới")
        self.assertEqual(segment["tts_text"], "")
        self.assertEqual(segment["dubbing_vi"], "")
        self.assertFalse(segment["voice_edited"])
        commit.assert_called_once_with(selected_index=0, changed_indices={0})

    def test_original_srt_is_rewritten_from_current_timeline(self):
        with tempfile.TemporaryDirectory() as folder:
            out_path = os.path.join(folder, "original.srt")
            self.window.last_original_srt_path = out_path
            self.window.current_segments = [
                {"start": 3.0, "end": 4.0, "text": "住手"},
            ]
            with patch.object(self.window, "persist_transcription_project_data"):
                self.window._regenerate_original_srt_from_segments()

            content = Path(out_path).read_text(encoding="utf-8")
            self.assertIn("00:00:03,000 --> 00:00:04,000", content)
            self.assertIn("住手", content)

    def test_export_button_does_not_forward_clicked_boolean(self):
        calls = []
        self.window.export_final_video = lambda: calls.append(True)
        self.window.export_btn.setEnabled(True)

        self.window.export_btn.click()

        self.assertEqual(calls, [True])

    def test_subtitle_inspector_actions_are_compact_and_not_clipped(self):
        buttons = (
            self.window.rewrite_translation_btn,
            self.window.subtitle_editor_btn,
            self.window.import_translation_btn,
            self.window.audio_inspector_regenerate_voice_btn,
            self.window.inspector_delete_segment_btn,
        )

        self.assertEqual(
            [button.text() for button in buttons],
            ["Rewrite", "Edit", "Import SRT", "Voice", "Delete"],
        )
        self.assertTrue(all(button.height() == 32 for button in buttons))
        self.assertTrue(all(not button.icon().isNull() for button in buttons))
        occupied_width = sum(button.maximumWidth() for button in buttons) + (len(buttons) - 1) * 6
        available_width = self.window.inspector_stack.minimumWidth() - 20
        self.assertLessEqual(occupied_width, available_width)
        self.assertEqual(
            self.window.inspector_delete_segment_btn.objectName(),
            "subtitleInspectorDangerAction",
        )

    def test_target_language_selector_exposes_multilingual_pipeline(self):
        codes = {
            self.window.lang_target_combo.itemData(index)
            for index in range(self.window.lang_target_combo.count())
        }
        self.assertTrue({
            "vi", "en", "ja", "ko", "th", "id", "es", "fr", "de",
            "pt", "ru", "ar", "zh-CN", "zh-TW",
        }.issubset(codes))

    def test_timeline_zoom_icons_execute_real_actions(self):
        self.assertFalse(self.window.timeline_zoom_out_btn.icon().isNull())
        self.assertFalse(self.window.timeline_zoom_in_btn.icon().isNull())
        self.assertFalse(self.window.timeline_zoom_reset_btn.icon().isNull())
        before = self.window.timeline.zoom_percent()

        self.window.timeline_zoom_in_btn.click()
        QTest.qWait(1)

        self.assertGreater(self.window.timeline.zoom_percent(), before)
        self.window.timeline_zoom_reset_btn.click()
        self.assertEqual(self.window.timeline.zoom_percent(), 100)

    def test_locked_track_layer_remains_clickable_for_inspection(self):
        timeline = Timeline(duration=10.0)
        track = Track(name="B1", type=LayerType.BLUR, height=60, locked=True)
        layer = BlurLayer(name="Blur 1", start=0.0, end=10.0)
        track.layers.append(layer)
        timeline.tracks.append(track)
        widget = self.window.timeline
        widget._timeline = timeline
        widget._duration = timeline.duration
        widget._track_heights[track.id] = 60
        widget.resize(900, 220)
        widget.show()
        widget._redraw()
        spy = QSignalSpy(widget.layerSelected)
        x = widget.CONTENT_LEFT_PAD + round(5 * widget.pixels_per_second)
        y = widget.RULER_HEIGHT + 30

        QTest.mouseClick(widget.viewport(), Qt.LeftButton, pos=QPoint(x, y))

        self.assertEqual(widget._selected_layer_id, layer.id)
        self.assertEqual(spy.count(), 1)

    def test_project_identity_uses_imported_source_not_preview_field(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "video_1.mp4")
            preview = os.path.join(folder, "video_1_recap.mp4")
            Path(source).touch()
            Path(preview).touch()
            expected = ProjectState(
                project_id="video_1", project_root=folder, input_video=source,
                settings={"audio_handling_mode": self.window.get_audio_handling_mode()},
            )
            self.window._current_video_path = source
            self.window.video_path_edit.setText(preview)
            from unittest.mock import Mock
            self.window.project_bridge.ensure_project = Mock(return_value=expected)

            state = self.window.ensure_current_project()

            self.assertIs(state, expected)
            requested = self.window.project_bridge.ensure_project.call_args.kwargs["video_path"]
            self.assertEqual(os.path.abspath(requested), os.path.abspath(source))
            self.window.current_project_state = None

    def test_existing_project_language_tracks_visible_english_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            service = ProjectService(folder)
            state = ProjectState(
                project_id="english_import",
                project_root=folder,
                input_video=os.path.join(folder, "video.mp4"),
                target_language="vi",
                settings={"audio_handling_mode": self.window.get_audio_handling_mode()},
            )
            self.window.project_service = service
            self.window.current_project_state = state
            english_index = self.window.lang_target_combo.findData("en")
            self.assertGreaterEqual(english_index, 0)
            self.window.lang_target_combo.setCurrentIndex(english_index)

            resolved = self.window.ensure_current_project()

            self.assertEqual(resolved.target_language, "en")
            reopened = service.load_project(service.project_file(folder))
            self.assertEqual(reopened.target_language, "en")
            self.window.current_project_state = None

    def test_restored_timeline_from_another_video_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            first = os.path.join(folder, "video_1.mp4")
            second = os.path.join(folder, "video_2.mp4")
            Path(first).touch()
            Path(second).touch()
            stale = Timeline(duration=10.0)
            append_video(stale, first, 10.0)
            timeline_dir = os.path.join(folder, "timeline")
            os.makedirs(timeline_dir)
            timeline_path = os.path.join(timeline_dir, "timeline.json")
            import json
            with open(timeline_path, "w", encoding="utf-8") as handle:
                json.dump(stale.to_dict(), handle)
            state = ProjectState(
                project_id="video_2", project_root=folder, input_video=second,
                artifacts={"timeline": timeline_path},
            )
            self.window._project_media_source_mismatch = False

            restored = self.window._restore_saved_timeline_model(state)

            self.assertFalse(restored)
            self.assertTrue(self.window._project_media_source_mismatch)
            self.assertEqual(timeline_video_clips(self.window.timeline._timeline), [])

    def test_project_switch_reset_removes_previous_v1_source(self):
        stale = Timeline(duration=10.0)
        append_video(stale, "video_1.mp4", 10.0)
        self.window.timeline._timeline = stale

        self.window.project_controller.reset_project_runtime_state()

        self.assertEqual(timeline_video_clips(self.window.timeline._timeline), [])

    def test_empty_named_project_accepts_multiple_videos_and_persists_v1_order(self):
        with tempfile.TemporaryDirectory() as folder:
            first = os.path.join(folder, "one.mp4")
            second = os.path.join(folder, "two.mp4")
            Path(first).touch()
            Path(second).touch()
            service = ProjectService(folder)
            state = service.create_project()
            original_id = state.project_id
            self.window.project_service = service
            self.window.project_bridge = GUIProjectBridge(service)
            self.window.current_project_state = state
            self.window.timeline._init_default_tracks()
            self.window.timeline._probe_video_duration = lambda path: 3.0 if path == first else 5.0
            self.window.ensure_media_backend_ready = lambda: None
            self.window.media_player.setSource = lambda _source: None
            self.window.refresh_video_dimensions = lambda _path: None
            self.window.schedule_timeline_visual_refresh = lambda **_kwargs: None

            with patch(
                "features.multi_video_timeline.QFileDialog.getOpenFileNames",
                return_value=([first, second], "Video Files"),
            ):
                self.window.add_videos_to_timeline()

            clips = timeline_video_clips(self.window.timeline._timeline)
            self.assertEqual([clip.source for clip in clips], [os.path.abspath(first), os.path.abspath(second)])
            self.assertAlmostEqual(self.window.timeline._timeline.duration, 8.0)
            self.assertEqual(state.input_video, os.path.abspath(first))
            self.assertEqual(state.project_id, original_id)
            self.assertEqual(state.display_name, "VIUSTUDIO10000")
            reopened = service.load_project(service.project_file(state.project_root))
            self.assertEqual(reopened.project_id, original_id)
            self.assertTrue(os.path.isfile(reopened.artifacts["timeline"]))

    def test_mismatched_artifacts_are_detached_without_deleting_files(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "video_2.mp4")
            transcript = os.path.join(folder, "transcript.json")
            Path(source).touch()
            Path(transcript).write_text("[]", encoding="utf-8")
            state = ProjectState(
                project_id="video_2", project_root=folder, input_video=source,
                artifacts={"transcript_segments": transcript},
                settings={"timeline_video_clips": [{"source": "video_1.mp4"}]},
            )

            self.window._detach_mismatched_media_artifacts(state)

            self.assertTrue(os.path.exists(transcript))
            self.assertNotIn("transcript_segments", state.artifacts)
            recovery = state.artifacts.get("detached_media_recovery", "")
            self.assertTrue(os.path.isfile(recovery))


if __name__ == "__main__":
    unittest.main()

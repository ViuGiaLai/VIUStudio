import os
import sys
import tempfile
import unittest
import wave
from array import array
from types import SimpleNamespace

from app.layers.base import LayerType
from app.layers.blur import BlurLayer
from app.layers.mask import MaskLayer
from app.layers.text import TextLayer
from app.layers.timeline import Timeline, Track
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI_DIR = os.path.join(ROOT, "ui")
if UI_DIR not in sys.path:
    sys.path.insert(0, UI_DIR)

from controllers.preview_controller import PreviewController
from app.video_processor import _build_mask_filter_chain
from app.workflows.export_workflow import ExportWorkflow


class PreviewRenderConsistencyTests(unittest.TestCase):
    def test_export_audio_mix_cache_is_scoped_by_current_slider_values(self):
        class Slider:
            def __init__(self, value):
                self._value = value

            def value(self):
                return self._value

            def setValue(self, value):
                self._value = value

        def write_mono_wav(path, sample_value):
            samples = array("h", [sample_value] * 16000)
            with wave.open(path, "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(16000)
                handle.writeframes(samples.tobytes())

        with tempfile.TemporaryDirectory() as temp_dir:
            original = os.path.join(temp_dir, "original.wav")
            voice = os.path.join(temp_dir, "voice.wav")
            write_mono_wav(original, 10000)
            write_mono_wav(voice, 0)
            mix_dir = os.path.join(temp_dir, "project", "audio_mix")
            gui = SimpleNamespace(
                workspace_root=temp_dir,
                audio_a1_volume_slider=Slider(50),
                audio_a2_volume_slider=Slider(100),
                last_voice_vi_path=voice,
                _resolve_preview_background_audio_path=lambda: original,
                get_project_temp_dir=lambda _name: mix_dir,
                _percent_to_db=lambda percent: -60.0 if percent <= 0 else 20.0 * __import__("math").log10(percent / 100.0),
            )
            controller = PreviewController(gui)
            mix_50 = controller._regenerate_mixed_audio_with_current_volumes()
            gui.audio_a1_volume_slider.setValue(25)
            mix_25 = controller._regenerate_mixed_audio_with_current_volumes()

            self.assertTrue(os.path.isfile(mix_50))
            self.assertTrue(os.path.isfile(mix_25))
            self.assertNotEqual(mix_50, mix_25)
            self.assertTrue(os.path.commonpath([mix_dir, mix_25]).startswith(mix_dir))
            with wave.open(mix_50, "rb") as first, wave.open(mix_25, "rb") as second:
                first_peak = max(abs(value) for value in array("h", first.readframes(first.getnframes())))
                second_peak = max(abs(value) for value in array("h", second.readframes(second.getnframes())))
            self.assertAlmostEqual(second_peak / first_peak, 0.5, delta=0.03)

    def test_live_timeline_is_single_source_for_visual_layers(self):
        timeline = Timeline()
        mask_track = Track(name="M1", type=LayerType.MASK, visible=True)
        mask_track.layers.append(MaskLayer(start=2.0, end=4.0, visible=True))
        text_track = Track(name="T1 Text", type=LayerType.TEXT, visible=False)
        text_track.layers.append(TextLayer(text="must stay hidden", start=0.0, end=5.0))
        blur_track = Track(name="B1", type=LayerType.BLUR, visible=True)
        blur_track.layers.append(BlurLayer(start=1.0, end=3.0, visible=True))
        timeline.tracks.extend([mask_track, text_track, blur_track])

        gui = SimpleNamespace(timeline=SimpleNamespace(_timeline=timeline))
        controller = PreviewController(gui)
        masks, blurs, logos, texts = controller._extract_render_layers()

        self.assertEqual(len(masks), 1, "M1 must not be duplicated by a second preview-state source")
        self.assertEqual((masks[0]["start"], masks[0]["end"]), (2.0, 4.0))
        self.assertEqual(len(blurs), 1)
        self.assertEqual(logos, [])
        self.assertEqual(texts, [], "Hidden tracks must match export visibility")

    def test_fast_preview_rebases_and_clips_timed_layers(self):
        layers = [
            {"name": "before", "start": 1.0, "end": 4.0},
            {"name": "cross-start", "start": 8.0, "end": 12.0},
            {"name": "inside", "start": 11.0, "end": 13.0},
            {"name": "after", "start": 16.0, "end": 18.0},
            {"name": "always", "start": 0.0, "end": 0.0},
        ]
        result = PreviewController._rebase_timed_layers(layers, 10.0, 5.0)

        self.assertEqual([item["name"] for item in result], ["cross-start", "inside", "always"])
        self.assertEqual((result[0]["start"], result[0]["end"]), (0.0, 2.0))
        self.assertEqual((result[1]["start"], result[1]["end"]), (1.0, 3.0))
        self.assertEqual((result[2]["start"], result[2]["end"]), (0.0, 0.0))

    def test_preview_cache_changes_when_blur_or_text_changes(self):
        gui = SimpleNamespace(
            get_output_quality_key=lambda: "source",
            get_output_ratio_key=lambda: "source",
            get_output_scale_mode_key=lambda: "fit",
            get_output_fill_focus=lambda: (0.5, 0.5),
            get_output_fps_key=lambda: "source",
            get_video_filter_state=lambda: {},
        )
        controller = PreviewController(gui)
        with tempfile.TemporaryDirectory() as temp_dir:
            video = os.path.join(temp_dir, "video.mp4")
            subtitle = os.path.join(temp_dir, "subtitle.srt")
            with open(video, "wb") as handle:
                handle.write(b"video")
            with open(subtitle, "w", encoding="utf-8") as handle:
                handle.write("1\n00:00:00,000 --> 00:00:01,000\nHello\n")
            common = dict(
                video_path=video, audio_path="", mode="subtitle", srt_path=subtitle,
                subtitle_style={}, mask_regions=[], logo_layers=[],
            )
            first = controller._build_styled_preview_signature(
                **common, blur_regions=[{"blur_strength": 10}], text_layers=[{"text": "A"}]
            )
            changed_blur = controller._build_styled_preview_signature(
                **common, blur_regions=[{"blur_strength": 20}], text_layers=[{"text": "A"}]
            )
            changed_text = controller._build_styled_preview_signature(
                **common, blur_regions=[{"blur_strength": 10}], text_layers=[{"text": "B"}]
            )
        self.assertNotEqual(first, changed_blur)
        self.assertNotEqual(first, changed_text)

    def test_mask_opacity_is_preserved_in_ffmpeg_filter(self):
        chain = _build_mask_filter_chain(
            [{"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2,
              "mode": "solid", "color": "#123456", "opacity": 0.25}],
            1920, 1080,
        )
        self.assertIn("0x123456@0.250", chain)
        self.assertIn("format=rgba", chain)

    def test_original_export_renders_active_filters_instead_of_copying_source(self):
        class FakeEngine:
            def __init__(self):
                self.render_calls = []

            def get_video_dimensions(self, _path):
                return 320, 180

            def embed_ass_subtitles(self, video_path, ass_path, output_path, **kwargs):
                self.render_calls.append((video_path, ass_path, dict(kwargs)))
                with open(output_path, "wb") as handle:
                    handle.write(b"rendered")
                return True

        with tempfile.TemporaryDirectory() as temp_dir:
            source = os.path.join(temp_dir, "source.mp4")
            output = os.path.join(temp_dir, "output.mp4")
            with open(source, "wb") as handle:
                handle.write(b"source")
            workflow = ExportWorkflow(temp_dir)
            fake = FakeEngine()
            workflow.engine_runtime = fake
            result = workflow.run(
                video_path=source, output_path=output, mode="original",
                video_filter_state={"active": True, "brightness": 0.1},
                project_temp_dir=temp_dir,
            )
        self.assertEqual(result, output)
        self.assertEqual(len(fake.render_calls), 1)
        self.assertTrue(fake.render_calls[0][2]["video_filter_state"]["active"])

    def test_subtitle_overlay_item_font_size_and_box_height_proportional(self):
        from PySide6.QtWidgets import QApplication
        from widgets.subtitle_overlay import SubtitleOverlayItem
        from PySide6.QtGui import QPainter, QImage

        app = QApplication.instance() or QApplication([])
        item = SubtitleOverlayItem()
        # Verify set_style updates font_size correctly
        item.set_style(font_size=18, background_box=True, background_padding=2, background_radius=0)
        self.assertEqual(item.font_size, 18, "font_size must be updated when set_style is called")

        # Set single-line text
        item.set_text("Một suất phi lê gà tăng thêm 1 tệ.")
        # Height must be proportional to font (e.g. ~24-34px), NOT the old hardcoded 96px!
        self.assertLess(item.H, 50, f"Single-line overlay height {item.H} must not be inflated to 96px")
        self.assertGreaterEqual(item.H, 18)

        # Paint onto image and ensure no crash
        img = QImage(360, 200, QImage.Format_ARGB32_Premultiplied)
        img.fill(0)
        painter = QPainter(img)
        item.paint(painter, None, None)
        painter.end()

    def test_video_view_subtitle_render_dimensions_scaling(self):
        from PySide6.QtWidgets import QApplication
        from widgets.video_view import VideoView

        app = QApplication.instance() or QApplication([])
        view = VideoView()
        view.resize(360, 200)
        # Set 1080p source video dimensions
        view.set_subtitle_render_dimensions(1920, 1080)
        self.assertEqual(view.subtitle_render_width, 1920)
        self.assertEqual(view.subtitle_render_height, 1080)

        # Reposition subtitle and verify scaled coordinates
        view.reposition_subtitle()
        canvas_rect = view.get_preview_canvas_rect()
    def test_subtitle_overlay_item_capcut_gizmo_and_handles(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QPainter, QImage
        from widgets.subtitle_overlay import SubtitleOverlayItem

        app = QApplication.instance() or QApplication([])
        item = SubtitleOverlayItem()
        item.set_style(font_size=24, background_box=True)
        item.set_text("Test Subtitle Line")
        item.set_editable(True)
        item.set_selected(True)

        content_rect = item._get_content_rect()
        self.assertGreater(content_rect.width(), 40)
        self.assertGreater(content_rect.height(), 16)

        handles = item._handle_rects(content_rect)
        self.assertIn("top_left", handles)
        self.assertIn("top_right", handles)
        self.assertIn("bottom_left", handles)
        self.assertIn("bottom_right", handles)

        # Hit test corner handle
        tl_point = handles["top_left"].center()
        self.assertEqual(item._hit_test(tl_point), "top_left")

        # Hit test center
        center_point = content_rect.center()
        self.assertEqual(item._hit_test(center_point), "move")

        # Hit test outside
        outside_point = QPointF(content_rect.left() - 50, content_rect.top() - 50)
        self.assertEqual(item._hit_test(outside_point), "")

        # Paint with gizmo enabled and verify no crash
        img = QImage(400, 200, QImage.Format_ARGB32_Premultiplied)
        img.fill(0)
        painter = QPainter(img)
        item.paint(painter, None, None)
        painter.end()

    def test_subtitle_overlay_item_drag_and_scale_signals(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QPointF
        from widgets.subtitle_overlay import SubtitleOverlayItem

        app = QApplication.instance() or QApplication([])
        item = SubtitleOverlayItem()
        item.set_style(font_size=20, base_font_size=60)
        item.set_text("Drag and Scale Subtitle")
        item.set_editable(True)
        item.set_selected(True)

        events_received = []
        item.positionDragFinished.connect(lambda x, y: events_received.append(("pos", x, y)))
        item.fontSizeChanged.connect(lambda size: events_received.append(("size", size)))

        # Simulate move drag release
        item._drag_mode = "move"
        item.custom_x_percent = 40
        item.custom_y_percent = 70
        from PySide6.QtWidgets import QGraphicsSceneMouseEvent
        from PySide6.QtCore import QEvent
        release_event = QGraphicsSceneMouseEvent(QEvent.GraphicsSceneMouseRelease)
        release_event.setButton(item.acceptedMouseButtons())
        item.mouseReleaseEvent(release_event)

        self.assertEqual(len(events_received), 1)
        self.assertEqual(events_received[0], ("pos", 40, 70))

        # Simulate scale resize release
        events_received.clear()
        item._drag_mode = "bottom_right"
        item.base_font_size = 72
        item.mouseReleaseEvent(release_event)

        self.assertEqual(len(events_received), 1)
        self.assertEqual(events_received[0], ("size", 72))

    def test_preview_manipulation_updates_export_ass_style_and_pos(self):
        from PySide6.QtWidgets import QApplication, QSpinBox, QComboBox
        from features.filter_subtitle_style import FilterSubtitleStyleMixin
        from app.video_processor import srt_to_ass

        app = QApplication.instance() or QApplication([])

        class DummyWindow(FilterSubtitleStyleMixin):
            def __init__(self):
                self.subtitle_custom_x_spin = QSpinBox()
                self.subtitle_custom_x_spin.setRange(0, 100)
                self.subtitle_custom_x_spin.setValue(50)
                self.subtitle_custom_y_spin = QSpinBox()
                self.subtitle_custom_y_spin.setRange(0, 100)
                self.subtitle_custom_y_spin.setValue(86)
                self.subtitle_font_size_spin = QSpinBox()
                self.subtitle_font_size_spin.setRange(8, 200)
                self.subtitle_font_size_spin.setValue(24)
                self.subtitle_position_mode_combo = QComboBox()
                self.subtitle_position_mode_combo.addItem("Anchor", "anchor")
                self.subtitle_position_mode_combo.addItem("Custom", "custom")
                self.subtitle_position_mode_combo.setCurrentIndex(0)
                self.style_updated = False
                self.state_persisted = False

            def _preview_is_playing(self):
                return False

            def update_subtitle_preview_style(self):
                self.style_updated = True

            def persist_project_state(self):
                self.state_persisted = True

            def schedule_timeline_project_persist(self):
                self.state_persisted = True

            def on_subtitle_style_control_edited(self):
                self.update_subtitle_preview_style()
                self.persist_project_state()

        window = DummyWindow()

        # Simulate user dragging subtitle to (35%, 65%)
        window.on_subtitle_position_dragged(35, 65)
        self.assertEqual(window.subtitle_position_mode_combo.currentData(), "custom")
        self.assertEqual(window.subtitle_custom_x_spin.value(), 35)
        self.assertEqual(window.subtitle_custom_y_spin.value(), 65)
        self.assertTrue(window.style_updated)

        # Simulate user scaling font to 52px
        window.on_subtitle_font_size_scaled(52)
        self.assertEqual(window.subtitle_font_size_spin.value(), 52)
        self.assertTrue(window.state_persisted)

        # Now test srt_to_ass generation with these exact dragged/scaled parameters
        with tempfile.TemporaryDirectory() as temp_dir:
            srt_file = os.path.join(temp_dir, "test.srt")
            with open(srt_file, "w", encoding="utf-8") as f:
                f.write("1\n00:00:01,000 --> 00:00:03,000\nCapCut Subtitle Drag & Scale Test\n\n")

            ass_file = srt_to_ass(
                srt_path=srt_file,
                video_width=1920,
                video_height=1080,
                font_size=window.subtitle_font_size_spin.value(),
                custom_position_enabled=True,
                custom_position_x=float(window.subtitle_custom_x_spin.value()),
                custom_position_y=float(window.subtitle_custom_y_spin.value()),
            )

            with open(ass_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Verify font size in Style header
            self.assertIn(",52,", content, "Exported ASS Style line must contain the scaled font_size 52")
            # Verify coordinates in Dialogue line: 1920 * 0.35 = 672, 1080 * 0.65 = 702
            self.assertIn(r"\an5\pos(672,702)", content, r"Exported ASS Dialogue must contain the exact dragged position \an5\pos(672,702)")


if __name__ == "__main__":
    unittest.main()

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


if __name__ == "__main__":
    unittest.main()

import json
import os
import sys
import tempfile
import unittest

APP_DIR = os.path.abspath(os.path.join(r"d:\all_my_project\CapCap", "app"))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from app.layers.base import LayerType
from app.layers.text import TextLayer
from app.layers.mask import MaskLayer
from app.layers.blur import BlurLayer
from app.layers.timeline import Timeline, Track
from app.workflows.export_workflow import ExportWorkflow
from app.core.models.segment import Segment
from app.services.segment_service import SegmentService
from app.services.project_service import ProjectService
from core.state.project_state import ProjectState


class DeepSynchronizationTests(unittest.TestCase):
    def test_zero_volume_is_not_signature_equivalent_to_default_volume(self):
        service = ProjectService(str(ROOT) if "ROOT" in globals() else os.getcwd())
        segments = [{"start": 0.0, "end": 1.0, "text": "Hello"}]
        muted = service.build_voice_signature(segments, original_volume=0, dub_volume=0)
        defaults = service.build_voice_signature(segments, original_volume=50, dub_volume=100)
        self.assertNotEqual(muted, defaults)

    def test_hidden_track_is_skipped_during_export(self):
        """When track.visible is False, export must ignore its layers."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state = ProjectState(project_id="p_sync", project_root=temp_dir, input_video="video.mp4")
            timeline = Timeline()

            # Create a hidden text track
            track_text = Track(name="T1 Text", type=LayerType.TEXT, visible=False)
            layer_text = TextLayer(text="Hidden Text", start=0.0, end=5.0)
            track_text.layers.append(layer_text)
            timeline.tracks.append(track_text)

            # Create a hidden mask track
            track_mask = Track(name="M1", type=LayerType.MASK, visible=False)
            layer_mask = MaskLayer(start=0.0, end=5.0)
            track_mask.layers.append(layer_mask)
            timeline.tracks.append(track_mask)

            # Create a visible blur track
            track_blur = Track(name="B1", type=LayerType.BLUR, visible=True)
            layer_blur = BlurLayer(start=0.0, end=5.0, visible=True)
            track_blur.layers.append(layer_blur)
            timeline.tracks.append(track_blur)

            timeline_path = os.path.join(temp_dir, "timeline", "timeline.json")
            os.makedirs(os.path.dirname(timeline_path), exist_ok=True)
            with open(timeline_path, "w", encoding="utf-8") as handle:
                json.dump(timeline.to_dict(), handle)
            state.artifacts["timeline"] = timeline_path

            workflow = ExportWorkflow(temp_dir)
            mask_regions, logo_layers, text_layers, blur_regions = workflow._extract_overlay_layers(state)

            # Hidden text and mask tracks must not be extracted
            self.assertEqual(len(text_layers), 0, "Hidden text track layers should not be exported")
            self.assertEqual(len(mask_regions), 0, "Hidden mask track layers should not be exported")
            # Visible blur track must be extracted
            self.assertEqual(len(blur_regions), 1, "Visible blur track layer must be exported")

    def test_preview_track_visibility_controls_fallback_export(self):
        """When timeline has no mask/blur, fallback to settings must honor preview_track_visibility."""
        with tempfile.TemporaryDirectory() as temp_dir:
            state = ProjectState(project_id="p_fb", project_root=temp_dir, input_video="video.mp4")
            state.settings["mask_state"] = {"enabled": True, "regions": [{"x": 0.2, "y": 0.3, "width": 0.4, "height": 0.2}]}
            state.settings["blur_state"] = {"enabled": True, "regions": [{"x": 0.1, "y": 0.1, "width": 0.5, "height": 0.3}]}
            # Explicitly hide M1 and B1 in preview_track_visibility
            state.settings["preview_track_visibility"] = {"M1": False, "B1": False}

            workflow = ExportWorkflow(temp_dir)
            mask_regions, _, _, blur_regions = workflow._extract_overlay_layers(state)
            self.assertEqual(len(mask_regions), 0, "Mask fallback must be skipped when M1 is hidden")
            self.assertEqual(len(blur_regions), 0, "Blur fallback must be skipped when B1 is hidden")

            # Enable M1 and verify it gets extracted
            state.settings["preview_track_visibility"] = {"M1": True, "B1": False}
            mask_regions, _, _, blur_regions = workflow._extract_overlay_layers(state)
            self.assertEqual(len(mask_regions), 1, "Mask fallback must be extracted when M1 is visible")
            self.assertEqual(len(blur_regions), 0, "Blur fallback must still be skipped")

    def test_voice_speed_preservation_in_segment_service(self):
        """SegmentService.apply_translations must preserve per-segment voice_speed from base models."""
        service = SegmentService()
        base_models = [
            Segment(id=1, start=0.0, end=3.0, original_text="One", metadata={"voice_speed": 1.25}),
            Segment(id=2, start=3.0, end=6.0, original_text="Two", metadata={"voice_speed": 0.85}),
        ]
        translated_dicts = [
            {"id": 1, "start": 0.0, "end": 3.0, "text": "Một"},
            {"id": 2, "start": 3.0, "end": 6.0, "text": "Hai"},
        ]
        translated_models = service.apply_translations(base_models, translated_dicts)
        self.assertEqual(len(translated_models), 2)
        self.assertAlmostEqual(translated_models[0].voice_speed, 1.25, places=2)
        self.assertAlmostEqual(translated_models[1].voice_speed, 0.85, places=2)

    def test_segment_to_original_subtitle_dict_includes_voice_speed(self):
        """Segment.to_original_subtitle_dict must serialize voice_speed when present."""
        seg = Segment(id=1, start=1.0, end=4.0, original_text="Hello", metadata={"voice_speed": 1.5})
        d = seg.to_original_subtitle_dict()
        self.assertIn("voice_speed", d)
        self.assertAlmostEqual(d["voice_speed"], 1.5, places=2)

    def test_segment_to_subtitle_dict_includes_voice_speed(self):
        """Segment.to_subtitle_dict must serialize voice_speed when present."""
        seg = Segment(id=1, start=1.0, end=4.0, final_text="Xin chào", metadata={"voice_speed": 0.75})
        d = seg.to_subtitle_dict()
        self.assertIn("voice_speed", d)
        self.assertAlmostEqual(d["voice_speed"], 0.75, places=2)


if __name__ == "__main__":
    unittest.main()

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path[:0] = [os.path.join(ROOT, "ui"), os.path.join(ROOT, "app"), ROOT]
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from app.layers.base import LayerType
from app.layers.image import ImageLayer
from app.layers.blur import BlurLayer
from app.layers.text import TextLayer
from app.layers.timeline import Timeline, Track
from app.workflows.export_workflow import ExportWorkflow
from core.state.project_state import ProjectState


class MockPreviewController:
    """Standalone test harness replicating PreviewController clip normalization."""

    def __init__(self, canonical_path=""):
        self.canonical_path = canonical_path
        self.gui = MagicMock()
        self.gui.resolve_canonical_video_path.return_value = canonical_path

    from controllers.preview_controller import PreviewController
    _normalize_export_timeline_clips = PreviewController._normalize_export_timeline_clips


class TestAutoRecapExportFlow(unittest.TestCase):
    def test_normalize_clips_repoints_canonical_source_to_recap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_video = os.path.join(tmpdir, "original.mp4")
            recap_video = os.path.join(tmpdir, "original_recap.mp4")
            with open(orig_video, "wb") as f:
                f.write(b"orig")
            with open(recap_video, "wb") as f:
                f.write(b"recap")

            controller = MockPreviewController(canonical_path=orig_video)
            raw_clips = [
                {
                    "source": orig_video,
                    "source_start": 0.0,
                    "source_duration": 4.0,
                    "start": 0.0,
                    "end": 4.0,
                    "speed": 1.0,
                },
                {
                    "source": orig_video,
                    "source_start": 4.0,
                    "source_duration": 6.0,
                    "start": 4.0,
                    "end": 10.0,
                    "speed": 1.0,
                },
            ]

            normalized = controller._normalize_export_timeline_clips(
                raw_clips,
                base_video_path=recap_video,
                is_recap_active=True,
            )

            # Contiguous unmodified sequence should be collapsed into a single clip pointing to recap_video
            self.assertEqual(len(normalized), 1)
            self.assertEqual(os.path.normcase(normalized[0]["source"]), os.path.normcase(recap_video))
            self.assertEqual(normalized[0]["source_start"], 0.0)
            self.assertEqual(normalized[0]["source_duration"], 10.0)

    def test_normalize_clips_preserves_user_edits_when_not_contiguous(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recap_video = os.path.join(tmpdir, "original_recap.mp4")
            with open(recap_video, "wb") as f:
                f.write(b"recap")

            controller = MockPreviewController(canonical_path=recap_video)
            # Gap between clip 1 (ends at 4.0) and clip 2 (starts at 7.0 - user deleted a shot)
            edited_clips = [
                {
                    "source": recap_video,
                    "source_start": 0.0,
                    "source_duration": 4.0,
                    "start": 0.0,
                    "end": 4.0,
                    "speed": 1.0,
                },
                {
                    "source": recap_video,
                    "source_start": 7.0,
                    "source_duration": 5.0,
                    "start": 7.0,
                    "end": 12.0,
                    "speed": 1.0,
                },
            ]

            normalized = controller._normalize_export_timeline_clips(
                edited_clips,
                base_video_path=recap_video,
                is_recap_active=True,
            )

            # Should NOT collapse because the user deliberately created a cut/gap!
            self.assertEqual(len(normalized), 2)
            self.assertEqual(normalized[0]["source_duration"], 4.0)
            self.assertEqual(normalized[1]["source_start"], 7.0)

    def test_export_workflow_extracts_and_burns_overlays_on_recap_video(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            recap_video = os.path.join(tmpdir, "video_recap.mp4")
            with open(recap_video, "wb") as f:
                f.write(b"video_content")

            logo_img = os.path.join(tmpdir, "logo.png")
            with open(logo_img, "wb") as f:
                f.write(b"fake_png_bytes")

            state = ProjectState(project_id="p1", project_root=tmpdir, input_video=recap_video)
            timeline = Timeline()

            # Add Logo on track L1
            track_l1 = Track(name="L1 Logo", type=LayerType.IMAGE)
            logo = ImageLayer(name="Watermark", source=logo_img, start=0.0, end=10.0)
            logo.transform.x = 0.05
            logo.transform.y = 0.05
            track_l1.layers.append(logo)
            timeline.tracks.append(track_l1)

            # Add Blur on track B1
            track_b1 = Track(name="B1 Blur", type=LayerType.BLUR)
            blur = BlurLayer(name="Top Blur", start=0.0, end=10.0)
            blur.position_x = 0.1
            blur.position_y = 0.1
            blur.width = 0.3
            blur.height = 0.2
            track_b1.layers.append(blur)
            timeline.tracks.append(track_b1)

            # Save timeline.json
            timeline_path = os.path.join(tmpdir, "timeline", "timeline.json")
            os.makedirs(os.path.dirname(timeline_path), exist_ok=True)
            with open(timeline_path, "w", encoding="utf-8") as f:
                json.dump(timeline.to_dict(), f)
            state.artifacts["timeline"] = timeline_path

            workflow = ExportWorkflow(tmpdir)

            # 1. State must detect visible overlay layers
            self.assertTrue(workflow._has_visible_overlay_layers(state))

            # 2. Extract overlay layers
            mask_regions, logo_layers, text_layers, blur_regions = workflow._extract_overlay_layers(state)
            self.assertEqual(len(logo_layers), 1)
            self.assertEqual(len(blur_regions), 1)
            self.assertEqual(logo_layers[0]["source"], logo_img)


if __name__ == "__main__":
    unittest.main()

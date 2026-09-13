import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
# UI modules import ``utils`` from ui/, while app services are also exposed
# as top-level modules. Keep UI first so test discovery cannot bind the wrong
# package when another integration test imports the main window afterwards.
sys.path[:0] = [str(ROOT / "ui"), str(ROOT), str(ROOT / "app")]

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QWidget

from features.timeline_selection import TimelineSelectionMixin
from widgets.video_view import VideoView
from widgets.mpv_video_view import (
    _BlurRegionOverlayWindow,
    _LogoRegionOverlayWindow,
    _MaskRegionOverlayWindow,
    _SubtitleOverlayWidget,
    _TextLayerOverlayWindow,
    _preview_host_is_available,
)
from views.preview_panel import OcrRegionOverlay, OcrTranslatorOverlay
from app.video_processor import _build_blur_filter_chain


APP = QApplication.instance() or QApplication([])


class _SelectionHarness(TimelineSelectionMixin):
    def _preview_is_playing(self):
        return False

    def refresh_timed_layer_preview(self):
        return None


class _OverlayPreviewHost(QWidget):
    """Small preview surface for native-overlay visibility tests."""

    def get_preview_canvas_rect(self):
        return QRectF(0, 0, self.width(), self.height())

    def get_video_content_rect(self):
        return QRectF(0, 0, self.width(), self.height())


class BlurPreviewTests(unittest.TestCase):
    def test_export_blur_uses_radius_opacity_and_pixelate_controls(self):
        strong = _build_blur_filter_chain([{
            "x": 0.1, "y": 0.2, "width": 0.5, "height": 0.2,
            "blur_strength": 30, "blur_opacity": 0.4,
        }], 1920, 1080)
        mosaic = _build_blur_filter_chain([{
            "x": 0.1, "y": 0.2, "width": 0.5, "height": 0.2,
            "pixelate": True, "pixelate_size": 24,
        }], 1920, 1080)

        # Export uses the current high-quality Gaussian blur path. Strength
        # maps directly to sigma while opacity remains an independent alpha.
        self.assertIn("gblur=sigma=30.0:steps=3", strong)
        self.assertIn("colorchannelmixer=aa=0.400", strong)
        self.assertIn("flags=neighbor", mosaic)

    def test_selected_blur_is_not_suppressed_while_editing(self):
        harness = _SelectionHarness()
        harness._deferred_effect_edit_type = ""
        harness._deferred_effect_edit_layer_id = ""
        track = SimpleNamespace(name="B1")
        layer = SimpleNamespace(id="blur-1", type=SimpleNamespace(value="blur"))

        harness._set_deferred_effect_edit_target(track, layer)

        self.assertEqual(harness._deferred_effect_layer_id_for("blur"), "")


    def test_qt_fallback_renders_blur_without_mpv(self):
        view = VideoView()
        view.resize(640, 360)
        view.set_video_dimensions(1280, 720)
        view._last_video_image = QImage(1280, 720, QImage.Format_RGB32)
        view._last_video_image.fill(QColor("red"))
        region = {
            "x": 0.15,
            "y": 0.78,
            "width": 0.70,
            "height": 0.18,
            "blur_strength": 20,
        }

        view.set_blur_regions_normalized([region])
        view.set_blur_effect_regions([region])
        APP.processEvents()

        self.assertTrue(view.has_blur_region())
        self.assertEqual(view.get_blur_region_normalized()["y"], 0.78)
        self.assertEqual(len(view._blur_preview_items), 1)

    def test_every_native_overlay_is_hidden_when_preview_host_is_minimized(self):
        host = QWidget()
        preview = _OverlayPreviewHost(host)
        host.resize(640, 480)
        preview.resize(320, 180)
        host.show()
        preview.show()
        APP.processEvents()
        self.assertTrue(_preview_host_is_available(preview))

        subtitle = _SubtitleOverlayWidget()
        subtitle.attach_to_view(preview)
        subtitle.show()
        overlays = [subtitle]

        for overlay_type in (
            _BlurRegionOverlayWindow,
            _LogoRegionOverlayWindow,
            _MaskRegionOverlayWindow,
        ):
            overlay = overlay_type()
            overlay.attach_to_view(preview)
            overlay.add_region()
            overlay.set_editable(True)
            overlay.sync_to_view()
            overlays.append(overlay)

        text = _TextLayerOverlayWindow()
        text.attach_to_view(preview)
        text.set_items([{"id": "text-1", "text": "Layer", "x": 0.5, "y": 0.5}], "text-1")
        overlays.append(text)

        ocr_region = OcrRegionOverlay()
        ocr_region.attach_to_view(preview)
        ocr_region.sync_to_view()
        overlays.append(ocr_region)
        ocr_translator = OcrTranslatorOverlay()
        ocr_translator.attach_to_view(preview)
        ocr_translator.sync_to_view()
        overlays.append(ocr_translator)

        host.showMinimized()
        APP.processEvents()
        for overlay in overlays:
            if hasattr(overlay, "sync_to_view"):
                overlay.sync_to_view()

        self.assertFalse(_preview_host_is_available(preview))
        self.assertTrue(all(not overlay.isVisible() for overlay in overlays))

        for overlay in overlays:
            overlay.deleteLater()
        host.close()


if __name__ == "__main__":
    unittest.main()

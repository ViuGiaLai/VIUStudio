import os
from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import QFrame, QGraphicsBlurEffect, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView

from .mpv_video_view import (
    _BlurRegionOverlayWindow,
    _MaskRegionOverlayWindow,
)
from .subtitle_overlay import SubtitleOverlayItem


class VideoView(QGraphicsView):
    """Hosts video, logo, and subtitle overlay in one scene."""

    framingChanged = Signal(float, float)
    blurRegionChanged = Signal()
    blurEditFinished = Signal()
    subtitlePositionChanged = Signal(int, int)  # x_percent, y_percent
    subtitleDragStarted = Signal()
    subtitleFontSizeChanged = Signal(int)  # new_base_font_size
    subtitleClicked = Signal()
    logoMoved = Signal(float, float, float, float)  # x, y, w, h
    logoDeleted = Signal()
    logoEditFinished = Signal()
    maskRegionChanged = Signal()
    maskMoved = Signal(float, float, float, float)  # x, y, w, h
    maskDeleted = Signal()
    maskEditFinished = Signal()
    textLayerSelected = Signal(str)
    textLayerMoved = Signal(str, float, float)
    scaleModeToggleRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("background-color: #050811; border-radius: 8px;")
        self.setRenderHint(QPainter.Antialiasing)

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self.video_item = QGraphicsVideoItem()
        self._scene.addItem(self.video_item)
        self._last_video_image = QImage()
        self._blur_effect_regions: list[dict] = []
        self._blur_preview_items: list[QGraphicsPixmapItem] = []

        self.blur_overlay = _BlurRegionOverlayWindow(
            on_region_changed=self._on_blur_overlay_changed,
            on_edit_finished=self.blurEditFinished.emit,
        )
        video_sink = self.video_item.videoSink()
        if video_sink is not None:
            video_sink.videoFrameChanged.connect(self._on_video_frame_changed)
        self.mask_overlay = _MaskRegionOverlayWindow(
            on_region_changed=self.maskRegionChanged.emit,
            on_edit_finished=self.maskEditFinished.emit,
        )
        self.mask_overlay.maskDeleted.connect(self.maskDeleted.emit)
        self.text_overlay = None

        self.logo_item = QGraphicsPixmapItem()
        self.logo_item.setZValue(5)
        self._scene.addItem(self.logo_item)
        self.logo_item.hide()
        self._current_logos = []
        self._raw_logo_pixmap = None
        self._logo_opacity = 1.0
        self._logo_rotation = 0.0
        self._logo_visible = True

        self.subtitle_item = SubtitleOverlayItem()
        self.subtitle_item.attach_to_view(self)
        self.subtitle_item.setZValue(10)
        self._scene.addItem(self.subtitle_item)
        self.subtitle_item.hide()
        self.subtitle_item.positionDragStarted.connect(self.subtitleDragStarted.emit)
        self.subtitle_item.positionDragFinished.connect(self.subtitlePositionChanged.emit)
        self.subtitle_item.fontSizeChanged.connect(self.subtitleFontSizeChanged.emit)
        self.subtitle_item.subtitleClicked.connect(self.subtitleClicked.emit)
        self.video_source_width = 0
        self.video_source_height = 0
        self.subtitle_render_width = 0
        self.subtitle_render_height = 0
        self.preview_aspect_key = "source"
        self.preview_scale_mode = "fit"
        self.preview_fill_focus_x = 0.5
        self.preview_fill_focus_y = 0.5
        self._framing_drag_active = False
        self._framing_drag_start = QPointF()
        self._framing_drag_focus = (0.5, 0.5)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width, height = self.width(), self.height()
        self._scene.setSceneRect(0, 0, width, height)
        content_rect = self.get_video_content_rect()
        self.video_item.setPos(content_rect.topLeft())
        self.video_item.setSize(QSizeF(content_rect.width(), content_rect.height()))
        self.reposition_subtitle()
        self.reposition_logo()
        self._refresh_blur_preview_items()
        self.blur_overlay.sync_to_view()
        self.viewport().update()

    def set_video_dimensions(self, width: int, height: int):
        self.video_source_width = max(0, int(width or 0))
        self.video_source_height = max(0, int(height or 0))
        content_rect = self.get_video_content_rect()
        self.video_item.setPos(content_rect.topLeft())
        self.video_item.setSize(QSizeF(content_rect.width(), content_rect.height()))
        self.reposition_subtitle()
        self._refresh_blur_preview_items()

    def set_preview_aspect_ratio(self, aspect_key: str):
        self.preview_aspect_key = str(aspect_key or "source").strip().lower() or "source"
        content_rect = self.get_video_content_rect()
        self.video_item.setPos(content_rect.topLeft())
        self.video_item.setSize(QSizeF(content_rect.width(), content_rect.height()))
        self.reposition_subtitle()
        self._refresh_blur_preview_items()
        self.blur_overlay.sync_to_view()
        self.viewport().update()

    def set_preview_scale_mode(self, scale_mode: str):
        self.preview_scale_mode = str(scale_mode or "fit").strip().lower() or "fit"
        content_rect = self.get_video_content_rect()
        self.video_item.setPos(content_rect.topLeft())
        self.video_item.setSize(QSizeF(content_rect.width(), content_rect.height()))
        self.reposition_subtitle()
        self._refresh_blur_preview_items()
        self.blur_overlay.sync_to_view()
        self.viewport().update()

    def set_preview_fill_focus(self, focus_x: float, focus_y: float):
        self.preview_fill_focus_x = max(0.0, min(1.0, float(focus_x)))
        self.preview_fill_focus_y = max(0.0, min(1.0, float(focus_y)))
        content_rect = self.get_video_content_rect()
        self.video_item.setPos(content_rect.topLeft())
        self.video_item.setSize(QSizeF(content_rect.width(), content_rect.height()))
        self.reposition_subtitle()
        self._refresh_blur_preview_items()
        self.blur_overlay.sync_to_view()
        self.viewport().update()

    def reset_preview_fill_focus(self):
        self.set_preview_fill_focus(0.5, 0.5)

    def get_preview_fill_focus(self) -> tuple[float, float]:
        return (float(self.preview_fill_focus_x), float(self.preview_fill_focus_y))

    def set_blur_edit_enabled(self, enabled: bool):
        self.blur_overlay.attach_to_view(self)
        self.blur_overlay.set_editable(bool(enabled))

    def add_blur_region(self):
        self.blur_overlay.attach_to_view(self)
        self.blur_overlay.add_region()

    def set_blur_active_index(self, index: int):
        self.blur_overlay.set_active_index(index)

    def clear_blur_region(self):
        self.blur_overlay.clear_region()
        self.set_blur_effect_regions(None)
        self.blurRegionChanged.emit()

    def has_blur_region(self) -> bool:
        return self.blur_overlay.has_region()

    def get_blur_region_normalized(self) -> "dict | list[dict] | None":
        if not self.blur_overlay.has_region():
            return None
        regions = [
            {
                "x": round(float(rect.x()), 6),
                "y": round(float(rect.y()), 6),
                "width": round(float(rect.width()), 6),
                "height": round(float(rect.height()), 6),
            }
            for rect in self.blur_overlay._regions
        ]
        return regions[0] if len(regions) == 1 else regions

    def set_blur_regions_normalized(self, regions) -> None:
        self.blur_overlay.attach_to_view(self)
        self.blur_overlay.set_regions(regions)

    def set_blur_effect_regions(self, regions) -> None:
        raw = regions if isinstance(regions, list) else ([regions] if isinstance(regions, dict) else [])
        self._blur_effect_regions = [dict(region) for region in raw if isinstance(region, dict)]
        self._refresh_blur_preview_items()

    def _on_blur_overlay_changed(self):
        raw = self.get_blur_region_normalized()
        raw = raw if isinstance(raw, list) else ([raw] if raw else [])
        previous = list(self._blur_effect_regions)
        self._blur_effect_regions = []
        for index, region in enumerate(raw):
            merged = dict(previous[index]) if index < len(previous) else {}
            merged.update(region)
            self._blur_effect_regions.append(merged)
        self._refresh_blur_preview_items()
        self.blurRegionChanged.emit()

    def _on_video_frame_changed(self, frame):
        try:
            image = frame.toImage()
        except Exception:
            image = QImage()
        if image is not None and not image.isNull():
            self._last_video_image = image.copy()
            if self._blur_effect_regions:
                self._refresh_blur_preview_items()

    def _clear_blur_preview_items(self):
        for item in self._blur_preview_items:
            self._scene.removeItem(item)
        self._blur_preview_items = []

    def _refresh_blur_preview_items(self):
        self._clear_blur_preview_items()
        image = self._last_video_image
        if image.isNull() or not self._blur_effect_regions:
            return
        content = self.get_video_content_rect()
        if content.width() <= 0 or content.height() <= 0:
            return
        source_w, source_h = image.width(), image.height()
        for region in self._blur_effect_regions:
            try:
                x = max(0.0, min(1.0, float(region.get("x", 0.0))))
                y = max(0.0, min(1.0, float(region.get("y", 0.0))))
                width = max(0.0, min(1.0 - x, float(region.get("width", 0.0))))
                height = max(0.0, min(1.0 - y, float(region.get("height", 0.0))))
            except (TypeError, ValueError):
                continue
            crop_x = max(0, min(source_w - 1, round(x * source_w)))
            crop_y = max(0, min(source_h - 1, round(y * source_h)))
            crop_w = max(1, min(source_w - crop_x, round(width * source_w)))
            crop_h = max(1, min(source_h - crop_y, round(height * source_h)))
            crop = image.copy(crop_x, crop_y, crop_w, crop_h)
            target = QRectF(
                content.x() + x * content.width(),
                content.y() + y * content.height(),
                width * content.width(),
                height * content.height(),
            )
            if target.width() <= 0 or target.height() <= 0:
                continue
            pixelate = bool(region.get("pixelate", False))
            if pixelate:
                try:
                    pixel_size = max(2, int(region.get("pixelate_size", region.get("pixel_size", 12)) or 12))
                except (TypeError, ValueError):
                    pixel_size = 12
                crop = crop.scaled(
                    max(1, crop.width() // pixel_size), max(1, crop.height() // pixel_size),
                    Qt.IgnoreAspectRatio, Qt.FastTransformation,
                ).scaled(crop.width(), crop.height(), Qt.IgnoreAspectRatio, Qt.FastTransformation)
            pixmap = QPixmap.fromImage(crop).scaled(
                max(1, round(target.width())), max(1, round(target.height())),
                Qt.IgnoreAspectRatio, Qt.FastTransformation if pixelate else Qt.SmoothTransformation,
            )
            item = QGraphicsPixmapItem(pixmap)
            item.setZValue(4)
            item.setPos(target.topLeft())
            if not pixelate:
                try:
                    radius = max(1.0, float(region.get("blur_strength", 36.0) or 36.0) * 3.0)
                except (TypeError, ValueError):
                    radius = 72.0
                effect = QGraphicsBlurEffect()
                effect.setBlurRadius(min(radius, max(1.0, min(target.width(), target.height()) / 2.0)))
                item.setGraphicsEffect(effect)
            try:
                opacity_value = region.get("blur_opacity", region.get("opacity", 1.0))
                opacity = float(1.0 if opacity_value is None else opacity_value)
            except (TypeError, ValueError):
                opacity = 1.0
            item.setOpacity(max(0.0, min(1.0, opacity)))
            self._scene.addItem(item)
            self._blur_preview_items.append(item)

    def set_mask_region(self, *, x: float = 0.0, y: float = 0.0,
                        w: float = 0.0, h: float = 0.0, **kwargs) -> None:
        if hasattr(self, "mask_overlay") and self.mask_overlay is not None:
            self.mask_overlay.attach_to_view(self)
            self.mask_overlay.set_mask_rect(x, y, w, h)
            if kwargs.get("color") is not None:
                self.mask_overlay.set_fill_color(kwargs["color"])
            self.mask_overlay.set_editable(bool(kwargs.get("editable", True)))
            self.mask_overlay.sync_to_view()

    def set_mask_regions(self, regions=None, *, active_index=0, editable=True, **_kwargs):
        if hasattr(self, "mask_overlay") and self.mask_overlay is not None:
            self.mask_overlay.attach_to_view(self)
            self.mask_overlay.set_mask_regions(regions or [], active_index)
            self.mask_overlay.set_editable(bool(editable))
            self.mask_overlay.sync_to_view()

    def clear_mask_region(self):
        if hasattr(self, "mask_overlay") and self.mask_overlay is not None:
            self.mask_overlay.set_editable(False)
            self.mask_overlay.clear_region()

    def set_mask_edit_enabled(self, enabled: bool):
        if hasattr(self, "mask_overlay") and self.mask_overlay is not None:
            self.mask_overlay.attach_to_view(self)
            self.mask_overlay.set_editable(bool(enabled))

    def set_text_track_visible(self, visible: bool):
        if getattr(self, "text_overlay", None) is not None:
            self.text_overlay.set_suppressed(not bool(visible))

    def clear_text_layers(self):
        if getattr(self, "text_overlay", None) is not None:
            self.text_overlay.set_items([], "")

    def set_text_layers(self, layers, active_id=""):
        if getattr(self, "text_overlay", None) is None:
            try:
                from .mpv_video_view import _TextLayerOverlayWindow
                self.text_overlay = _TextLayerOverlayWindow()
                self.text_overlay.attach_to_view(self)
                self.text_overlay.layerSelected.connect(self.textLayerSelected.emit)
                self.text_overlay.layerMoved.connect(self.textLayerMoved.emit)
            except Exception:
                pass
        if getattr(self, "text_overlay", None) is not None:
            self.text_overlay.set_items(layers or [], active_id or "")
            self.text_overlay.sync_to_view()

    def set_subtitle_render_dimensions(self, width: int, height: int):
        self.subtitle_render_width = max(0, int(width or 0))
        self.subtitle_render_height = max(0, int(height or 0))
        self.reposition_subtitle()

    def set_subtitle_track_visible(self, visible: bool):
        if hasattr(self, "subtitle_item") and self.subtitle_item is not None:
            if visible and getattr(self.subtitle_item, "current_text", ""):
                self.subtitle_item.show()
            else:
                self.subtitle_item.hide()

    def set_logos(self, logos=None, active_index=0, editable=False):
        self._current_logos = list(logos or [])
        if not self._current_logos or not self._logo_visible:
            if hasattr(self, "logo_item") and self.logo_item is not None:
                self.logo_item.hide()
            return

        idx = max(0, min(active_index, len(self._current_logos) - 1))
        logo_data = self._current_logos[idx]
        src = str(logo_data.get("source", "") or "")
        if not src or not os.path.exists(src):
            if hasattr(self, "logo_item") and self.logo_item is not None:
                self.logo_item.hide()
            return

        self._raw_logo_pixmap = QPixmap(src)
        if self._raw_logo_pixmap.isNull():
            if hasattr(self, "logo_item") and self.logo_item is not None:
                self.logo_item.hide()
            return

        self._logo_opacity = float(logo_data.get("opacity", 1.0))
        self._logo_rotation = float(logo_data.get("rotation", 0.0) or 0.0)
        self.logo_item.setOpacity(self._logo_opacity)
        self.reposition_logo()
        self.logo_item.show()
        self.viewport().update()

    def set_logo_opacity(self, opacity: float = 1.0):
        self._logo_opacity = max(0.0, min(1.0, float(opacity)))
        if hasattr(self, "logo_item") and self.logo_item is not None:
            self.logo_item.setOpacity(self._logo_opacity)
            self.viewport().update()

    def set_logo_rotation(self, rotation: float = 0.0):
        self._logo_rotation = float(rotation)
        if hasattr(self, "logo_item") and self.logo_item is not None:
            self.logo_item.setRotation(self._logo_rotation)
            self.viewport().update()

    def set_logo_editable(self, editable: bool):
        pass

    def set_logo_track_visible(self, visible: bool):
        self._logo_visible = bool(visible)
        if hasattr(self, "logo_item") and self.logo_item is not None:
            if not self._logo_visible:
                self.logo_item.hide()
            elif self._current_logos and self._raw_logo_pixmap and not self._raw_logo_pixmap.isNull():
                self.logo_item.show()
            self.viewport().update()

    def clear_logo(self):
        self._current_logos = []
        self._raw_logo_pixmap = None
        if hasattr(self, "logo_item") and self.logo_item is not None:
            self.logo_item.hide()
            self.viewport().update()

    def set_logo_scale(self, scale: float = 0.2):
        if self._current_logos:
            self._current_logos[0]["width"] = max(0.02, min(1.0, float(scale)))
            self._current_logos[0]["height"] = max(0.02, min(1.0, float(scale)))
            self.reposition_logo()
            self.viewport().update()

    def set_logo_position(self, x: float = 0.05, y: float = 0.05):
        if self._current_logos:
            self._current_logos[0]["x"] = max(0.0, min(1.0, float(x)))
            self._current_logos[0]["y"] = max(0.0, min(1.0, float(y)))
            self.reposition_logo()
            self.viewport().update()

    def set_logo_properties(self, *args, **kwargs):
        pass

    def set_logo_image(self, *args, **kwargs):
        pass

    # Keep text-track controls functional after the logo helpers.  These
    # methods used to be duplicated later in the class as ``pass`` stubs,
    # silently overriding the real implementations above; toggling a text
    # layer therefore appeared to do nothing in the preview.

    def reposition_logo(self):
        if not hasattr(self, "logo_item") or not self._current_logos or self._raw_logo_pixmap is None or self._raw_logo_pixmap.isNull():
            return
        rect = self.get_preview_canvas_rect()
        if rect.width() <= 0 or rect.height() <= 0:
            return

        logo_data = self._current_logos[0]
        x_norm = float(logo_data.get("x", 0.05))
        y_norm = float(logo_data.get("y", 0.05))
        w_norm = float(logo_data.get("width", 0.2))
        h_norm = float(logo_data.get("height", 0.2))

        target_w = max(16, int(rect.width() * w_norm))
        target_h = max(16, int(rect.height() * h_norm))

        scaled_pix = self._raw_logo_pixmap.scaled(target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.logo_item.setPixmap(scaled_pix)

        pos_x = rect.left() + rect.width() * x_norm
        pos_y = rect.top() + rect.height() * y_norm
        self.logo_item.setPos(pos_x, pos_y)

    def _resolve_canvas_aspect_ratio(self) -> float | None:
        aspect_key = str(getattr(self, "preview_aspect_key", "source") or "source").strip().lower()
        aspect_map = {
            "16:9": 16.0 / 9.0,
            "9:16": 9.0 / 16.0,
            "1:1": 1.0,
            "4:3": 4.0 / 3.0,
        }
        if aspect_key in aspect_map:
            return aspect_map[aspect_key]
        if self.video_source_width and self.video_source_height:
            return self.video_source_width / self.video_source_height
        return None

    def get_preview_canvas_rect(self) -> QRectF:
        view_w, view_h = float(self.width()), float(self.height())
        if view_w <= 0 or view_h <= 0:
            return QRectF(0, 0, 0, 0)
        canvas_ratio = self._resolve_canvas_aspect_ratio()
        if not canvas_ratio:
            return QRectF(0, 0, view_w, view_h)

        scale_mode = str(getattr(self, "preview_scale_mode", "fit") or "fit").strip().lower()
        aspect_key = str(getattr(self, "preview_aspect_key", "source") or "source").strip().lower()
        source_aspect = (self.video_source_width / self.video_source_height) if self.video_source_width and self.video_source_height else None
        if scale_mode == "fill" and (aspect_key == "source" or (source_aspect and canvas_ratio and abs(source_aspect - canvas_ratio) < 0.05)):
            return QRectF(0.0, 0.0, view_w, view_h)

        view_ratio = view_w / view_h if view_h else canvas_ratio

        if canvas_ratio > view_ratio:
            content_w = view_w
            content_h = view_w / canvas_ratio
            offset_x = 0
            offset_y = (view_h - content_h) / 2
        else:
            content_h = view_h
            content_w = view_h * canvas_ratio
            offset_x = (view_w - content_w) / 2
            offset_y = 0

        return QRectF(offset_x, offset_y, content_w, content_h)

    def get_video_content_rect(self) -> QRectF:
        canvas_rect = self.get_preview_canvas_rect()
        if canvas_rect.width() <= 0 or canvas_rect.height() <= 0:
            return QRectF(0, 0, 0, 0)
        if not self.video_source_width or not self.video_source_height:
            return canvas_rect

        source_ratio = self.video_source_width / self.video_source_height
        canvas_ratio = canvas_rect.width() / canvas_rect.height() if canvas_rect.height() else source_ratio

        scale_mode = str(getattr(self, "preview_scale_mode", "fit") or "fit").strip().lower()
        if scale_mode == "fill":
            if source_ratio > canvas_ratio:
                content_h = canvas_rect.height()
                content_w = content_h * source_ratio
                overflow_w = max(0.0, content_w - canvas_rect.width())
                offset_x = canvas_rect.left() - overflow_w * float(getattr(self, "preview_fill_focus_x", 0.5))
                offset_y = canvas_rect.top()
            else:
                content_w = canvas_rect.width()
                content_h = content_w / source_ratio
                offset_x = canvas_rect.left()
                overflow_h = max(0.0, content_h - canvas_rect.height())
                offset_y = canvas_rect.top() - overflow_h * float(getattr(self, "preview_fill_focus_y", 0.5))
        else:
            if source_ratio > canvas_ratio:
                content_w = canvas_rect.width()
                content_h = content_w / source_ratio
                offset_x = canvas_rect.left()
                offset_y = canvas_rect.top() + (canvas_rect.height() - content_h) / 2.0
            else:
                content_h = canvas_rect.height()
                content_w = content_h * source_ratio
                offset_x = canvas_rect.left() + (canvas_rect.width() - content_w) / 2.0
                offset_y = canvas_rect.top()
        return QRectF(offset_x, offset_y, content_w, content_h)

    def reposition_subtitle(self):
        item = self.subtitle_item
        rect = self.get_preview_canvas_rect()
        if rect.width() <= 0 or rect.height() <= 0:
            return

        source_w = max(1, int(self.subtitle_render_width or self.video_source_width or rect.width()))
        source_h = max(1, int(self.subtitle_render_height or self.video_source_height or rect.height()))
        scale_x = rect.width() / source_w
        scale_y = rect.height() / source_h
        side_margin_px = 60 * scale_x

        desired_width = max(1, min(int(rect.width() - 2 * side_margin_px), int((source_w - 120) * scale_x)))
        item.set_layout_width(desired_width)

        base_font = getattr(item, "base_font_size", None)
        if base_font is not None and base_font > 0:
            preview_font_size = max(1, int(round(base_font * scale_y)))
            base_outline = getattr(item, "base_outline_width", 2.0)
            scaled_outline = max(0.0, float(base_outline) * scale_y)
            base_pad = getattr(item, "base_padding", 4.0)
            scaled_pad = max(1.0, float(base_pad) * scale_y)
            base_rad = getattr(item, "base_radius", 0.0)
            scaled_rad = max(0.0, float(base_rad) * scale_y)
            item.set_style(
                font_size=preview_font_size,
                outline_width=scaled_outline,
                background_padding=scaled_pad,
                background_radius=scaled_rad,
            )

        item_w, item_h = item.W, item.H
        left_pad = rect.left() + side_margin_px
        right_limit = rect.right() - item_w - side_margin_px
        if item.custom_position_enabled:
            x_pos = rect.left() + (rect.width() * item.custom_x_percent / 100.0) - (item_w / 2.0)
            y_pos = rect.top() + (rect.height() * item.custom_y_percent / 100.0) - (item_h / 2.0)
        else:
            if item.alignment == "Bottom Left":
                x_pos = left_pad
            elif item.alignment == "Bottom Right":
                x_pos = right_limit
            else:
                x_pos = rect.left() + (rect.width() - item_w) / 2

            x_pos += item.x_offset * scale_x
            if item.alignment == "Top Center":
                y_pos = rect.top() + (item.bottom_offset * scale_y)
            elif item.alignment == "Center":
                y_pos = rect.top() + (rect.height() - item_h) / 2 + (item.bottom_offset * scale_y)
            else:
                y_pos = rect.bottom() - item_h - (item.bottom_offset * scale_y)

        x_pos = max(left_pad - item_w, min(x_pos, rect.right() + item_w)) # Allow slightly off-screen
        y_min = rect.top() - item_h
        y_max = rect.bottom()
        y_pos = max(y_min, min(y_pos, y_max))
        item.setPos(QPointF(x_pos, y_pos))

    def _can_drag_framing(self) -> bool:
        if str(getattr(self, "preview_scale_mode", "fit") or "fit").strip().lower() != "fill":
            return False
        canvas_rect = self.get_preview_canvas_rect()
        content_rect = self.get_video_content_rect()
        return content_rect.width() > canvas_rect.width() + 0.5 or content_rect.height() > canvas_rect.height() + 0.5

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos_p = event.pos() if hasattr(event, "pos") else event.position().toPoint()
            item = self.itemAt(pos_p)
            if item is not self.subtitle_item and hasattr(self, "subtitle_item") and self.subtitle_item is not None:
                self.subtitle_item.set_selected(False)
            if self._can_drag_framing():
                pos = QPointF(event.position()) if hasattr(event, "position") else QPointF(event.pos())
                if self.get_preview_canvas_rect().contains(pos):
                    self._framing_drag_active = True
                    self._framing_drag_start = pos
                    self._framing_drag_focus = self.get_preview_fill_focus()
                    self.viewport().setCursor(Qt.ClosedHandCursor)
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._framing_drag_active:
            pos = QPointF(event.position()) if hasattr(event, "position") else QPointF(event.pos())
            canvas_rect = self.get_preview_canvas_rect()
            content_rect = self.get_video_content_rect()
            dx = pos.x() - self._framing_drag_start.x()
            dy = pos.y() - self._framing_drag_start.y()
            focus_x, focus_y = self._framing_drag_focus
            overflow_w = max(0.0, content_rect.width() - canvas_rect.width())
            overflow_h = max(0.0, content_rect.height() - canvas_rect.height())
            if overflow_w > 0.0:
                focus_x = max(0.0, min(1.0, focus_x - (dx / overflow_w)))
            if overflow_h > 0.0:
                focus_y = max(0.0, min(1.0, focus_y - (dy / overflow_h)))
            self.set_preview_fill_focus(focus_x, focus_y)
            self.framingChanged.emit(focus_x, focus_y)
            event.accept()
            return
        if self._can_drag_framing():
            self.viewport().setCursor(Qt.OpenHandCursor)
        else:
            self.viewport().unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._framing_drag_active and event.button() == Qt.LeftButton:
            self._framing_drag_active = False
            if self._can_drag_framing():
                self.viewport().setCursor(Qt.OpenHandCursor)
            else:
                self.viewport().unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.scaleModeToggleRequested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        canvas_rect = self.get_preview_canvas_rect()
        if canvas_rect.width() <= 0 or canvas_rect.height() <= 0:
            return

        painter = QPainter(self.viewport())
        outer = QPainterPath()
        outer.addRect(QRectF(self.viewport().rect()))
        inner = QPainterPath()
        inner.addRect(canvas_rect)
        matte = outer.subtracted(inner)
        if not matte.isEmpty():
            painter.fillPath(matte, QColor(9, 13, 22, 240))
        painter.setPen(QPen(QColor(38, 52, 74, 180), 1.0))
        painter.drawRect(canvas_rect)

        aspect_key = str(getattr(self, "preview_aspect_key", "source") or "source").strip().lower()
        if aspect_key != "source":
            label = aspect_key.upper()
            metrics = painter.fontMetrics()
            text_w = metrics.horizontalAdvance(label) + 18
            text_h = metrics.height() + 8
            chip_rect = QRectF(
                canvas_rect.right() - text_w - 10,
                canvas_rect.top() + 10,
                text_w,
                text_h,
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(12, 24, 38, 210))
            painter.drawRoundedRect(chip_rect, 9, 9)
            painter.setPen(QColor(183, 227, 255))
            painter.drawText(chip_rect, Qt.AlignCenter, label)

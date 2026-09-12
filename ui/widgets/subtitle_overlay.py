import math
from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QGraphicsObject, QGraphicsItem


class SubtitleOverlayItem(QGraphicsObject):
    """A draggable graphics item to represent the subtitle overlay on VideoView."""
    positionDragStarted = Signal()
    positionDragFinished = Signal(int, int)  # x_percent, y_percent
    positionChanged = Signal(int, int)
    fontSizeChanged = Signal(int)  # new_base_font_size
    subtitleClicked = Signal()

    W, H = 640, 48
    LINE_HEIGHT_FACTOR = 1.35
    VERTICAL_PADDING = 4
    HANDLE_SIZE = 12.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setZValue(10)
        self.current_text = ""
        self.current_lines: list[str] = []
        self.font_name = "Segoe UI"
        self.font_size = 20
        self.base_font_size = 60
        self.font_color = QColor(255, 255, 255)
        self.outline_width = 2
        self.base_outline_width = 2.0
        self.outline_color = QColor(0, 0, 0, 220)
        self.alignment = "Bottom Center"
        self.background_box = False
        self.background_color = QColor(0, 0, 0, 170)
        self.background_padding = 4.0
        self.base_padding = 4.0
        self.background_radius = 0.0
        self.base_radius = 0.0
        self.single_line = False
        self.bold = True
        self.shadow_color = QColor(0, 0, 0, 160)
        self.shadow_depth = 0.0
        self.x_offset = 0
        self.bottom_offset = 30
        self.custom_position_enabled = False
        self.custom_x_percent = 50
        self.custom_y_percent = 86
        self.highlight_color = QColor("#FFD400")
        self.highlight_phrases: list[str] = []
        self.karaoke_word_index = -1
        self.auto_keyword_highlight = False
        self.animation_style = "static"
        self.animation_progress = 1.0
        self._text_rendering_enabled = True
        self._editable = False
        self._suppressed = False
        self._target_view = None
        self._is_selected = False
        self._drag_mode = ""  # "", "move", "top_left", "top_right", "bottom_left", "bottom_right"
        self._press_scene_pos = QPointF()
        self._press_item_pos = QPointF()
        self._initial_base_font_size = 60
        self._initial_center_scene = QPointF()
        self._initial_distance = 1.0

    def attach_to_view(self, view):
        self._target_view = view

    def set_editable(self, editable: bool):
        """Match the MPV subtitle overlay API on the Qt fallback preview."""
        self._editable = bool(editable)
        if not self._editable:
            self._is_selected = False
            self._drag_mode = ""
        self.update()

    def set_selected(self, selected: bool):
        if self._is_selected != bool(selected):
            self._is_selected = bool(selected)
            self.update()

    def is_selected(self) -> bool:
        return bool(self._is_selected)

    def set_suppressed(self, suppressed: bool):
        """Temporarily keep this overlay hidden during modal dialogs."""
        self._suppressed = bool(suppressed)
        if self._suppressed:
            self.hide()
        elif self.current_text or self.current_lines:
            self.show()

    def is_top_level_overlay(self) -> bool:
        return False

    def set_effects(self, *, highlight_color=None, highlight_phrases=None,
                    karaoke_word_index=-1, auto_keyword_highlight=False,
                    animation_style="Static", animation_progress=1.0):
        """Apply cue-specific highlight and karaoke effects."""
        self.highlight_color = QColor(highlight_color or "#FFD400")
        self.highlight_phrases = [str(value).strip() for value in (highlight_phrases or []) if str(value).strip()]
        self.karaoke_word_index = int(karaoke_word_index)
        self.auto_keyword_highlight = bool(auto_keyword_highlight)
        self.animation_style = str(animation_style or "Static").strip().lower()
        self.animation_progress = max(0.0, min(1.0, float(animation_progress)))
        self.update()

    def set_text_rendering(self, enabled: bool):
        """Enable/disable Qt text painting while retaining the drag item."""
        if not self.is_top_level_overlay():
            self._text_rendering_enabled = True
            return
        enabled = bool(enabled)
        if enabled == self._text_rendering_enabled:
            return
        self._text_rendering_enabled = enabled
        self.update()

    def set_text(self, text):
        new_lines = [line for line in str(text or "").splitlines() if line] or ([] if not text else [str(text)])
        if self.current_lines != new_lines or self.current_text != text:
            self.current_text = text
            self.current_lines = new_lines
            self._update_height()
            self.update()
        if text and not self._suppressed:
            self.show()
        elif not text:
            self.hide()

    def set_lines(self, lines):
        """Set multiple subtitle lines (e.g. when two segments overlap)."""
        cleaned = [str(line or "").strip() for line in (lines or []) if str(line or "").strip()]
        joined = "\n".join(cleaned)
        if self.current_lines != cleaned or self.current_text != joined:
            self.current_lines = cleaned
            self.current_text = joined
            self._update_height()
            self.update()
        if cleaned and not self._suppressed:
            self.show()
        elif not cleaned:
            self.hide()

    def _line_layout_heights(self) -> list[int]:
        font = QFont(self.font_name)
        font.setPixelSize(max(1, int(self.font_size)))
        font.setBold(bool(self.bold))
        metrics = QFontMetrics(font)
        fallback = max(12, int(round(self.font_size * self.LINE_HEIGHT_FACTOR)))
        flags = int(Qt.AlignCenter | Qt.TextWordWrap)
        width = max(1, int(self.W))
        entries = self.current_lines or [""]
        heights = []
        for text in entries:
            bounds = metrics.boundingRect(QRect(0, 0, width, 10000), flags, text)
            heights.append(max(fallback, int(bounds.height())))
        return heights

    def _update_height(self):
        new_h = max(16, sum(self._line_layout_heights()) + self.VERTICAL_PADDING * 2)
        if new_h != self.H:
            self.prepareGeometryChange()
            self.H = new_h

    def set_style(
        self,
        *,
        font_name=None,
        font_size=None,
        font_color=None,
        outline_width=None,
        outline_color=None,
        background_box=None,
        background_color=None,
        single_line=None,
        bold=None,
        shadow_color=None,
        shadow_depth=None,
        background_padding=None,
        background_radius=None,
        **kwargs,
    ):
        changed = False
        if font_name and font_name != self.font_name:
            self.font_name = font_name
            changed = True
        if font_size is not None and int(font_size) != self.font_size:
            self.prepareGeometryChange()
            self.font_size = int(font_size)
            self._update_height()
            changed = True
        if font_color and font_color != self.font_color:
            self.font_color = font_color
            changed = True
        if outline_width is not None and float(outline_width) != self.outline_width:
            self.outline_width = max(0.0, float(outline_width))
            changed = True
        if outline_color is not None and outline_color != self.outline_color:
            self.outline_color = outline_color
            changed = True
        if background_box is not None and bool(background_box) != self.background_box:
            self.background_box = bool(background_box)
            changed = True
        if background_color is not None and background_color != self.background_color:
            self.background_color = background_color
            changed = True
        if single_line is not None and bool(single_line) != self.single_line:
            self.single_line = bool(single_line)
            changed = True
        if bold is not None and bool(bold) != self.bold:
            self.bold = bool(bold)
            changed = True
        if shadow_color is not None and shadow_color != self.shadow_color:
            self.shadow_color = shadow_color
            changed = True
        if shadow_depth is not None and float(shadow_depth) != self.shadow_depth:
            self.shadow_depth = max(0.0, float(shadow_depth))
            changed = True
        if background_padding is not None and float(background_padding) != self.background_padding:
            self.background_padding = max(1.0, float(background_padding))
            changed = True
        if background_radius is not None and float(background_radius) != self.background_radius:
            self.background_radius = max(0.0, float(background_radius))
            changed = True
        if kwargs.get("base_font_size") is not None:
            self.base_font_size = max(1, int(kwargs["base_font_size"]))
        elif font_size is not None and getattr(self, "base_font_size", None) is None:
            self.base_font_size = max(1, int(font_size))
        if kwargs.get("base_outline_width") is not None:
            self.base_outline_width = max(0.0, float(kwargs["base_outline_width"]))
        if kwargs.get("base_padding") is not None:
            self.base_padding = max(1.0, float(kwargs["base_padding"]))
        if kwargs.get("base_radius") is not None:
            self.base_radius = max(0.0, float(kwargs["base_radius"]))
        if changed:
            self._update_height()
            self.update()
        if (self.current_text or self.current_lines) and not self._suppressed:
            self.show()

    def set_alignment(self, alignment: str):
        self.alignment = alignment or "Bottom Center"
        self.update()

    def set_positioning(self, *, x_offset=None, bottom_offset=None, custom_position_enabled=None, custom_x_percent=None, custom_y_percent=None):
        if x_offset is not None:
            self.x_offset = x_offset
        if bottom_offset is not None:
            self.bottom_offset = bottom_offset
        if custom_position_enabled is not None:
            self.custom_position_enabled = bool(custom_position_enabled)
        if custom_x_percent is not None:
            self.custom_x_percent = int(custom_x_percent)
        if custom_y_percent is not None:
            self.custom_y_percent = int(custom_y_percent)
        self.update()

    def set_layout_width(self, width: int):
        width = max(20, int(width))
        if width != self.W:
            self.prepareGeometryChange()
            self.W = width
            self._update_height()
            self.update()

    def _get_content_rect(self) -> QRectF:
        font = QFont(self.font_name)
        font.setPixelSize(max(1, int(self.font_size)))
        font.setBold(bool(self.bold))
        metrics = QFontMetrics(font)
        entries = self.current_lines or ([self.current_text] if self.current_text else [""])
        max_text_width = max((metrics.boundingRect(line).width() for line in entries), default=0)
        box_pad_x = max(8.0, float(self.background_padding) + 6.0)
        w = max(40.0, min(float(self.W), float(max_text_width) + box_pad_x * 2.0))
        cx = float(self.W) / 2.0
        return QRectF(cx - w / 2.0, float(self.VERTICAL_PADDING), w, max(16.0, float(self.H - self.VERTICAL_PADDING * 2)))

    def _handle_rects(self, content_rect: QRectF) -> dict[str, QRectF]:
        s = float(self.HANDLE_SIZE)
        half = s / 2.0
        points = {
            "top_left": content_rect.topLeft(),
            "top_right": content_rect.topRight(),
            "bottom_left": content_rect.bottomLeft(),
            "bottom_right": content_rect.bottomRight(),
        }
        return {
            key: QRectF(point.x() - half, point.y() - half, s, s)
            for key, point in points.items()
        }

    def _hit_test(self, pos: QPointF) -> str:
        content_rect = self._get_content_rect()
        if self._is_selected or self._editable:
            for handle_name, handle_rect in self._handle_rects(content_rect).items():
                if handle_rect.adjusted(-4, -4, 4, 4).contains(pos):
                    return handle_name
        if content_rect.adjusted(-6, -6, 6, 6).contains(pos):
            return "move"
        return ""

    def boundingRect(self):
        s = float(self.HANDLE_SIZE) + 8.0
        return QRectF(-s, -s, self.W + s * 2, self.H + s * 2)

    def hoverMoveEvent(self, event):
        if not self._text_rendering_enabled or self._suppressed or (not self.current_text and not self.current_lines):
            super().hoverMoveEvent(event)
            return
        hit = self._hit_test(event.pos())
        if hit in ("top_left", "bottom_right"):
            self.setCursor(Qt.SizeFDiagCursor)
        elif hit in ("top_right", "bottom_left"):
            self.setCursor(Qt.SizeBDiagCursor)
        elif hit == "move":
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.setCursor(Qt.ArrowCursor)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or not self._text_rendering_enabled or self._suppressed:
            super().mousePressEvent(event)
            return
        hit = self._hit_test(event.pos())
        if hit:
            self._drag_mode = hit
            self._is_selected = True
            self._editable = True
            self._press_scene_pos = event.scenePos()
            self._press_item_pos = event.pos()
            self._initial_base_font_size = int(getattr(self, "base_font_size", 60) or 60)
            content_rect = self._get_content_rect()
            self._initial_center_scene = self.mapToScene(content_rect.center())
            self._initial_distance = max(10.0, math.hypot(
                event.scenePos().x() - self._initial_center_scene.x(),
                event.scenePos().y() - self._initial_center_scene.y()
            ))
            if hit == "move":
                self.setCursor(Qt.ClosedHandCursor)
                self.positionDragStarted.emit()
            self.subtitleClicked.emit()
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._drag_mode:
            super().mouseMoveEvent(event)
            return
        view = self._target_view
        if view is None:
            views = self.scene().views() if self.scene() else []
            if views:
                view = views[0]
        if view is None or not hasattr(view, "get_preview_canvas_rect"):
            super().mouseMoveEvent(event)
            return
        canvas = view.get_preview_canvas_rect()
        if canvas.width() <= 0 or canvas.height() <= 0:
            super().mouseMoveEvent(event)
            return

        if self._drag_mode == "move":
            delta = event.scenePos() - self._press_scene_pos
            new_cx = self._initial_center_scene.x() + delta.x()
            new_cy = self._initial_center_scene.y() + delta.y()
            new_cx = max(canvas.left(), min(new_cx, canvas.right()))
            new_cy = max(canvas.top(), min(new_cy, canvas.bottom()))
            x_pct = int(round((new_cx - canvas.left()) * 100.0 / canvas.width()))
            y_pct = int(round((new_cy - canvas.top()) * 100.0 / canvas.height()))
            self.custom_position_enabled = True
            self.custom_x_percent = max(0, min(100, x_pct))
            self.custom_y_percent = max(0, min(100, y_pct))
            view.reposition_subtitle()
            self.positionChanged.emit(self.custom_x_percent, self.custom_y_percent)
            event.accept()
            return
        elif self._drag_mode in ("top_left", "top_right", "bottom_left", "bottom_right"):
            cur_dist = math.hypot(
                event.scenePos().x() - self._initial_center_scene.x(),
                event.scenePos().y() - self._initial_center_scene.y()
            )
            ratio = cur_dist / max(10.0, self._initial_distance)
            new_base = int(round(self._initial_base_font_size * ratio))
            new_base = max(12, min(140, new_base))
            self.base_font_size = new_base
            source_h = max(1, int(getattr(view, "subtitle_render_height", 0) or getattr(view, "video_source_height", 0) or 1080))
            scale_y = canvas.height() / source_h if canvas.height() > 0 else 1.0
            preview_font_size = max(1, int(round(new_base * scale_y)))
            self.set_style(font_size=preview_font_size, base_font_size=new_base)
            view.reposition_subtitle()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_mode == "move":
            self.setCursor(Qt.OpenHandCursor)
            self.positionDragFinished.emit(self.custom_x_percent, self.custom_y_percent)
        elif self._drag_mode in ("top_left", "top_right", "bottom_left", "bottom_right"):
            self.setCursor(Qt.OpenHandCursor)
            self.fontSizeChanged.emit(int(getattr(self, "base_font_size", self.font_size) or 60))
        self._drag_mode = ""
        self.update()
        event.accept()

    def paint(self, painter, option, widget):
        if not self._text_rendering_enabled:
            return
        if not self.current_text and not self.current_lines and not self.isVisible():
            return
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0, 0, self.W, self.H)

        if not self.current_lines:
            return

        painter.setPen(self.font_color)
        font = QFont(self.font_name)
        font.setPixelSize(max(1, int(self.font_size)))
        font.setBold(bool(self.bold))
        painter.setFont(font)
        wrap_flags = Qt.AlignCenter | Qt.TextWordWrap
        line_heights = self._line_layout_heights()

        line_rects: list[QRectF] = []
        if len(self.current_lines) == 1:
            lh = line_heights[0] if line_heights else float(self.H - self.VERTICAL_PADDING * 2)
            line_rects = [QRectF(
                rect.x(), float(self.VERTICAL_PADDING), rect.width(), lh,
            )]
        else:
            y = float(self.VERTICAL_PADDING)
            for lh in line_heights:
                line_rects.append(QRectF(rect.x(), y, rect.width(), lh))
                y += lh

        if self.background_box:
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.background_color)
            metrics = painter.fontMetrics()
            box_pad_x = max(2, int(round(self.background_padding)))
            box_pad_y = max(1, int(round(self.background_padding * 0.6)))
            max_width = max((metrics.boundingRect(line).width() for line in self.current_lines), default=0)
            if max_width and line_rects:
                block_top = line_rects[0].top()
                block_bottom = line_rects[-1].bottom()
                text_rect = QRect(
                    int(round(rect.center().x() - max_width / 2.0)),
                    int(round(block_top)),
                    max_width,
                    max(1, int(round(block_bottom - block_top))),
                ).adjusted(-box_pad_x, -box_pad_y, box_pad_x, box_pad_y)
                radius = max(0, int(round(self.background_radius)))
                if radius > 0:
                    painter.drawRoundedRect(QRectF(text_rect), radius, radius)
                else:
                    painter.drawRect(QRectF(text_rect))

        if self.shadow_depth > 0:
            painter.setPen(self.shadow_color)
            for line_text, line_rect in zip(self.current_lines, line_rects):
                painter.drawText(line_rect.translated(self.shadow_depth, self.shadow_depth), int(wrap_flags), line_text)

        if self.outline_width > 0:
            stroke_max = max(0.4, min(float(self.outline_width), float(self.font_size) * 0.2))
            w = max(0.4, stroke_max)
            outline_offsets = [
                (-w, 0), (w, 0), (0, -w), (0, w),
                (-w * 0.7, -w * 0.7), (w * 0.7, -w * 0.7),
                (-w * 0.7, w * 0.7), (w * 0.7, w * 0.7),
            ]
            painter.setPen(self.outline_color)
            for line_text, line_rect in zip(self.current_lines, line_rects):
                for dx, dy in outline_offsets:
                    painter.drawText(line_rect.translated(dx, dy), int(wrap_flags), line_text)

        painter.setPen(self.font_color)
        for line_text, line_rect in zip(self.current_lines, line_rects):
            painter.drawText(line_rect, int(wrap_flags), line_text)

        # CapCut-style Bounding Box & Transform Handles
        if self._editable and self._is_selected:
            content_rect = self._get_content_rect()
            gizmo_rect = content_rect.adjusted(-6, -4, 6, 4)

            # High-contrast drop shadow / outline
            painter.setPen(QPen(QColor(0, 0, 0, 180), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(gizmo_rect, 2, 2)

            # Bright cyan dashed selection border
            painter.setPen(QPen(QColor("#00E5FF"), 1.5, Qt.DashLine))
            painter.drawRoundedRect(gizmo_rect, 2, 2)

            # 4 Corner Handles
            for handle_name, handle_rect in self._handle_rects(content_rect).items():
                painter.setPen(QPen(QColor(0, 0, 0, 220), 1.5))
                painter.setBrush(QColor("#00E5FF"))
                painter.drawEllipse(handle_rect)
                inner = handle_rect.adjusted(3, 3, -3, -3)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(255, 255, 255))
                painter.drawEllipse(inner)

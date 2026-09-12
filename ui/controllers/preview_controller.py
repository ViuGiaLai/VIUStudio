import os
import hashlib
import json
import re
import shutil
import subprocess
import time

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QFileDialog, QMessageBox

from runtime_paths import bin_path
from worker_adapters import (
    AutoRecapRenderWorker,
    ExactFramePreviewWorker,
    FinalExportWorker,
    PreviewMuxWorker,
    QuickPreviewWorker,
)
from utils.thread_lifecycle import release_thread_when_stopped


class PreviewController:
    def __init__(self, gui):
        self.gui = gui

    def _extract_fast_preview_blur_regions(self, start_seconds: float, duration_seconds: float) -> list[dict]:
        """Compatibility helper using the same canonical visual-layer path."""
        result = self._rebase_timed_layers(
            self._extract_blur_layers(), start_seconds, duration_seconds
        )
        print(f"[Preview] Fast Preview extracted {len(result)} active blur layer(s).")
        return result

    def _extract_overlay_layers(self):
        mask_regions = []
        logo_layers = []
        text_layers = []
        try:
            if hasattr(self.gui, "timeline") and hasattr(self.gui.timeline, "_timeline"):
                timeline_obj = self.gui.timeline._timeline
                if timeline_obj:
                    for tr in timeline_obj.tracks:
                        track_type = tr.type.value if hasattr(tr.type, "value") else str(tr.type)
                        print(f"[Preview] Checking track: name={tr.name} type={track_type}")
                        if not bool(getattr(tr, "visible", True)):
                            continue
                        if track_type == "mask":
                            for layer in tr.layers:
                                try:
                                    if not bool(getattr(layer, "visible", True)):
                                        continue
                                    mask_regions.append({
                                        "x": float(getattr(layer, "position_x", 0.3)),
                                        "y": float(getattr(layer, "position_y", 0.4)),
                                        "width": float(getattr(layer, "width", 0.4)),
                                        "height": float(getattr(layer, "height", 0.2)),
                                        "mode": str(getattr(layer, "mode", "solid")),
                                        "color": str(getattr(layer, "color", "#000000")),
                                        "opacity": float(getattr(layer, "opacity", 1.0)),
                                        "pixelate_size": int(getattr(layer, "pixelate_size", 12)),
                                        "blur_strength": int(getattr(layer, "blur_strength", 20)),
                                        "start": float(getattr(layer, "start", 0.0) or 0.0),
                                        "end": float(getattr(layer, "end", 0.0) or 0.0),
                                    })
                                except (TypeError, ValueError):
                                    continue
                        elif track_type == "image":
                            for layer in tr.layers:
                                try:
                                    if not getattr(layer, "visible", True):
                                        continue
                                    source = getattr(layer, "source", "")
                                    if not source:
                                        continue
                                    transform = getattr(layer, "transform", None)
                                    if transform:
                                        val_x = getattr(transform, "x", 0.0)
                                        raw_x = float(val_x if val_x is not None else 0.0)
                                        x = raw_x / 100.0 if raw_x > 1.0 else raw_x
                                        val_y = getattr(transform, "y", 0.0)
                                        raw_y = float(val_y if val_y is not None else 0.0)
                                        y = raw_y / 100.0 if raw_y > 1.0 else raw_y
                                        val_sx = getattr(transform, "scale_x", 0.2)
                                        raw_sx = float(val_sx if val_sx is not None else 0.2)
                                        w = raw_sx / 100.0 if raw_sx > 1.0 else raw_sx
                                        val_sy = getattr(transform, "scale_y", 0.2)
                                        raw_sy = float(val_sy if val_sy is not None else 0.2)
                                        h = raw_sy / 100.0 if raw_sy > 1.0 else raw_sy
                                        val_rot = getattr(transform, "rotation", 0.0)
                                        rotation = float(val_rot if val_rot is not None else 0.0)
                                    else:
                                        x = 0.0
                                        y = 0.0
                                        w = 0.2
                                        h = 0.2
                                        rotation = 0.0
                                    logo_layers.append({
                                        "source": str(source),
                                        "x": x,
                                        "y": y,
                                        "width": w,
                                        "height": h,
                                        "opacity": float(getattr(layer, "opacity", 1.0) or 1.0),
                                        "rotation": rotation,
                                        "start": float(getattr(layer, "start", 0.0) or 0.0),
                                        "end": float(getattr(layer, "end", 0.0) or 0.0),
                                    })
                                    print(f"[Preview/Export] Added logo layer: source={source}, x={x:.2f}, y={y:.2f}, w={w:.2f}, h={h:.2f}")
                                except (TypeError, ValueError) as e:
                                    print(f"[Preview] Failed to extract logo layer: {e}")
                                    continue
                        elif track_type == "text":
                            for layer in tr.layers:
                                try:
                                    if not getattr(layer, "visible", True):
                                        continue
                                    text = str(getattr(layer, "text", "") or "").strip()
                                    if not text:
                                        continue
                                    transform = getattr(layer, "transform", None)
                                    text_layers.append({
                                        "text": text,
                                        "font_name": str(getattr(layer, "font_name", "Arial") or "Arial"),
                                        "font_size": float(getattr(layer, "font_size", 60) or 60),
                                        "font_color": str(getattr(layer, "font_color", "#FFFFFF") or "#FFFFFF"),
                                        "background_color": str(getattr(layer, "background_color", "") or ""),
                                        "background_opacity": max(0.0, min(1.0, float(getattr(layer, "background_opacity", 0.5) or 0.0))),
                                        "opacity": max(0.0, min(1.0, float(getattr(layer, "opacity", 1.0) or 1.0))),
                                        "font_bold": bool(getattr(layer, "font_bold", False)),
                                        "font_italic": bool(getattr(layer, "font_italic", False)),
                                        "font_underline": bool(getattr(layer, "font_underline", False)),
                                        "x": float(getattr(transform, "x", 0.5)) if transform else 0.5,
                                        "y": float(getattr(transform, "y", 0.5)) if transform else 0.5,
                                        "start": float(getattr(layer, "start", 0.0) or 0.0),
                                        "end": float(getattr(layer, "end", 0.0) or 0.0),
                                    })
                                except (TypeError, ValueError):
                                    continue
        except Exception as e:
            print(f"Warning: Failed to extract logo layers: {e}")

        print(f"[Preview] Final overlay extraction: {len(mask_regions)} mask(s), {len(logo_layers)} logo(s), {len(text_layers)} text layer(s)")
        return mask_regions, logo_layers, text_layers

    def _extract_blur_layers(self) -> list[dict]:
        """Read every visible B1 layer from the live timeline model."""
        result = []
        timeline = getattr(getattr(self.gui, "timeline", None), "_timeline", None)
        for track in list(getattr(timeline, "tracks", []) or []):
            track_type = getattr(getattr(track, "type", None), "value", getattr(track, "type", ""))
            if str(track_type).lower() != "blur" or not bool(getattr(track, "visible", True)):
                continue
            for layer in list(getattr(track, "layers", []) or []):
                if not bool(getattr(layer, "visible", True)):
                    continue
                try:
                    result.append({
                        "x": float(getattr(layer, "position_x", 0.0) or 0.0),
                        "y": float(getattr(layer, "position_y", 0.0) or 0.0),
                        "width": float(getattr(layer, "width", 0.0) or 0.0),
                        "height": float(getattr(layer, "height", 0.0) or 0.0),
                        "blur_strength": float(getattr(layer, "blur_strength", 20.0) or 20.0),
                        "blur_opacity": float(getattr(layer, "blur_opacity", 1.0) or 1.0),
                        "pixelate": bool(getattr(layer, "pixelate", False)),
                        "pixelate_size": int(getattr(layer, "pixelate_size", 12) or 12),
                        "start": float(getattr(layer, "start", 0.0) or 0.0),
                        "end": float(getattr(layer, "end", 0.0) or 0.0),
                    })
                except (TypeError, ValueError):
                    continue
        return result

    @staticmethod
    def _rebase_timed_layers(layers, start_seconds: float, duration_seconds: float) -> list[dict]:
        """Clip project-time visual layers and rebase them to a preview clip."""
        clip_start = max(0.0, float(start_seconds or 0.0))
        duration = max(0.0, float(duration_seconds or 0.0))
        clip_end = clip_start + duration
        result = []
        for raw in list(layers or []):
            layer = dict(raw)
            try:
                start = max(0.0, float(layer.get("start", 0.0) or 0.0))
                end = float(layer.get("end", 0.0) or 0.0)
            except (TypeError, ValueError):
                continue
            if end <= start:
                if start > clip_end:
                    continue
                layer["start"], layer["end"] = 0.0, 0.0
                result.append(layer)
                continue
            overlap_start = max(start, clip_start)
            overlap_end = min(end, clip_end)
            if overlap_end <= overlap_start:
                continue
            layer["start"] = overlap_start - clip_start
            layer["end"] = overlap_end - clip_start
            result.append(layer)
        return result

    def _extract_render_layers(self):
        masks, logos, texts = self._extract_overlay_layers()
        return masks, self._extract_blur_layers(), logos, texts

    @staticmethod
    def _ass_timestamp(seconds: float) -> str:
        total = max(0, int(round(float(seconds) * 100)))
        hours, total = divmod(total, 360000)
        minutes, total = divmod(total, 6000)
        whole, centis = divmod(total, 100)
        return f"{hours}:{minutes:02d}:{whole:02d}.{centis:02d}"

    @staticmethod
    def _parse_ass_timestamp(value: str) -> float:
        """Return an ASS H:MM:SS.cc timestamp as seconds."""
        match = re.fullmatch(r"\s*(\d+):(\d{1,2}):(\d{1,2})[.:](\d{1,2})\s*", str(value or ""))
        if not match:
            raise ValueError(f"Invalid ASS timestamp: {value!r}")
        hours, minutes, seconds, centiseconds = (int(part) for part in match.groups())
        return hours * 3600.0 + minutes * 60.0 + seconds + centiseconds / 100.0

    def _build_fast_preview_subtitle_ass(self, start_seconds: float, duration_seconds: float) -> str:
        """Rebase the live libass script to the short Fast Preview clip.

        The editor and final export use the live ASS file as their source of truth.
        Fast Preview trims the source video first, so its subtitle events need only a
        time offset; copying the script otherwise keeps font metrics, positions,
        speaker colours, boxes, and animation styles identical.
        """
        try:
            self.gui.sync_live_subtitle_preview()
            live_ass_path = str(getattr(self.gui, "live_preview_ass_path", "") or "")
            if not live_ass_path or not os.path.isfile(live_ass_path):
                segments = self.gui.live_preview_segments or self.gui.get_active_segments()
                if segments:
                    _srt, ass_path = self.gui._write_live_preview_assets(segments)
                    live_ass_path = ass_path
            if not live_ass_path or not os.path.isfile(live_ass_path):
                return ""

            clip_start = max(0.0, float(start_seconds))
            clip_end = clip_start + max(0.0, float(duration_seconds))
            rebased_lines = []
            event_count = 0
            with open(live_ass_path, "r", encoding="utf-8-sig", errors="replace") as handle:
                for raw_line in handle:
                    if not raw_line.startswith("Dialogue:"):
                        rebased_lines.append(raw_line)
                        continue
                    parts = raw_line.rstrip("\r\n").split(":", 1)
                    fields = parts[1].lstrip().split(",", 9) if len(parts) == 2 else []
                    if len(fields) != 10:
                        rebased_lines.append(raw_line)
                        continue
                    try:
                        event_start = self._parse_ass_timestamp(fields[1])
                        event_end = self._parse_ass_timestamp(fields[2])
                    except ValueError:
                        rebased_lines.append(raw_line)
                        continue
                    if event_end <= clip_start or event_start >= clip_end:
                        continue
                    fields[1] = self._ass_timestamp(max(event_start, clip_start) - clip_start)
                    fields[2] = self._ass_timestamp(min(event_end, clip_end) - clip_start)
                    rebased_lines.append("Dialogue: " + ",".join(fields) + "\n")
                    event_count += 1

            if not event_count:
                return ""
            preview_dir = self.gui.get_project_temp_dir("preview")
            os.makedirs(preview_dir, exist_ok=True)
            output_path = os.path.join(preview_dir, f"fast_preview_subtitle_{int(time.time() * 1000)}.ass")
            with open(output_path, "w", encoding="utf-8") as handle:
                handle.writelines(rebased_lines)
            print(f"[Preview] Rebased {event_count} live ASS subtitle event(s) for Fast Preview.")
            return output_path
        except Exception as exc:
            print(f"[Preview] Could not build Fast Preview ASS from live preview: {exc}")
            return ""

    @staticmethod
    def _ass_color(value: str) -> str:
        value = str(value or "#FFFFFF").strip().lstrip("#")
        if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
            value = "FFFFFF"
        return f"&H00{value[4:6]}{value[2:4]}{value[0:2]}"

    @classmethod
    def _ass_color_with_opacity(cls, value: str, opacity: float) -> str:
        alpha = max(0, min(255, int(round((1.0 - max(0.0, min(1.0, float(opacity)))) * 255))))
        return f"&H{alpha:02X}{cls._ass_color(value)[4:]}"

    def _build_fast_preview_text_ass(self, text_layers, start_seconds, duration_seconds, width, height, temp_dir):
        """Build a clip-relative ASS overlay for editor TEXT layers."""
        if not text_layers:
            return ""
        styles, events = [], []
        for index, layer in enumerate(text_layers):
            layer_start, layer_end = float(layer["start"]), float(layer["end"])
            clip_start = max(0.0, layer_start - start_seconds)
            clip_end = min(float(duration_seconds), layer_end - start_seconds)
            if clip_end <= clip_start:
                continue
            style_name = f"VIUStudioText{index}"
            background_color = layer.get("background_color", "")
            styles.append(
                f"Style: {style_name},{layer['font_name']},{max(1, int(round(layer['font_size'] * 0.85)))},{self._ass_color(layer['font_color'])},"
                f"&H000000FF,{self._ass_color_with_opacity(background_color, layer.get('background_opacity', 0.5)) if background_color else '&H00000000'},{self._ass_color_with_opacity(background_color, layer.get('background_opacity', 0.5)) if background_color else '&H00000000'},"
                f"{-1 if layer['font_bold'] else 0},0,0,0,100,100,0,0,{3 if background_color else 1},3,0,5,0,0,0,0"
            )
            text = str(layer["text"]).replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\r\n", "\n").replace("\n", "\\N")
            x = int(round(max(0.0, min(1.0, layer["x"])) * width))
            y = int(round(max(0.0, min(1.0, layer["y"])) * height))
            events.append(
                f"Dialogue: 10,{self._ass_timestamp(clip_start)},{self._ass_timestamp(clip_end)},{style_name},,0,0,0,,{{\\an5\\pos({x},{y})}}{text}"
            )
        if not events:
            return ""
        os.makedirs(temp_dir, exist_ok=True)
        ass_path = os.path.join(temp_dir, f"preview_text_layers_{int(time.time() * 1000)}.ass")
        source = (
            f"[Script Info]\nPlayResX: {int(width)}\nPlayResY: {int(height)}\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            + "\n".join(styles)
            + "\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            + "\n".join(events)
            + "\n"
        )
        with open(ass_path, "w", encoding="utf-8") as handle:
            handle.write(source)
        print(f"[Preview] Added {len(events)} TextLayer event(s) to {ass_path}")
        return ass_path

    def _build_fast_preview_text_images(self, text_layers, start_seconds, duration_seconds, width, height, temp_dir):
        """Render editor TEXT layers with the shared Qt renderer for Fast Preview."""
        if not text_layers:
            return []
        from app.layers.text_renderer import render_text_layer

        output_dir = os.path.join(temp_dir, "text_layer_images")
        os.makedirs(output_dir, exist_ok=True)
        result = []
        for index, layer in enumerate(text_layers):
            layer_start, layer_end = float(layer["start"]), float(layer["end"])
            clip_start = max(0.0, layer_start - start_seconds)
            clip_end = min(float(duration_seconds), layer_end - start_seconds)
            if clip_end <= clip_start:
                continue
            try:
                payload = dict(layer)
                payload["font_size"] = max(1, int(round(float(layer["font_size"]) * 0.85)))
                payload["padding_scale"] = 1.0
                rendered = render_text_layer(payload, int(width), int(height))
                path = os.path.join(output_dir, f"preview_text_layer_{index}_{int(time.time() * 1000)}.png")
                if not rendered.image.save(path, "PNG"):
                    raise RuntimeError("QImage could not save PNG")
                result.append({
                    "path": path,
                    "x": int(round(rendered.rect.left())),
                    "y": int(round(rendered.rect.top())),
                    "start": clip_start,
                    "end": clip_end,
                })
            except Exception as exc:
                print(f"[Preview] Could not render TextLayer {index} image: {exc}")
        return result

    @staticmethod
    def _format_duration_ms(duration_ms: int) -> str:
        total_seconds = max(0, int(round(float(duration_ms or 0) / 1000.0)))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    @staticmethod
    def _format_bytes(num_bytes: int) -> str:
        value = float(max(0, int(num_bytes or 0)))
        units = ["B", "KB", "MB", "GB", "TB"]
        unit_idx = 0
        while value >= 1024.0 and unit_idx < len(units) - 1:
            value /= 1024.0
            unit_idx += 1
        return f"{value:.1f} {units[unit_idx]}"

    def _probe_source_fps(self, video_path: str) -> str:
        ffprobe_candidates = [
            bin_path("ffmpeg", "ffprobe.exe"),
            bin_path("ffprobe.exe"),
            shutil.which("ffprobe"),
            shutil.which("ffprobe.exe"),
        ]
        ffprobe_path = ""
        for candidate in ffprobe_candidates:
            if candidate and os.path.isfile(candidate):
                ffprobe_path = candidate
                break
        if not ffprobe_path:
            return "Unknown"
        try:
            startupinfo = None
            creationflags = 0
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            result = subprocess.run(
                [
                    ffprobe_path,
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=r_frame_rate",
                    "-of",
                    "default=nw=1:nk=1",
                    video_path,
                ],
                capture_output=True,
                text=True,
                timeout=10,
                startupinfo=startupinfo,
                creationflags=creationflags,
                check=False,
            )
            raw = str(result.stdout or "").strip()
            if not raw:
                return "Unknown"
            if "/" in raw:
                num, den = raw.split("/", 1)
                fps = float(num) / max(1.0, float(den))
            else:
                fps = float(raw)
            return f"{fps:.2f}".rstrip("0").rstrip(".")
        except Exception:
            return "Unknown"

    def _video_has_audio_stream(self, video_path: str) -> bool:
        """Determine whether the source audio that subtitle-only export maps exists."""
        ffprobe_candidates = [
            bin_path("ffmpeg", "ffprobe.exe"), bin_path("ffprobe.exe"),
            shutil.which("ffprobe"), shutil.which("ffprobe.exe"),
        ]
        ffprobe_path = next((path for path in ffprobe_candidates if path and os.path.isfile(path)), "")
        if not ffprobe_path:
            # A selected/extracted source is a safer fallback than presenting
            # a misleading “No Audio” label when ffprobe is unavailable.
            return bool(getattr(self.gui, "last_extracted_audio", ""))
        try:
            startupinfo = None
            creationflags = 0
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            result = subprocess.run(
                [ffprobe_path, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index", "-of", "csv=p=0", video_path],
                capture_output=True, text=True, timeout=10,
                startupinfo=startupinfo, creationflags=creationflags,
                check=False,
            )
            return bool(str(result.stdout or "").strip())
        except Exception:
            return bool(getattr(self.gui, "last_extracted_audio", ""))

    def _export_voice_summary(self) -> str:
        """Return a compact voice label without exposing individual mappings."""
        default_voice = ""
        combo = getattr(self.gui, "free_voice_combo", None)
        if combo is not None:
            default_voice = str(combo.currentText() or "").strip()
        assignments = {}
        try:
            assignments = self.gui._speaker_voice_assignments()
        except Exception:
            pass
        speakers = {
            str(segment.get("speaker", "") or "").strip()
            for segment in list(getattr(self.gui, "current_translated_segments", None) or self.gui.get_active_segments() or [])
            if str(segment.get("speaker", "") or "").strip()
        }
        voices = set()
        for speaker in speakers:
            assigned = str((assignments.get(speaker, {}) or {}).get("voice", "") or "").strip()
            if assigned and assigned.lower() != "original":
                voices.add(assigned)
            elif default_voice:
                voices.add(default_voice)
        if not voices and default_voice:
            voices.add(default_voice)
        if len(voices) > 1:
            return f"Multi-speaker ({len(voices)} voices)"
        return next(iter(voices), "Selected voice")

    def _active_export_layer_summary(self) -> str:
        """Count only visible, exportable overlay layers from the live timeline."""
        timeline = getattr(getattr(self.gui, "timeline", None), "_timeline", None)
        if timeline is None:
            return "None"
        labels = {"blur": "Blur", "mask": "Mask", "text": "Text", "image": "Logo"}
        counts = {key: 0 for key in labels}
        for track in list(getattr(timeline, "tracks", []) or []):
            if bool(getattr(track, "muted", False)):
                continue
            track_type = str(getattr(getattr(track, "type", ""), "value", getattr(track, "type", ""))).lower()
            if track_type not in labels:
                continue
            for layer in list(getattr(track, "layers", []) or []):
                if bool(getattr(layer, "visible", True)):
                    counts[track_type] += 1
        parts = [f"{count} {labels[key]}" for key, count in counts.items() if count]
        return ", ".join(parts) if parts else "None"

    def _resolve_export_resolution_label(self, video_path: str, output_quality: str) -> str:
        try:
            from video_processor import get_video_dimensions

            src_w, src_h = get_video_dimensions(video_path)
        except Exception:
            src_w, src_h = 0, 0

        if not src_w or not src_h:
            return "Unknown"

        target_w, target_h = self._resolve_output_canvas_dimensions(video_path)
        if target_w and target_h:
            return f"{target_w}x{target_h}"

        key = str(output_quality or "source").strip().lower()
        if key in ("", "source", "same", "original", "auto"):
            return f"{src_w}x{src_h} (Source)"

        portrait = src_h > src_w
        if key in ("720", "720p", "hd"):
            base_w, base_h = (720, 1280) if portrait else (1280, 720)
        elif key in ("1080", "1080p", "fullhd", "fhd", "full hd", "full"):
            base_w, base_h = (1080, 1920) if portrait else (1920, 1080)
        elif key in ("1440", "1440p", "2k", "qhd"):
            base_w, base_h = (1440, 2560) if portrait else (2560, 1440)
        elif key in ("2160", "2160p", "4k", "uhd"):
            base_w, base_h = (2160, 3840) if portrait else (3840, 2160)
        else:
            return f"{src_w}x{src_h}"

        if src_w <= base_w and src_h <= base_h:
            return f"{src_w}x{src_h} (Source)"
        return f"{base_w}x{base_h}"

    def _resolve_output_canvas_dimensions(self, video_path: str):
        try:
            from video_processor import get_video_dimensions
            src_w, src_h = get_video_dimensions(video_path)
        except Exception:
            return None, None
        if not src_w or not src_h:
            return None, None

        output_quality = self.gui.get_output_quality_key()
        output_ratio = self.gui.get_output_ratio_key()
        ratio_map = {
            "16:9": (16, 9),
            "9:16": (9, 16),
            "1:1": (1, 1),
            "4:3": (4, 3),
        }
        ratio = ratio_map.get(str(output_ratio or "source").strip().lower())
        quality_key = str(output_quality or "source").strip().lower()

        if quality_key in ("", "source", "same", "original", "auto"):
            if not ratio:
                return None, None
            src_ratio = src_w / src_h
            target_ratio = ratio[0] / ratio[1]
            if abs(src_ratio - target_ratio) < 0.001:
                return None, None
            fit_scale = min(src_w / ratio[0], src_h / ratio[1])
            return (
                max(2, int((ratio[0] * fit_scale) // 2 * 2)),
                max(2, int((ratio[1] * fit_scale) // 2 * 2)),
            )

        if quality_key in ("720", "720p", "hd"):
            short_edge = 720
        elif quality_key in ("1080", "1080p", "fullhd", "fhd", "full hd", "full"):
            short_edge = 1080
        elif quality_key in ("1440", "1440p", "2k", "qhd"):
            short_edge = 1440
        elif quality_key in ("2160", "2160p", "4k", "uhd"):
            short_edge = 2160
        else:
            return None, None

        if ratio:
            scale = short_edge / min(ratio)
            target_w = max(2, int((ratio[0] * scale) // 2 * 2))
            target_h = max(2, int((ratio[1] * scale) // 2 * 2))
            if src_w <= target_w and src_h <= target_h:
                fit_scale = min(src_w / ratio[0], src_h / ratio[1])
                target_w = max(2, int((ratio[0] * fit_scale) // 2 * 2))
                target_h = max(2, int((ratio[1] * fit_scale) // 2 * 2))
            return target_w, target_h

        portrait = src_h > src_w
        target_w = short_edge if portrait else int(round(short_edge * 16 / 9))
        target_h = int(round(short_edge * 16 / 9)) if portrait else short_edge
        if src_w <= target_w and src_h <= target_h:
            return None, None
        return target_w, target_h

    def _confirm_export_summary(self, *, video_path: str, output_path: str, mode: str, audio_path: str):
        output_quality = self.gui.get_output_quality_key()
        output_fps = self.gui.get_output_fps_key()
        source_fps = self._probe_source_fps(video_path)
        duration_ms = 0
        try:
            duration_ms = int(getattr(self.gui.media_player, "duration", lambda: 0)() or 0)
        except Exception:
            duration_ms = int(getattr(self.gui.timeline, "duration", 0) or 0)

        mode_label = {
            "original": "Source video",
            "subtitle": "Subtitle only",
            "voice": "Voice only",
            "both": "Subtitle + voice",
        }.get(str(mode or "").strip().lower(), str(mode or "Unknown"))
        fps_label = f"{source_fps} FPS (Source)" if output_fps == "source" else f"{output_fps} FPS"
        canvas_label = self.gui.get_output_scale_mode_key().capitalize()
        focus_x, focus_y = self.gui.get_output_fill_focus()
        mode_key = str(mode or "").strip().lower()
        a1_volume = int(self.gui.audio_a1_volume_slider.value()) if hasattr(self.gui, "audio_a1_volume_slider") else 100
        a2_volume = int(self.gui.audio_a2_volume_slider.value()) if hasattr(self.gui, "audio_a2_volume_slider") else 100
        has_original_audio = self._video_has_audio_stream(video_path)
        if mode_key in {"subtitle", "original"}:
            audio_mode = "Original" if has_original_audio and a1_volume > 0 else "No Audio"
        elif mode_key == "voice":
            if not audio_path or (a1_volume <= 0 and a2_volume <= 0):
                audio_mode = "No Audio"
            elif a1_volume > 0 and a2_volume > 0:
                audio_mode = "Original + Dubbed"
            elif a1_volume > 0:
                audio_mode = "Original"
            else:
                audio_mode = "Dubbed"
        elif a1_volume <= 0 and a2_volume <= 0:
            audio_mode = "No Audio"
        elif a1_volume <= 0:
            audio_mode = "Dubbed"
        elif a2_volume <= 0:
            audio_mode = "Original"
        else:
            audio_mode = "Original + Dubbed"

        language_code = str(self.gui.get_target_language_code() if hasattr(self.gui, "get_target_language_code") else "").lower()
        language_label = {"vi": "Vietnamese", "en": "English"}.get(language_code, language_code.upper() or "Output language")
        quality_key = str(output_quality or "").strip().lower()
        quality_label = {
            "": "Source", "source": "Source", "same": "Source", "original": "Source", "auto": "Source",
            "720": "720p", "720p": "720p", "hd": "720p",
            "1080": "1080p", "1080p": "1080p", "fullhd": "1080p", "fhd": "1080p",
            "1440": "1440p", "1440p": "1440p", "2k": "1440p", "qhd": "1440p",
            "2160": "2160p", "2160p": "2160p", "4k": "2160p", "uhd": "2160p",
        }.get(quality_key, str(output_quality))
        ratio_key = str(self.gui.get_output_ratio_key() or "source").strip().lower()
        ratio_label = "Source" if ratio_key in {"", "source", "same", "original", "auto"} else ratio_key
        has_subtitles = mode_key in {"subtitle", "both"} and bool(
            getattr(self.gui, "current_translated_segments", None)
            or getattr(self.gui, "last_translated_srt_path", "")
        )
        filters_on = bool(self.gui.has_active_video_filters()) if hasattr(self.gui, "has_active_video_filters") else False
        export_preset = self.gui.get_export_preset() if hasattr(self.gui, "get_export_preset") else "balanced"
        preset_label = {"fast": "Fast", "balanced": "Balanced", "max": "Maximum quality"}.get(export_preset, str(export_preset))
        bitrate_kbps = self.gui.get_output_bitrate_kbps() if hasattr(self.gui, "get_output_bitrate_kbps") else 2000

        summary_lines = [
            f"Name: {os.path.basename(output_path)}",
            f"Folder: {os.path.dirname(output_path)}",
            f"Mode: {mode_label}",
            f"Duration: {self._format_duration_ms(duration_ms)}",
            "",
            "VIDEO",
            f"Resolution: {self._resolve_export_resolution_label(video_path, output_quality)}",
            f"Frame Rate: {fps_label}",
            f"Quality: {quality_label}",
            f"Ratio: {ratio_label}",
            f"Canvas: {canvas_label}",
            f"Framing: {int(round(focus_x * 100))}% x / {int(round(focus_y * 100))}% y" if self.gui.get_output_scale_mode_key() == "fill" else "Framing: Center",
            f"Video Filters: {'On' if filters_on else 'Off'}",
            f"Encoder Preset: {preset_label}",
            f"Target Bitrate: {int(bitrate_kbps)} kbps",
            "",
            "AUDIO & LANGUAGE",
            f"Language: {language_label}",
            f"Audio Mode: {audio_mode}",
        ]
        if mode_key in {"voice", "both"} and audio_mode != "No Audio":
            processing = str(self.gui.get_audio_handling_mode() if hasattr(self.gui, "get_audio_handling_mode") else "").strip().lower()
            processing_label = {"fast": "Fast", "clean": "Cleaner"}.get(processing, processing.capitalize() or "Standard")
            summary_lines.append(f"Audio Processing: {processing_label}")
        if mode_key in {"voice", "both"} and "Dubbed" in audio_mode:
            summary_lines.append(f"Voice: {self._export_voice_summary()}")
        is_already_recapped = bool(
            "_recap" in os.path.basename(video_path).lower()
            or (hasattr(self.gui, "last_recap_video_path") and self.gui.last_recap_video_path and os.path.normcase(os.path.abspath(video_path)) == os.path.normcase(os.path.abspath(self.gui.last_recap_video_path)))
        )
        initial_recap = bool(
            (hasattr(self.gui, "is_auto_recap_enabled") and self.gui.is_auto_recap_enabled())
            or (hasattr(self.gui, "anti_duplicate_cb") and self.gui.anti_duplicate_cb.isChecked())
        )
        recap_desc = (
            "Đã áp dụng sẵn trong video nguồn"
            if is_already_recapped
            else ("Bật (1-Pass: Lật gương + Zoom YouTube + Dịch cao độ)" if initial_recap else "Tắt")
        )

        summary_lines.extend([
            "",
            "CONTENT",
            f"Subtitles: {'Yes' if has_subtitles else 'No'}",
            f"Layers: {self._active_export_layer_summary()}",
            "",
            "CHỐNG TRÙNG LẶP / RECAP",
            f"Auto Recap: {recap_desc}",
        ])

        from app.anti_duplicate import AntiDuplicateSettings

        # Load existing custom settings from memory or project state if available
        existing_ad_settings = getattr(self.gui, "_anti_duplicate_settings", None)
        if existing_ad_settings is None and hasattr(self.gui, "current_project_state") and self.gui.current_project_state:
            ps = self.gui.current_project_state
            saved_dict = None
            if hasattr(ps, "get_setting"):
                saved_dict = ps.get_setting("anti_duplicate_custom_settings", None)
            elif hasattr(ps, "settings") and isinstance(getattr(ps, "settings", None), dict):
                saved_dict = ps.settings.get("anti_duplicate_custom_settings", None)
            if saved_dict and isinstance(saved_dict, dict):
                existing_ad_settings = AntiDuplicateSettings.from_dict(saved_dict)

        try:
            from ui.dialogs.export_confirm_dialog import ExportConfirmDialog
            dialog = ExportConfirmDialog(
                summary_lines,
                is_already_recapped=is_already_recapped,
                initial_recap=initial_recap,
                ad_settings=existing_ad_settings,
                parent=self.gui,
            )
            dialog.exec()
            confirmed = (dialog.result() == QDialog.Accepted)
            wants_recap, ad_settings = dialog.get_result()
            self.gui._anti_duplicate_settings = ad_settings
            if hasattr(self.gui, "current_project_state") and self.gui.current_project_state:
                ps = self.gui.current_project_state
                if hasattr(ps, "set_setting"):
                    ps.set_setting("anti_duplicate_custom_settings", ad_settings.to_dict())
                elif hasattr(ps, "settings") and isinstance(getattr(ps, "settings", None), dict):
                    ps.settings["anti_duplicate_custom_settings"] = ad_settings.to_dict()
            return confirmed, wants_recap, ad_settings
        except Exception as exc:
            # Safe fallback if UI fails to initialize
            print(f"[Export] ExportConfirmDialog fallback: {exc}")
            box = QMessageBox(self.gui)
            box.setIcon(QMessageBox.Information)
            box.setWindowTitle("Export Summary")
            box.setText("Review export details before starting.")
            box.setInformativeText("\n".join(summary_lines))
            recap_cb = QCheckBox("✨ Bật Chống trùng lặp (Auto Recap 1-Pass)", box)
            recap_cb.setChecked(initial_recap if not is_already_recapped else False)
            recap_cb.setEnabled(not is_already_recapped)
            box.setCheckBox(recap_cb)
            start_btn = box.addButton("Start Export", QMessageBox.AcceptRole)
            box.addButton("Cancel", QMessageBox.RejectRole)
            box.exec()
            confirmed = (box.clickedButton() is start_btn)
            wants_recap = bool(recap_cb.isChecked()) if not is_already_recapped else False
            return confirmed, wants_recap, existing_ad_settings

    def _resolve_export_video_path(self, *, prefer_recap: bool = True) -> str:
        """Resolve the active video path for preview and export.

        When prefer_recap=True and Auto Recap is active with a rendered recap video,
        returns the recap video path so timeline overlays (logos, text, blur) and
        previews are rendered on top of the recapped media.
        """
        if prefer_recap and hasattr(self.gui, "is_auto_recap_enabled") and self.gui.is_auto_recap_enabled():
            recap_path = str(getattr(self.gui, "last_recap_video_path", "") or "").strip()
            if recap_path and os.path.isfile(recap_path):
                return os.path.abspath(recap_path)
        canonical = getattr(self.gui, "resolve_canonical_video_path", None)
        if callable(canonical):
            resolved = canonical()
            if resolved:
                return resolved
        candidates = [str(getattr(self.gui, "_current_video_path", "") or "").strip()]
        state = getattr(self.gui, "current_project_state", None)
        if state is not None:
            candidates.append(str(getattr(state, "input_video", "") or "").strip())
        try:
            candidates.extend(
                str(item.get("source", "") or "").strip()
                for item in self.gui.get_timeline_video_clips(existing_only=True)
            )
        except Exception:
            pass
        editor = getattr(self.gui, "video_path_edit", None)
        if editor is not None:
            candidates.append(str(editor.text() or "").strip())
        candidates.append(str(getattr(self.gui, "last_video_path", "") or "").strip())
        seen = set()
        for candidate in candidates:
            if not candidate:
                continue
            path = os.path.abspath(candidate)
            key = os.path.normcase(path)
            if key in seen:
                continue
            seen.add(key)
            if os.path.isfile(path):
                return path
        return ""

    def _normalize_export_timeline_clips(
        self,
        clips: list[dict],
        base_video_path: str,
        is_recap_active: bool,
    ) -> list[dict]:
        """Normalize timeline clips for final export.

        When Auto Recap is active, any clips referencing the raw canonical source
        are updated to point to the rendered recap video. Furthermore, if the
        sequence of clips forms an uninterrupted, contiguous playback of base_video_path
        (e.g., unmodified auto recap shots), collapses them into a single continuous
        clip so FFmpeg can render in a single input pass rather than opening dozens
        of duplicated file handles.
        """
        if not clips:
            return []
        norm_base = os.path.normcase(os.path.abspath(base_video_path)) if base_video_path else ""
        canonical_src = ""
        if hasattr(self.gui, "resolve_canonical_video_path"):
            try:
                resolved = self.gui.resolve_canonical_video_path()
                if resolved:
                    canonical_src = os.path.normcase(os.path.abspath(resolved))
            except Exception:
                pass

        updated_clips: list[dict] = []
        for c in clips:
            c_copy = dict(c)
            src_str = str(c_copy.get("source", "") or "")
            src_norm = os.path.normcase(os.path.abspath(src_str)) if src_str else ""
            if is_recap_active and base_video_path and canonical_src and src_norm == canonical_src:
                c_copy["source"] = base_video_path
            updated_clips.append(c_copy)

        # Defensive sanitization: if sequential clips have end times that overlap
        # past the subsequent clip's start (e.g. legacy timeline corruption),
        # clamp each clip's end to the next clip's start so total duration remains exact.
        if len(updated_clips) > 1:
            for i in range(len(updated_clips) - 1):
                cur_st = float(updated_clips[i].get("start", 0.0) or 0.0)
                cur_end = float(updated_clips[i].get("end", 0.0) or 0.0)
                nxt_st = float(updated_clips[i + 1].get("start", 0.0) or 0.0)
                if nxt_st > cur_st and cur_end > nxt_st:
                    updated_clips[i]["end"] = nxt_st
                    updated_clips[i]["source_duration"] = nxt_st - cur_st

        if len(updated_clips) > 1 and norm_base and os.path.isfile(base_video_path):
            expected_pos = 0.0
            is_contiguous = True
            for i, c in enumerate(updated_clips):
                c_src = os.path.normcase(os.path.abspath(str(c.get("source", "") or "")))
                if c_src != norm_base:
                    is_contiguous = False
                    break
                if abs(float(c.get("speed", 1.0) or 1.0) - 1.0) > 0.001:
                    is_contiguous = False
                    break
                if bool(c.get("muted", False)):
                    is_contiguous = False
                    break
                if abs(float(c.get("volume", 1.0) or 1.0) - 1.0) > 0.001:
                    is_contiguous = False
                    break
                start = float(c.get("start", 0.0) or 0.0)
                source_start = float(c.get("source_start", 0.0) or 0.0)
                if i == 0 and (abs(start) > 0.05 or abs(source_start) > 0.05):
                    is_contiguous = False
                    break
                if abs(start - expected_pos) > 0.05 or abs(source_start - expected_pos) > 0.05:
                    is_contiguous = False
                    break
                dur = float(c.get("source_duration", 0.0) or (float(c.get("end", 0.0) or 0.0) - start))
                if dur <= 0:
                    is_contiguous = False
                    break
                expected_pos += dur

            if is_contiguous:
                return [{
                    "source": base_video_path,
                    "source_start": 0.0,
                    "source_duration": expected_pos,
                    "start": 0.0,
                    "end": expected_pos,
                    "speed": 1.0,
                    "volume": 1.0,
                    "muted": False,
                }]

        return updated_clips

    def _check_audio_freshness(self, audio_path: str) -> bool:
        """Reject missing or stale generated audio before export."""
        path = os.path.abspath(str(audio_path or "").strip()) if audio_path else ""
        if not path or not os.path.isfile(path):
            return False
        if bool(getattr(self.gui, "_voice_track_partial", False)):
            QMessageBox.warning(
                self.gui,
                "Voiceover Out of Date",
                "Subtitle timing or text changed after voice generation. Generate the voiceover again before exporting.",
            )
            return False
        state = getattr(self.gui, "current_project_state", None)
        expected = str(getattr(state, "settings", {}).get("voice_signature", "") or "") if state else ""
        if not expected or not hasattr(self.gui, "build_current_voice_signature"):
            return True
        try:
            actual = str(
                self.gui.build_current_voice_signature(
                    segments=self.gui._get_voiceover_segments(),
                    background_path=self.gui.resolve_background_audio_path(),
                ) or ""
            )
        except Exception:
            actual = ""
        if actual and actual != expected:
            QMessageBox.warning(
                self.gui,
                "Voiceover Out of Date",
                "Voice settings or subtitles changed after voice generation. Generate the voiceover again before exporting.",
            )
            return False
        return True
    
    def _regenerate_mixed_audio_with_current_volumes(self) -> str:
        """Regenerate the mixed audio file using current volume settings from Audio tab.

        Returns the path to the newly generated mixed audio file, or empty string if failed.
        """
        # Read the live controls at the instant Export/Preview is requested.
        # Do not reuse ``mixed_vi`` here: it was authored with an older pair of
        # gains and is therefore not a valid source after either slider moves.
        original_volume = int(self.gui.audio_a1_volume_slider.value()) if hasattr(self.gui, 'audio_a1_volume_slider') else 100
        dub_volume = int(self.gui.audio_a2_volume_slider.value()) if hasattr(self.gui, 'audio_a2_volume_slider') else 100

        a1_muted = False
        if hasattr(self.gui, "_is_audio_track_muted"):
            a1_muted = bool(self.gui._is_audio_track_muted("A1 Audio") or self.gui._is_audio_track_muted("A1"))
        if not a1_muted and hasattr(self.gui, "_mute_original"):
            a1_muted = bool(self.gui._mute_original)
        if a1_muted:
            original_volume = 0

        a2_muted = False
        if hasattr(self.gui, "_is_audio_track_muted"):
            a2_muted = bool(self.gui._is_audio_track_muted("A2 Dub") or self.gui._is_audio_track_muted("A2"))
        if not a2_muted and hasattr(self.gui, "_mute_dubbed"):
            a2_muted = bool(self.gui._mute_dubbed)
        if a2_muted:
            dub_volume = 0

        # Resolve voice (dub) track
        voice_path = ""
        if hasattr(self.gui, 'last_voice_vi_path') and self.gui.last_voice_vi_path:
            voice_path = self.gui.last_voice_vi_path
            if not os.path.exists(voice_path):
                voice_path = ""

        # Resolve background / original audio from video or extracted file
        bg_path = self.gui._resolve_preview_background_audio_path() if hasattr(self.gui, '_resolve_preview_background_audio_path') else ""

        mix_dir = (
            self.gui.get_project_temp_dir("audio_mix")
            if hasattr(self.gui, "get_project_temp_dir")
            else os.path.join(self.gui.workspace_root, "temp", "audio_mix")
        )
        os.makedirs(mix_dir, exist_ok=True)

        if not bg_path or not os.path.exists(bg_path):
            # Try to extract audio from the original video on-the-fly
            video_path = self._resolve_export_video_path()
            if video_path and os.path.exists(video_path) and original_volume > 0:
                try:
                    video_stat = os.stat(video_path)
                    source_key = hashlib.sha1(
                        f"{os.path.abspath(video_path)}|{video_stat.st_size}|{video_stat.st_mtime_ns}".encode("utf-8")
                    ).hexdigest()[:16]
                    extracted_path = os.path.join(mix_dir, f"original_{source_key}.wav")
                    from audio_mixer import extract_audio_from_video
                    if not os.path.exists(extracted_path) or os.path.getsize(extracted_path) <= 44:
                        extract_audio_from_video(video_path, extracted_path)
                    if os.path.exists(extracted_path):
                        bg_path = extracted_path
                        print(f"[Export] Extracted original audio from video: {extracted_path}")
                except Exception as e:
                    print(f"[Export] Could not extract original audio: {e}")

        signature_payload = {
            "original": self._file_signature(bg_path),
            "dub": self._file_signature(voice_path),
            "original_volume": int(original_volume),
            "dub_volume": int(dub_volume),
        }
        mix_key = hashlib.sha1(
            json.dumps(signature_payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
        ).hexdigest()[:16]
        output_path = os.path.join(mix_dir, f"export_mix_{mix_key}.wav")
        print(
            f"[Export] Audio mix snapshot: A1 Original={original_volume}%, "
            f"A2 Dub={dub_volume}%, cache={os.path.basename(output_path)}"
        )

        # A completed file with this content-addressed name has exactly the
        # requested sources and gains. It is safe to reuse and avoids remixing
        # a multi-hour project when the user exports again unchanged.
        if os.path.exists(output_path) and os.path.getsize(output_path) > 44:
            return output_path

        # --- Case 0: Both Muted or 0 volume ---
        if original_volume <= 0 and dub_volume <= 0:
            print("[Export] Both original and dub tracks are muted/zero volume; outputting silent audio")
            try:
                from audio_mixer import ffprobe_wav_duration
                ref = voice_path if (voice_path and os.path.exists(voice_path)) else bg_path
                dur = ffprobe_wav_duration(ref) if (ref and os.path.exists(ref)) else 1.0
                if dur <= 0.0:
                    dur = 1.0
                from pydub import AudioSegment
                silence = AudioSegment.silent(duration=int(dur * 1000), frame_rate=16000)
                silence.export(output_path, format="wav")
                return output_path
            except Exception as e:
                print(f"[Export] Failed to generate silence: {e}")
                return ""

        # --- Case 1: Original Only (dub_volume == 0) ---
        if dub_volume <= 0 and original_volume > 0:
            if bg_path and os.path.exists(bg_path):
                if original_volume == 100:
                    print(f"[Export] Dub volume=0, using original audio only (100%): {bg_path}")
                    return bg_path
                try:
                    original_gain_db = self.gui._percent_to_db(original_volume) if hasattr(self.gui, '_percent_to_db') else 0.0
                    from audio_mixer import _ffmpeg_path
                    ffmpeg = _ffmpeg_path()
                    command = [
                        ffmpeg, "-y", "-loglevel", "error", "-i", bg_path,
                        "-af", f"volume={original_gain_db:.2f}dB",
                        "-c:a", "pcm_s16le", "-ar", "16000", "-ac", "1", output_path
                    ]
                    import subprocess
                    from runtime_paths import subprocess_text_kwargs
                    subprocess.run(command, check=True, **subprocess_text_kwargs())
                    print(f"[Export] Dub volume=0, scaled original audio to {original_volume}%: {output_path}")
                    return output_path
                except Exception as e:
                    print(f"[Export] Failed to scale original audio: {e}")
                    return ""
            print("[Export] Dub volume=0 but no original audio found, returning empty")
            return ""

        # --- Case 2: Dub Only (original_volume == 0) ---
        if original_volume <= 0 and dub_volume > 0:
            if voice_path and os.path.exists(voice_path):
                if dub_volume == 100:
                    print(f"[Export] Original volume=0, using voice only (100%): {voice_path}")
                    return voice_path
                try:
                    dub_gain_db = self.gui._percent_to_db(dub_volume) if hasattr(self.gui, '_percent_to_db') else 0.0
                    from audio_mixer import _ffmpeg_path
                    ffmpeg = _ffmpeg_path()
                    command = [
                        ffmpeg, "-y", "-loglevel", "error", "-i", voice_path,
                        "-af", f"volume={dub_gain_db:.2f}dB",
                        "-c:a", "pcm_s16le", "-ar", "16000", "-ac", "1", output_path
                    ]
                    import subprocess
                    from runtime_paths import subprocess_text_kwargs
                    subprocess.run(command, check=True, **subprocess_text_kwargs())
                    print(f"[Export] Original volume=0, scaled dub audio to {dub_volume}%: {output_path}")
                    return output_path
                except Exception as e:
                    print(f"[Export] Failed to scale dubbed audio: {e}")
                    return ""
            print("[Export] Original volume=0 but no voice file found, returning empty")
            return ""

        # --- Case 3: No voice track generated yet ---
        if not voice_path:
            if bg_path and os.path.exists(bg_path):
                if original_volume == 100:
                    print(f"[Export] No voice file, using original audio only: {bg_path}")
                    return bg_path
                print("[Export] No voice file is available for the requested two-track mix")
                return ""
            print("[Export] No voice file and no original audio, returning empty")
            return ""

        # --- Case 4: Mix both tracks ---
        if not bg_path or not os.path.exists(bg_path):
            # Returning the raw voice here used to silently ignore A1 and A2
            # slider values. A visibly wrong export is worse than a clear
            # failure, so require the requested source to be available.
            print("[Export] No original audio available for the requested two-track mix")
            return ""

        try:
            from audio_mixer import mix_original_with_dub
            original_gain_db = self.gui._percent_to_db(original_volume) if hasattr(self.gui, '_percent_to_db') else 0.0
            dub_gain_db = self.gui._percent_to_db(dub_volume) if hasattr(self.gui, '_percent_to_db') else 0.0
            mix_original_with_dub(
                original_wav_path=bg_path,
                dub_wav_path=voice_path,
                output_wav_path=output_path,
                original_gain_db=original_gain_db,
                dub_gain_db=dub_gain_db,
            )
            print(f"[Export] Mixed audio created: {output_path}")
            return output_path
        except Exception as e:
            print(f"[Export] Failed to regenerate mixed audio: {e}")
            import traceback
            traceback.print_exc()
            return ""

    def _prepare_current_export_srt(self) -> str:
        segments = list(self.gui.get_active_segments() or [])
        saved_candidates = [
            str(getattr(self.gui, "last_translated_srt_path", "") or "").strip(),
            str(getattr(self.gui, "processed_artifacts", {}).get("srt_translated", "") or "").strip(),
        ]
        project_state = getattr(self.gui, "current_project_state", None)
        if project_state is not None:
            artifacts = getattr(project_state, "artifacts", {}) or {}
            saved_candidates.extend(
                [
                    str(artifacts.get("subtitle_translated_srt", "") or "").strip(),
                    str(artifacts.get("srt_translated", "") or "").strip(),
                ]
            )
        existing_path = next((path for path in saved_candidates if path and os.path.exists(path)), "")
        if not segments:
            return existing_path

        out_path = existing_path or str(self.gui.last_translated_srt_path or "").strip()
        if not out_path:
            video_path = self._resolve_export_video_path()
            video_name = os.path.splitext(os.path.basename(video_path or "subtitle"))[0]
            # Normal video export must not place subtitle sidecars beside the
            # chosen video. Keep this generated SRT in the project export
            # workspace; explicit subtitle export remains available through
            # the dedicated subtitle download action.
            out_path = self.gui.get_project_temp_path(
                "export", f"{video_name}_vi.srt", create_parent=True
            )

        from subtitle_builder import generate_srt

        generate_srt(segments, out_path)
        self.gui.last_translated_srt_path = out_path
        self.gui.processed_artifacts["srt_translated"] = out_path
        self.gui.persist_translation_project_data(self.gui.current_translated_segments, out_path)
        return out_path

    def _file_signature(self, path: str) -> dict:
        if not path or not os.path.exists(path):
            return {"path": "", "size": 0, "mtime_ns": 0}
        stat = os.stat(path)
        return {
            "path": os.path.abspath(path),
            "size": int(stat.st_size),
            "mtime_ns": int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))),
        }

    def _text_file_hash(self, path: str) -> str:
        if not path or not os.path.exists(path):
            return ""
        hasher = hashlib.sha1()
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(65536)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()

    def _build_styled_preview_signature(self, *, video_path: str, audio_path: str, mode: str, srt_path: str, subtitle_style: dict, mask_regions=None, blur_regions=None, logo_layers=None, text_layers=None) -> str:
        payload = {
            "kind": "styled_preview_v2",
            "mode": mode,
            "video": self._file_signature(video_path),
            "audio": self._file_signature(audio_path),
            "original_audio_gain_db": self._original_audio_gain_db_for_render(mode),
            "subtitle_path": os.path.abspath(srt_path) if srt_path and os.path.exists(srt_path) else "",
            "subtitle_hash": self._text_file_hash(srt_path),
            "subtitle_style": subtitle_style or {},
            "output_quality": self.gui.get_output_quality_key(),
            "output_ratio": self.gui.get_output_ratio_key(),
            "output_scale_mode": self.gui.get_output_scale_mode_key(),
            "output_fill_focus": self.gui.get_output_fill_focus(),
            "output_fps": self.gui.get_output_fps_key(),
            "video_filter": self.gui.get_video_filter_state() if hasattr(self.gui, "get_video_filter_state") else {},
            "mask_regions": mask_regions or [],
            "blur_regions": blur_regions or [],
            "logo_layers": logo_layers or [],
            "text_layers": text_layers or [],
        }
        return hashlib.sha1(json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")).hexdigest()

    def _effective_render_mode_without_tts(self, requested_mode: str) -> str:
        """Allow a translated-subtitle export when voice generation was skipped.

        The historical output mode can still be ``both``.  If there is no
        generated or explicitly selected audio, requiring it would block a
        perfectly valid subtitle-only export.  Never override a real voice
        track: users who generated one retain their requested voice/both mode.
        """
        mode = str(requested_mode or "both").strip().lower()
        if mode not in {"voice", "both"}:
            return mode
        has_translated_subtitles = bool(
            getattr(self.gui, "current_translated_segments", None)
            or str(self.gui.translated_text.toPlainText() if hasattr(self.gui, "translated_text") else "").strip()
            or (
                getattr(self.gui, "last_translated_srt_path", "")
                and os.path.exists(str(self.gui.last_translated_srt_path))
            )
        )
        project_state = getattr(self.gui, "current_project_state", None)
        if has_translated_subtitles and bool(
            project_state and project_state.settings.get("tts_skipped", False)
        ):
            self.gui.log("[Export] TTS was skipped; exporting translated subtitles with original audio.")
            return "subtitle"
        audio_path = self.gui.resolve_selected_audio_path()
        if has_translated_subtitles and not (audio_path and os.path.exists(audio_path)):
            self.gui.log("[Export] No TTS audio selected; exporting translated subtitles with original audio.")
            return "subtitle"
        return mode

    def _original_audio_gain_db_for_render(self, mode: str) -> float:
        """Return A1 gain for render modes that retain the source audio."""
        if str(mode or "").strip().lower() not in {"original", "subtitle"}:
            return 0.0
        try:
            a1_muted = False
            if hasattr(self.gui, "_is_audio_track_muted"):
                a1_muted = bool(self.gui._is_audio_track_muted("A1 Audio") or self.gui._is_audio_track_muted("A1"))
            if not a1_muted and hasattr(self.gui, "_mute_original"):
                a1_muted = bool(self.gui._mute_original)
            if a1_muted:
                return -60.0
            percent = int(self.gui.audio_a1_volume_slider.value())
            if percent <= 0:
                return -60.0
            return float(self.gui._percent_to_db(percent))
        except Exception:
            return 0.0

    def export_final_video(self, *, automatic: bool = False):
        video_path = self._resolve_export_video_path()
        if not video_path:
            QMessageBox.warning(self.gui, "Error", "Please choose a video first.")
            return

        # Auto Edit Recap Base Video Preparation
        is_recap_active = bool(
            (hasattr(self.gui, "is_auto_recap_enabled") and self.gui.is_auto_recap_enabled())
            or (hasattr(self.gui, "anti_duplicate_cb") and self.gui.anti_duplicate_cb.isChecked())
        )
        canonical_src = (
            self.gui.resolve_canonical_video_path()
            if hasattr(self.gui, "resolve_canonical_video_path")
            else video_path
        )
        recap_path = str(getattr(self.gui, "last_recap_video_path", "") or "").strip()

        # If a recap video was already generated on disk (e.g. via Generate button), use it.
        # Otherwise, the export pipeline will apply the Auto Recap filters directly in 1-Pass!
        if recap_path and os.path.isfile(recap_path):
            video_path = recap_path

        has_translated_content = bool(
            getattr(self.gui, "current_translated_segments", None)
            or (hasattr(self.gui, "get_active_segments") and self.gui.get_active_segments())
            or str(self.gui.translated_text.toPlainText() if hasattr(self.gui, "translated_text") else "").strip()
            or (
                getattr(self.gui, "last_translated_srt_path", "")
                and os.path.exists(str(getattr(self.gui, "last_translated_srt_path", "")))
            )
        )
        configured_mode = self.gui.get_output_mode_key()
        selected_audio_path = self.gui.resolve_selected_audio_path()
        has_selected_voice = bool(selected_audio_path and os.path.exists(selected_audio_path))
        # Do not make a source video unexportable just because the optional
        # translation and TTS stages have not been run yet.
        if not has_translated_content and not has_selected_voice:
            mode = "original"
        elif configured_mode == "subtitle":
            mode = "subtitle" if has_translated_content else "original"
        elif configured_mode == "voice":
            mode = "voice" if has_selected_voice else "subtitle"
        elif has_translated_content and has_selected_voice:
            mode = "both"
        elif has_translated_content:
            mode = "subtitle"
        else:
            mode = "voice"
        if mode == "original":
            self.gui.log("[Export] No translated subtitles or dubbed audio yet; exporting a source-video copy.")
        original_audio_gain_db = self._original_audio_gain_db_for_render(mode)
        video_name = os.path.splitext(os.path.basename(video_path))[0]
        translated_srt_path = self.gui.last_translated_srt_path
        translated_ass_path = self.gui.live_preview_ass_path
        
        # For voice/both modes, regenerate mixed audio with current volume settings
        chosen_audio = ""
        if mode in ("voice", "both"):
            chosen_audio = self._regenerate_mixed_audio_with_current_volumes()
        else:
            chosen_audio = self.gui.resolve_selected_audio_path()

        # Check if audio needs regeneration due to changed settings
        if mode in ("voice", "both") and chosen_audio:
            if not self._check_audio_freshness(chosen_audio):
                return

        # 3-Tier QA Gate Validation
        segments_for_qa = getattr(self.gui, "current_translated_segments", None) or getattr(self.gui, "current_segments", None)
        if segments_for_qa and mode in ("subtitle", "both", "voice"):
            from services.subtitle_exchange_service import SubtitleExchangeService
            qa_res = SubtitleExchangeService.evaluate_3tier_qa(
                segments_for_qa,
                source_language=self.gui.get_source_language_code() if hasattr(self.gui, "get_source_language_code") else "auto",
                target_language=self.gui.get_target_language_code() if hasattr(self.gui, "get_target_language_code") else "vi",
            )
            if qa_res.get("status") == "critical":
                critical_msg = "\n".join(f"• {issue}" for issue in qa_res.get("critical_issues", [])[:5])
                QMessageBox.critical(
                    self.gui,
                    "Export Blocked (Critical QA Errors)",
                    f"Export cannot proceed due to critical subtitle issues:\n\n{critical_msg}\n\nPlease fix these cues in the editor before exporting.",
                )
                return
            elif qa_res.get("status") == "warning":
                warning_count = len(qa_res.get("warning_issues", []))
                self.gui.log(f"[QA Warning] {warning_count} potential issue(s) detected. Continuing export...")

        if mode in ("subtitle", "both"):
            translated_srt_path = self._prepare_current_export_srt()
            # Refresh once, then export the exact ASS that MPV is currently
            # displaying. This prevents a second, slightly different ASS
            # generation pass from changing custom anchors/margins after a
            # Ratio or Canvas setting is selected.
            try:
                self.gui.sync_live_subtitle_preview()
                active_segments = self.gui.get_active_segments()
                snapshot = self.gui._build_live_subtitle_ass_snapshot(active_segments)
                translated_ass_path = self.gui._write_subtitle_ass_from_snapshot(
                    snapshot, translated_srt_path
                )
            except Exception as exc:
                self.gui.log(f"[Export] Could not refresh live subtitle ASS: {exc}")
                translated_ass_path = ""

        if mode in ("subtitle", "both") and (not translated_srt_path or not os.path.exists(translated_srt_path)):
            QMessageBox.warning(self.gui, "Error", "Translated subtitle file not found. Translate or import an SRT first.")
            return

        if mode in ("voice", "both") and (not chosen_audio or not os.path.exists(chosen_audio)):
            QMessageBox.warning(
                self.gui,
                "Error",
                "Selected audio source is not ready. Generate voice/mix first, or switch to 'Use existing mixed audio' and choose a valid file.",
            )
            return

        default_dir = self.gui.final_output_folder_edit.text().strip() or os.path.dirname(video_path)
        base_title = video_name
        if is_recap_active and base_title.endswith("_recap"):
            base_title = base_title[:-6]
        recap_tag = "_recap" if is_recap_active else ""

        if mode == "original":
            suggested_name = f"{base_title}{recap_tag}_final.mp4"
        elif mode == "subtitle":
            suggested_name = f"{base_title}{recap_tag}_sub_vi.mp4"
        elif mode == "voice":
            suggested_name = f"{base_title}{recap_tag}_voice_vi.mp4"
        else:
            suggested_name = f"{base_title}{recap_tag}_final_vi.mp4"

        default_path = os.path.join(default_dir, suggested_name)
        if automatic:
            output_path = default_path
        else:
            output_path, _ = QFileDialog.getSaveFileName(
                self.gui,
                "Export Final Video",
                default_path,
                "Video Files (*.mp4)",
            )
        if not output_path:
            return
        if not output_path.lower().endswith(".mp4"):
            output_path += ".mp4"

        chosen_dir = os.path.dirname(output_path)
        if chosen_dir:
            os.makedirs(chosen_dir, exist_ok=True)
            self.gui.final_output_folder_edit.setText(chosen_dir)

        wants_recap = is_recap_active
        custom_ad_settings = getattr(self.gui, "_anti_duplicate_settings", None)
        if not automatic:
            confirm_res = self._confirm_export_summary(
                video_path=video_path,
                output_path=output_path,
                mode=mode,
                audio_path=chosen_audio,
            )
            if isinstance(confirm_res, tuple) and len(confirm_res) == 3:
                confirmed, wants_recap, custom_ad_settings = confirm_res
            else:
                confirmed, wants_recap = confirm_res
            if not confirmed:
                return

        # Update GUI controls to reflect user's selection
        if hasattr(self.gui, "anti_duplicate_cb"):
            self.gui.anti_duplicate_cb.setChecked(wants_recap)
        if hasattr(self.gui, "auto_recap_cb"):
            self.gui.auto_recap_cb.setChecked(wants_recap)

        # Check if an export is already running — guard against deleted C++ object
        if hasattr(self.gui, 'export_thread') and self.gui.export_thread is not None:
            try:
                if self.gui.export_thread.isRunning():
                    self.gui.log("[Export] Export already running, ignoring request")
                    return
            except RuntimeError:
                # C++ object was already deleted by Qt; safe to proceed
                self.gui.export_thread = None

        # Flush the coalesced editor transaction before the worker reads the
        # project file. This guarantees that a Text/Blur value changed just
        # before clicking Export is rendered with the same state as preview.
        if hasattr(self.gui, "_flush_pending_timeline_persist"):
            self.gui._flush_pending_timeline_persist()
        elif hasattr(self.gui, "persist_current_timeline_project_data"):
            self.gui.persist_current_timeline_project_data()

        self.gui.export_btn.setEnabled(False)
        self.gui.export_btn.setText("Exporting...")
        self.gui.progress_bar.setValue(96)
        self.gui.update_project_step("export", "running")
        self.gui._export_progress_messages = ["Preparing final export..."]
        self.gui.on_export_progress(5, "Preparing final export...")

        project_state_path = self.gui.project_service.project_file(self.gui.current_project_state.project_root) if self.gui.current_project_state else ""
        fill_focus_x, fill_focus_y = self.gui.get_output_fill_focus()
        
        is_already_recapped = bool(
            "_recap" in os.path.basename(video_path).lower()
            or (recap_path and os.path.isfile(recap_path) and os.path.normcase(os.path.abspath(video_path)) == os.path.normcase(os.path.abspath(recap_path)))
        )
        anti_dup = bool(wants_recap and not is_already_recapped)

        raw_timeline_clips = (
            self.gui.get_timeline_video_clips(existing_only=True)
            if hasattr(self.gui, "get_timeline_video_clips") else []
        )
        timeline_clips = self._normalize_export_timeline_clips(
            raw_timeline_clips,
            base_video_path=video_path,
            is_recap_active=(is_already_recapped or wants_recap),
        )

        self.gui.export_thread = FinalExportWorker(
            workspace_root=self.gui.workspace_root,
            video_path=video_path,
            output_path=output_path,
            mode=mode,
            srt_path=translated_srt_path,
            ass_path=translated_ass_path,
            audio_path=chosen_audio,
            subtitle_style=self.gui.get_subtitle_export_style(segments=self.gui.get_active_segments()),
            output_quality=self.gui.get_output_quality_key(),
            output_fps=self.gui.get_output_fps_key(),
            output_ratio=self.gui.get_output_ratio_key(),
            output_scale_mode=self.gui.get_output_scale_mode_key(),
            output_fill_focus_x=fill_focus_x,
            output_fill_focus_y=fill_focus_y,
            video_filter_state=self.gui.get_video_filter_state() if hasattr(self.gui, "get_video_filter_state") else {},
            original_audio_gain_db=original_audio_gain_db,
            project_state_path=project_state_path,
            project_temp_dir=self.gui.get_project_temp_dir("export"),
            timeline_clips=timeline_clips,
            export_preset=self.gui.get_export_preset(),
            video_bitrate_kbps=self.gui.get_output_bitrate_kbps(),
            anti_duplicate_enabled=anti_dup,
            anti_duplicate_settings=custom_ad_settings if anti_dup else None,
        )
        self.gui.export_thread.progress.connect(self.gui.on_export_progress)
        self.gui.export_thread.finished.connect(self.gui.on_export_finished)
        # Do NOT use deleteLater() here — it destroys the C++ object while
        # self.gui.export_thread still holds the Python reference, causing
        # "Internal C++ object already deleted" on the next Export click.
        # Instead, clear the reference once the thread is truly done.
        self.gui.export_thread.finished.connect(self._on_export_thread_done)
        self.gui.export_thread.start()

    def _on_export_thread_done(self, *args):
        """Clear the export_thread reference after the thread finishes.

        The result signal is emitted from inside ``run()`` before the native
        QThread has fully stopped, so release the reference only after the
        worker is idle.
        """
        thread = getattr(self.gui, "export_thread", None)
        release_thread_when_stopped(
            thread,
            lambda: setattr(self.gui, "export_thread", None)
            if getattr(self.gui, "export_thread", None) is thread
            else None,
        )

    def preview_five_seconds(self):
        if hasattr(self.gui, "ensure_media_backend_ready"):
            self.gui.ensure_media_backend_ready()
        video_path = self._resolve_export_video_path()
        if not video_path or not os.path.exists(video_path):
            QMessageBox.warning(self.gui, "Error", "Please choose a video first.")
            return

        # Check if a quick preview is already running
        if hasattr(self.gui, 'quick_preview_thread') and self.gui.quick_preview_thread.isRunning():
            self.gui.log("[Preview] 5s preview already running, ignoring request")
            return

        start_seconds = max(0.0, self.gui.media_player.position() / 1000.0)
        duration_seconds = 5.0
        mode = self._effective_render_mode_without_tts(self.gui.get_output_mode_key())
        preview_output = os.path.join(self.gui.get_project_temp_dir("preview"), f"preview_5s_{int(start_seconds)}.mp4")

        chosen_audio = ""
        if mode in ("voice", "both"):
            chosen_audio = self._regenerate_mixed_audio_with_current_volumes()
        if mode in ("voice", "both") and not chosen_audio:
            QMessageBox.warning(self.gui, "Error", "Please generate dubbed voice or choose existing audio first.")
            return

        preview_srt_path = ""
        preview_segments = []
        preview_ass_path = ""
        mask_regions, blur_regions, logo_layers, text_layers = self._extract_render_layers()
        has_visual_layers = bool(mask_regions or blur_regions or logo_layers or text_layers)
        has_active_video_filters = bool(
            hasattr(self.gui, "has_active_video_filters") and self.gui.has_active_video_filters()
        )

        if mode in ("subtitle", "both"):
            preview_srt_path, preview_segments = self.build_subtitle_preview_srt(start_seconds, duration_seconds)
            if not preview_srt_path and not has_visual_layers and not has_active_video_filters:
                QMessageBox.warning(self.gui, "Error", "Could not build the 5-second subtitle preview clip.")
                return
            if preview_srt_path:
                preview_ass_path = self._build_fast_preview_subtitle_ass(start_seconds, duration_seconds)

        self.gui.preview_5s_btn.setEnabled(False)
        self.gui.preview_5s_btn.setText("Rendering...")
        self.gui.progress_bar.setValue(92)

        try:
            self.gui.media_player.pause()
        except Exception:
            pass

        target_width, target_height = self._resolve_output_canvas_dimensions(video_path)
        fill_focus_x, fill_focus_y = self.gui.get_output_fill_focus()
        original_audio_gain_db = self.gui.get_effective_original_audio_gain_db()
        mask_regions = self._rebase_timed_layers(mask_regions, start_seconds, duration_seconds)
        blur_regions = self._rebase_timed_layers(blur_regions, start_seconds, duration_seconds)
        logo_layers = self._rebase_timed_layers(logo_layers, start_seconds, duration_seconds)
        text_image_layers = self._build_fast_preview_text_images(
            text_layers, start_seconds, duration_seconds, target_width, target_height,
            self.gui.get_project_temp_dir("preview"),
        )

        self.gui.quick_preview_thread = QuickPreviewWorker(
            video_path=video_path,
            output_path=preview_output,
            mode=mode,
            start_seconds=start_seconds,
            duration_seconds=duration_seconds,
            srt_path=preview_srt_path,
            ass_path=preview_ass_path,
            audio_path=chosen_audio,
            subtitle_style=self.gui.get_subtitle_export_style(segments=preview_segments),
            target_width=target_width,
            target_height=target_height,
            output_scale_mode=self.gui.get_output_scale_mode_key(),
            output_fill_focus_x=fill_focus_x,
            output_fill_focus_y=fill_focus_y,
            video_filter_state=self.gui.get_video_filter_state() if hasattr(self.gui, "get_video_filter_state") else {},
            original_audio_gain_db=original_audio_gain_db,
            mask_regions=mask_regions,
            blur_regions=blur_regions,
            logo_layers=logo_layers,
            text_image_layers=text_image_layers,
            temp_dir=self.gui.get_project_temp_dir("preview"),
        )
        worker = self.gui.quick_preview_thread
        worker.finished.connect(self.gui.on_quick_preview_ready)
        worker.finished.connect(
            lambda *_args, worker=worker: release_thread_when_stopped(
                worker,
                lambda: setattr(self.gui, "quick_preview_thread", None)
                if getattr(self.gui, "quick_preview_thread", None) is worker
                else None,
            )
        )
        self.gui.quick_preview_thread.start()

    def start_exact_frame_preview(self, show_dialog: bool = True):
        if hasattr(self.gui, "ensure_media_backend_ready"):
            self.gui.ensure_media_backend_ready()
        video_path = self._resolve_export_video_path()
        if not video_path or not os.path.exists(video_path):
            if show_dialog:
                QMessageBox.warning(self.gui, "Error", "Please choose a video first.")
            return

        # Check if a frame preview is already running
        if hasattr(self.gui, 'frame_preview_thread') and self.gui.frame_preview_thread.isRunning():
            self.gui.log("[Preview] Frame preview already running, ignoring request")
            return

        mode = self._effective_render_mode_without_tts(self.gui.get_output_mode_key())
        preview_srt_path = ""
        preview_segments = []
        if mode in ("subtitle", "both"):
            preview_srt_path, preview_segments = self.build_full_active_subtitle_srt()
        has_active_video_filters = bool(hasattr(self.gui, "has_active_video_filters") and self.gui.has_active_video_filters())
        if mode in ("subtitle", "both") and not preview_srt_path and not has_active_video_filters:
            if show_dialog:
                QMessageBox.warning(self.gui, "Error", "No active subtitle track is available for frame preview.")
            return

        if self.gui._frame_preview_running:
            self.gui._pending_auto_frame_preview = True
            self.gui._show_dialog_on_frame_preview = self.gui._show_dialog_on_frame_preview or show_dialog
            return

        timestamp_seconds = max(0.0, self.gui.media_player.position() / 1000.0)
        out_dir = self.gui.get_project_temp_dir("preview")
        video_name = os.path.splitext(os.path.basename(video_path))[0]
        self.gui.cleanup_file_if_exists(self.gui.last_exact_preview_frame_path)
        frame_output = os.path.join(out_dir, f"{video_name}_preview_frame_{int(time.time())}.png")

        self.gui._frame_preview_running = True
        self.gui._show_dialog_on_frame_preview = show_dialog
        self.gui.preview_frame_btn.setEnabled(False)
        self.gui.preview_frame_btn.setText("Rendering frame...")
        self.gui.progress_bar.setValue(90)
        self.gui.frame_preview_status_label.setText("Rendering exact frame preview...")
        # For live filter thumbnail preview, render the source frame directly and let the UI
        # provide the black background. This keeps the actual video content larger.
        use_output_canvas = bool(show_dialog)
        target_width, target_height = ((None, None) if not use_output_canvas else self._resolve_output_canvas_dimensions(video_path))
        fill_focus_x, fill_focus_y = self.gui.get_output_fill_focus()

        self.gui.frame_preview_thread = ExactFramePreviewWorker(
            video_path=video_path,
            output_path=frame_output,
            timestamp_seconds=timestamp_seconds,
            srt_path=preview_srt_path,
            subtitle_style=self.gui.get_subtitle_export_style(segments=preview_segments),
            target_width=target_width,
            target_height=target_height,
            output_scale_mode=self.gui.get_output_scale_mode_key(),
            output_fill_focus_x=fill_focus_x,
            output_fill_focus_y=fill_focus_y,
            video_filter_state=self.gui.get_video_filter_state() if hasattr(self.gui, "get_video_filter_state") else {},
        )
        worker = self.gui.frame_preview_thread
        worker.finished.connect(self.gui.on_exact_frame_ready)
        worker.finished.connect(
            lambda *_args, worker=worker: release_thread_when_stopped(
                worker,
                lambda: setattr(self.gui, "frame_preview_thread", None)
                if getattr(self.gui, "frame_preview_thread", None) is worker
                else None,
            )
        )
        self.gui.frame_preview_thread.start()

    def on_exact_frame_ready(self, output_path, error):
        self.gui._frame_preview_running = False
        self.gui.preview_frame_btn.setEnabled(True)
        self.gui.preview_frame_btn.setText("Open Large Frame Preview")
        self.gui.progress_bar.setValue(100)

        if error:
            self.gui.frame_preview_status_label.setText("Frame preview could not be rendered.")
            if self.gui._show_dialog_on_frame_preview:
                self.gui.show_error("Error", "Frame preview failed.", str(error))
            else:
                self.gui.log(f"[Frame Preview] skipped: {error}")
            self.gui._show_dialog_on_frame_preview = False
            return

        if output_path and os.path.exists(output_path):
            self.gui.last_exact_preview_frame_path = output_path
            self.gui.processed_artifacts["preview_frame"] = output_path
            self.gui.update_frame_preview_thumbnail(output_path)
            if bool(hasattr(self.gui, "has_active_video_filters") and self.gui.has_active_video_filters()) and hasattr(self.gui, "show_filter_thumbnail_preview"):
                self.gui.show_filter_thumbnail_preview(output_path)
            if self.gui._show_dialog_on_frame_preview:
                self.gui.show_frame_preview_dialog(output_path)

        rerun_pending = bool(getattr(self.gui, "_pending_auto_frame_preview", False))
        self.gui._pending_auto_frame_preview = False
        self.gui._show_dialog_on_frame_preview = False
        if rerun_pending:
            QTimer.singleShot(0, self.gui.trigger_auto_frame_preview)

    def build_subtitle_preview_srt(self, start_seconds: float, duration_seconds: float):
        segments = self.gui.get_active_segments()
        if not segments:
            return "", []

        clipped = []
        end_seconds = start_seconds + duration_seconds
        for seg in segments:
            seg_start = float(seg["start"])
            seg_end = float(seg["end"])
            if seg_end < start_seconds or seg_start > end_seconds:
                continue
            clipped_words = []
            for word in seg.get("words", []) or []:
                try:
                    word_start = float(word.get("start", 0.0))
                    word_end = float(word.get("end", 0.0))
                except (TypeError, ValueError, AttributeError):
                    continue
                if word_end < start_seconds or word_start > end_seconds:
                    continue
                clipped_words.append(
                    {
                        "start": max(0.0, word_start - start_seconds),
                        "end": min(duration_seconds, word_end - start_seconds),
                        "text": str(word.get("text", "") or "").strip(),
                    }
                )
            seg_text = (
                seg.get("final_text")
                or seg.get("text")
                or seg.get("subtitle_text")
                or seg.get("raw_translation")
                or seg.get("original_text")
                or ""
            ) if isinstance(seg, dict) else (
                getattr(seg, "subtitle_text", "")
                or getattr(seg, "final_text", "")
                or getattr(seg, "original_text", "")
                or getattr(seg, "text", "")
            )
            clipped.append(
                {
                    "start": max(0.0, seg_start - start_seconds),
                    "end": min(duration_seconds, seg_end - start_seconds),
                    "text": seg_text,
                    "final_text": seg_text,
                    "words": clipped_words,
                    "manual_highlights": list(seg.get("manual_highlights", []) if isinstance(seg, dict) else getattr(seg, "manual_highlights", [])),
                }
            )

        if not clipped:
            return "", []

        preview_srt_path = self.gui.get_project_temp_path("preview", "preview_subtitle_5s.srt", create_parent=True)
        self.gui.cleanup_file_if_exists(preview_srt_path)
        from subtitle_builder import generate_srt

        generate_srt(clipped, preview_srt_path)
        return preview_srt_path, clipped

    def build_full_active_subtitle_srt(self):
        segments = self.gui.get_active_segments()
        if not segments:
            return "", []
        preview_srt_path = self.gui.get_project_temp_path("preview", "preview_subtitle_full.srt", create_parent=True)
        self.gui.cleanup_file_if_exists(preview_srt_path)
        from subtitle_builder import generate_srt

        generate_srt(segments, preview_srt_path)
        return preview_srt_path, segments

    def on_export_finished(self, output_path, error):
        self.gui._close_export_progress_dialog()
        self.gui.export_btn.setEnabled(True)
        self.gui.on_output_mode_changed(self.gui.output_mode_combo.currentText())
        if error:
            if "cancelled" in str(error).lower():
                self.gui.export_btn.setText("Export")
                if hasattr(self.gui, "progress_bar"):
                    self.gui.progress_bar.setValue(0)
                self.gui.update_project_step("export", "pending")
                self.gui.log("[Export] Video export was cancelled by user.")
                self.gui.refresh_ui_state()
                return
            self.gui.progress_bar.setValue(100)
            self.gui.update_project_step("export", "failed")
            self.gui.show_error("Error", "Final export failed.", error)
            return

        self.gui.progress_bar.setValue(100)

        if output_path and os.path.exists(output_path):
            self.gui.last_exported_video_path = output_path
            self.gui.processed_artifacts["final_video"] = output_path
            self.gui.update_project_artifact("final_video", output_path)
            self.gui.update_project_step("export", "done")
            self.gui.sync_preview_audio_track_to_output(apply_to_player=False)
            self.gui.update_workflow_stage_badges()
            self.gui.log(f"[Export] Final video exported successfully: {output_path}")
            self.gui.log("[Export] Kept current preview/subtitle state so you can continue editing after export.")
            message = QMessageBox(self.gui)
            message.setIcon(QMessageBox.Information)
            message.setWindowTitle("Export completed")
            message.setText("Video exported successfully.")
            message.setInformativeText(output_path)
            open_folder = message.addButton("Open Folder", QMessageBox.ActionRole)
            message.addButton("Close", QMessageBox.AcceptRole)
            message.exec()
            if message.clickedButton() is open_folder:
                QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(output_path)))

    def _on_auto_recap_export_finished(self, output_path, error):
        if not error and output_path:
            self.gui.last_recap_video_path = output_path
            if hasattr(self.gui, "persist_auto_recap_project_data"):
                self.gui.persist_auto_recap_project_data(
                    self.gui.current_auto_recap_edl, output_path
                )
        self.on_export_finished(output_path, error)

    def on_quick_preview_ready(self, output_path, error):
        if hasattr(self.gui, "ensure_media_backend_ready"):
            self.gui.ensure_media_backend_ready()
        self.gui._suspend_live_subtitle_sync = False
        self.gui.preview_5s_btn.setEnabled(True)
        self.gui.preview_5s_btn.setText("Fast Preview")
        self.gui.progress_bar.setValue(100)

        if error:
            self.gui.show_error("Error", "5-second preview failed.", error)
            return

        if output_path and os.path.exists(output_path):
            self.gui.last_exact_preview_5s_path = output_path
            self.gui.processed_artifacts["preview_video_5s"] = output_path
            if hasattr(self.gui, "update_project_artifact"):
                self.gui.update_project_artifact("preview_video_5s", output_path)
            self.gui.log(f"[Preview] 5-second preview exported: {output_path}")
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(output_path)):
                self.gui.open_folder(os.path.dirname(output_path))
            self.gui.refresh_ui_state()

    def preview_video(self):
        self._start_video_preview()

    def _start_video_preview(self):
        self.gui.log("[Preview] _start_video_preview called")
        
        # Check if a preview is already running
        if hasattr(self.gui, 'preview_thread') and self.gui.preview_thread.isRunning():
            self.gui.log("[Preview] Preview already running, ignoring request")
            return
        
        if hasattr(self.gui, "ensure_media_backend_ready"):
            self.gui.ensure_media_backend_ready()
        video_path = self._resolve_export_video_path()
        mode = self._effective_render_mode_without_tts(self.gui.get_output_mode_key())
        audio_path = ""
        if mode in ("voice", "both"):
            audio_path = self._regenerate_mixed_audio_with_current_volumes()
        if not video_path or not os.path.exists(video_path):
            self.gui.log("[Preview] Video file not found, showing error")
            QMessageBox.warning(self.gui, "Error", "Video file not found. Please select a video first.")
            return
        if mode in ("voice", "both") and (not audio_path or not os.path.exists(audio_path)):
            self.gui.log(f"[Preview] Audio file not found for mode={mode}, showing error")
            QMessageBox.warning(
                self.gui,
                "Error",
                "Selected audio source is not ready. Generate voice/mix first, or switch to 'Use existing mixed audio' and choose a valid file.",
            )
            return

        has_active_video_filters = bool(hasattr(self.gui, "has_active_video_filters") and self.gui.has_active_video_filters())
        self.gui.log(f"[Preview] has_active_video_filters={has_active_video_filters}")
        mask_regions, blur_regions, logo_layers, text_layers = self._extract_render_layers()
        has_overlays = bool(mask_regions or blur_regions or logo_layers or text_layers)
        self.gui._preview_video_has_burned_subtitles = bool(
            mode in ("subtitle", "both") and (has_active_video_filters or has_overlays)
        )

        # Subtitle-only preview can stay live when no canvas/filter/overlay processing is needed.
        if mode == "subtitle" and not has_active_video_filters and not has_overlays:
            self.gui.log("[Preview] Subtitle-only mode, no filters/overlays, using live preview")
            try:
                self.gui._preview_video_has_burned_subtitles = False
                if hasattr(self.gui.video_view, "set_preview_aspect_ratio"):
                    self.gui.video_view.set_preview_aspect_ratio(self.gui.get_output_ratio_key())
                if hasattr(self.gui.video_view, "set_preview_scale_mode"):
                    self.gui.video_view.set_preview_scale_mode(self.gui.get_output_scale_mode_key())
                self.gui.media_player.setSource(QUrl.fromLocalFile(video_path))
                self.gui.sync_live_subtitle_preview()
                self.gui.refresh_ui_state()
            except Exception:
                pass
            return
        ts = int(time.time())
        preview_out = self.gui.get_project_temp_path("preview", f"preview_vi_voice_{ts}.mp4", create_parent=True)
        self.gui.log(f"[Preview] Starting full preview render: mode={mode}, preview_out={preview_out}")
        preview_srt_path = ""
        preview_segments = []
        subtitle_style = {}
        styled_signature = ""
        cached_preview = ""
        if mode in ("subtitle", "both"):
            preview_srt_path, preview_segments = self.build_full_active_subtitle_srt()
            if not preview_srt_path and not has_overlays and not has_active_video_filters:
                QMessageBox.warning(self.gui, "Error", "No active subtitle track is available for video preview.")
                return
            subtitle_style = self.gui.get_subtitle_export_style(segments=preview_segments) if preview_srt_path else {}
            styled_signature = self._build_styled_preview_signature(
                video_path=video_path,
                audio_path=audio_path,
                mode=mode,
                srt_path=preview_srt_path,
                subtitle_style=subtitle_style,
                mask_regions=mask_regions,
                blur_regions=blur_regions,
                logo_layers=logo_layers,
                text_layers=text_layers,
            )
            cached_preview = str(getattr(self.gui, "last_styled_preview_path", "") or "").strip()
            cached_signature = str(getattr(self.gui, "last_styled_preview_signature", "") or "").strip()
            if cached_preview and cached_signature == styled_signature and os.path.exists(cached_preview):
                self.gui.log(f"[Preview] styled cache hit: {cached_preview}")
                self.gui.on_preview_ready(cached_preview, "", styled_signature)
                return

        if self.gui.last_preview_video_path and self.gui.last_preview_video_path != self.gui.last_exact_preview_5s_path:
            if not (cached_preview and os.path.abspath(self.gui.last_preview_video_path) == os.path.abspath(cached_preview)):
                try:
                    # Release file handle so Windows can delete the previous preview clip.
                    self.gui.media_player.stop()
                    self.gui.media_player.setSource(QUrl())
                except Exception:
                    pass
                self.gui.cleanup_file_if_exists(self.gui.last_preview_video_path)
            self.gui.processed_artifacts.pop("preview_video", None)
            self.gui.last_preview_video_path = ""

        try:
            self.gui.media_player.pause()
        except Exception:
            pass

        # Don't quit/wait on preview thread - let it finish naturally
        # The Apply button is disabled to prevent double-clicks

        self.gui.log(f"[Preview] video={video_path}")
        self.gui.log(f"[Preview] audio={audio_path or '<none>'}")
        self.gui.log(f"[Preview] out={preview_out}")
        self.gui.log(f"[Preview] app_mode={mode}")
        self.gui.log("[Preview] render_mode=styled")
        if styled_signature:
            self.gui.log(f"[Preview] styled cache miss: {styled_signature[:10]}")
        self.gui._styled_preview_running = True
        self.gui._preview_video_has_burned_subtitles = bool(
            mode in ("subtitle", "both") and preview_srt_path
        )
        if hasattr(self.gui, "preview_btn"):
            self.gui.preview_btn.setEnabled(False)
        self.gui.progress_bar.setValue(95)
        self.gui.refresh_ui_state()
        target_width, target_height = self._resolve_output_canvas_dimensions(video_path)
        fill_focus_x, fill_focus_y = self.gui.get_output_fill_focus()
        timeline_duration_ms = getattr(getattr(self.gui, "timeline", None), "duration", 0)
        if callable(timeline_duration_ms):
            timeline_duration_ms = timeline_duration_ms()
        project_duration = max(
            0.1,
            float(getattr(self.gui, "video_duration_ms", 0) or 0) / 1000.0,
            float(timeline_duration_ms or 0) / 1000.0,
            max((float(layer.get("end", 0.0) or 0.0) for layer in text_layers), default=0.0),
        )
        text_image_layers = self._build_fast_preview_text_images(
            text_layers, 0.0, project_duration, target_width, target_height,
            self.gui.get_project_temp_dir("preview"),
        )

        self.gui.preview_thread = PreviewMuxWorker(
            video_path,
            audio_path,
            preview_out,
            mode=mode,
            srt_path=preview_srt_path,
            subtitle_style=subtitle_style,
            render_subtitles=bool(mode in ("subtitle", "both") and preview_srt_path),
            target_width=target_width,
            target_height=target_height,
            output_scale_mode=self.gui.get_output_scale_mode_key(),
            output_fill_focus_x=fill_focus_x,
            output_fill_focus_y=fill_focus_y,
            video_filter_state=self.gui.get_video_filter_state() if hasattr(self.gui, "get_video_filter_state") else {},
            mask_regions=mask_regions,
            blur_regions=blur_regions,
            logo_layers=logo_layers,
            text_image_layers=text_image_layers,
            original_audio_gain_db=self._original_audio_gain_db_for_render(mode),
            temp_dir=self.gui.get_project_temp_dir("preview"),
        )
        self.gui.preview_thread.finished.connect(
            lambda preview_path, error: self.gui.on_preview_ready(preview_path, error, styled_signature)
        )
        pipeline_controller = getattr(self.gui, "pipeline_controller", None)
        if pipeline_controller is not None and hasattr(self.gui.preview_thread, "progress"):
            self.gui.preview_thread.progress.connect(pipeline_controller.on_preview_progress)
        self.gui.log("[Preview] Starting preview thread")
        self.gui.preview_thread.start()

    def on_preview_ready(self, preview_path, error, styled_signature=""):
        self.gui.log(f"[Preview] on_preview_ready called: preview_path={preview_path}, error={error}")
        if hasattr(self.gui, "ensure_media_backend_ready"):
            self.gui.ensure_media_backend_ready()
        self.gui._styled_preview_running = False
        self.gui._suspend_live_subtitle_sync = False
        if hasattr(self.gui, "preview_btn"):
            self.gui.preview_btn.setEnabled(True)
        self.gui.progress_bar.setValue(100)
        try:
            self.gui.refresh_ui_state()
        except Exception as e:
            if hasattr(self.gui, "log"):
                self.gui.log(f"[Preview] UI refresh error: {e}")
        try:
            if hasattr(self.gui, "_refresh_video_inspector_status"):
                self.gui._refresh_video_inspector_status()
        except Exception as e:
            if hasattr(self.gui, "log"):
                self.gui.log(f"[Preview] Inspector status error: {e}")
        
        # Re-enable Apply button after preview is ready

        if error:
            self.gui.log(f"[Preview] Error occurred: {error}")
            self.gui._video_filter_preview_dirty = bool(hasattr(self.gui, "has_active_video_filters") and self.gui.has_active_video_filters())
            self.gui._video_filter_apply_requested = False
            self.gui._play_video_filter_preview_when_ready = False
            self.gui._suspend_live_subtitle_sync = False
            self.gui.show_error("Error", "Preview failed.", str(error))
            self.gui._pipeline_fail("Preview failed.")
            self.gui.refresh_ui_state()
            return

        if preview_path and os.path.exists(preview_path):
            self.gui.log(f"[Preview] Preview successful, loading into player: {preview_path}")
            self.gui._video_filter_preview_dirty = False
            self.gui._video_filter_apply_requested = False
            if hasattr(self.gui, "hide_filter_thumbnail_preview"):
                self.gui.hide_filter_thumbnail_preview()
            self.gui.last_preview_video_path = preview_path
            self.gui.processed_artifacts["preview_video"] = preview_path
            self.gui.last_styled_preview_path = preview_path
            self.gui.last_styled_preview_signature = styled_signature
            self.gui.log(f"[Preview] ready={preview_path}")
            self.gui.refresh_video_dimensions(preview_path)
            self.gui.media_player.setSource(QUrl.fromLocalFile(preview_path))
            try:
                if hasattr(self.gui, "timeline"):
                    current_timeline_pos = int(self.gui.timeline._playhead * 1000)
                    if current_timeline_pos > 0:
                        self.gui.media_player.setPosition(current_timeline_pos)
            except Exception:
                pass
            if getattr(self.gui, "_preview_video_has_burned_subtitles", False):
                self.gui.media_player.clear_subtitle()
            else:
                self.gui.sync_live_subtitle_preview()
            self.gui.sync_preview_audio_track_to_output(apply_to_player=False)
            if getattr(self.gui, "_play_video_filter_preview_when_ready", False):
                self.gui._play_video_filter_preview_when_ready = False
                self.gui.media_player.play()
                self.gui.timeline.set_playing(True)

        if bool(getattr(self.gui, "_pipeline_active", False)) and str(getattr(self.gui, "_pipeline_step", "") or "").strip().lower() == "preview":
            self.gui.pipeline_controller.pipeline_advance("preview")
            self.gui.apply_segments_to_timeline()
            self.gui.refresh_ui_state()

        if getattr(self.gui, "_pending_video_filter_preview", False):
            QTimer.singleShot(0, self.gui.run_live_video_filter_preview)







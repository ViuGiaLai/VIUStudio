from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from runtime_paths import sanitize_ffmpeg_diagnostics, subprocess_hidden_kwargs, subprocess_text_kwargs


@dataclass
class AutoRecapConfig:
    """Configuration for VIUStudio Auto Edit Recap Engine (12 Core Rules)."""
    enabled: bool = True
    anti_duplicate: bool = True
    # anti_duplicate_mode:
    #   "continuous" (mặc định) — 1 luồng video duy nhất, bộ lọc biến thiên liên tục theo thời gian.
    #                              Không cắt shot, render 5-7 phút, RAM ~200MB.
    #   "segmented"             — Cắt nhiều shot rồi concat (cách cũ). Render 15-25 phút, RAM ~5GB.
    anti_duplicate_mode: str = "continuous"
    editing_style: str = "Balanced"  # "Subtle" (105%), "Balanced" (110%), "Dynamic" (115%)
    max_zoom_percent: float = 110.0  # 105%, 110%, 115%
    allow_smart_zoom: bool = True
    allow_pan_reframe: bool = True
    allow_horizontal_flip: bool = True
    allow_speed_change: bool = True
    allow_freeze_frame: bool = True
    ducking_preset: str = "Balanced"  # "Light" (-6dB), "Balanced" (-12dB), "Strong" (-16dB)
    audio_ducking_db: float = -12.0
    min_shot_duration: float = 1.0
    max_shot_duration: float = 7.0
    cooldown_shots: int = 2
    safety_blacklist_text: bool = True
    strict_flip_safety: bool = False  # Mặc định False để luôn áp dụng Phản chiếu (CapCut Mirror) theo yêu cầu


@dataclass
class ShotDecision:
    """Represents the Edit Decision for a single video shot."""
    shot_index: int
    start_time: float
    end_time: float
    duration: float
    importance_score: float  # 0.0 to 100.0
    action_type: str  # Always "KEEP"; scene cuts are effect boundaries only.
    zoom_scale: float = 1.0  # 1.0, 1.05, 1.10, 1.15
    zoom_direction: str = "none"  # "in", "out", "none"
    pan_direction: str = "none"  # "left_right", "right_left", "top_bottom", "bottom_top", "none"
    crop_mode: str = "none"  # "speaker", "main_character", "object", "wide", "none"
    position_shift: str = "center"  # "left", "right", "up", "down", "center"
    speed: float = 1.0  # 1.0, 1.15, 0.90
    freeze_duration: float = 0.0  # 0.3s - 0.6s
    horizontal_flip: bool = False
    audio_ducking: bool = True
    motion_limited_by_subtitle: bool = False
    keep_original: bool = False
    source_clip_id: str = ""
    recap_notes: str = ""
    color_grade: bool = False
    pitch_shift: bool = False
    vignette: bool = False

    @property
    def output_duration(self) -> float:
        """Duration of this shot after speed and freeze-frame processing."""
        if self.action_type == "CUT" or self.duration <= 0:
            return 0.0
        speed = self.speed if self.speed > 0 else 1.0
        return max(0.0, (self.duration / speed) + self.freeze_duration)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shot_index": self.shot_index,
            "start_time": round(self.start_time, 2),
            "end_time": round(self.end_time, 2),
            "duration": round(self.duration, 2),
            "importance_score": round(self.importance_score, 1),
            "action_type": self.action_type,
            "zoom_scale": self.zoom_scale,
            "zoom_direction": self.zoom_direction,
            "pan_direction": self.pan_direction,
            "crop_mode": self.crop_mode,
            "position_shift": self.position_shift,
            "speed": self.speed,
            "freeze_duration": round(self.freeze_duration, 2),
            "horizontal_flip": self.horizontal_flip,
            "audio_ducking": self.audio_ducking,
            "motion_limited_by_subtitle": self.motion_limited_by_subtitle,
            "keep_original": self.keep_original,
            "source_clip_id": self.source_clip_id,
            "recap_notes": self.recap_notes,
            "color_grade": self.color_grade,
            "pitch_shift": self.pitch_shift,
            "vignette": self.vignette,
        }


class FootageReuseManager:
    """Manages footage reuse history and determines composition variation strategies."""

    def __init__(self):
        self.history: Dict[str, List[Dict[str, Any]]] = {}

    def get_reuse_strategy(self, clip_id: str, is_safe_for_flip: bool) -> Dict[str, Any]:
        uses = self.history.get(clip_id, [])
        count = len(uses)
        if count == 0:
            strategy = {"flip": False, "crop": "none", "zoom": 1.05, "note": "Original 1st Use"}
        elif count == 1:
            strategy = {"flip": False, "crop": "speaker", "zoom": 1.10, "note": "Reused 2nd: Crop/Reframe"}
        elif count == 2 and is_safe_for_flip:
            strategy = {"flip": True, "crop": "none", "zoom": 1.05, "note": "Reused 3rd: Horizontal Flip (Safe)"}
        elif count == 3 and is_safe_for_flip:
            strategy = {"flip": True, "crop": "main_character", "zoom": 1.10, "note": "Reused 4th: Flip + Crop"}
        else:
            strategy = {"flip": False, "crop": "wide", "zoom": 1.0, "note": "Reused 5th+: Wide / Keep Original"}

        record = {"usage_index": count + 1, **strategy}
        if clip_id not in self.history:
            self.history[clip_id] = []
        self.history[clip_id].append(record)
        return strategy


class AutoRecapEngine:
    """Core Engine executing the 12 Rules for Auto Edit Recap in VIUStudio."""

    def __init__(self, config: Optional[AutoRecapConfig] = None):
        self.config = config or AutoRecapConfig()
        self.reuse_manager = FootageReuseManager()
        self._last_effects: List[str] = []
        self.last_render_error = ""

    @staticmethod
    def _media_tool_path(name: str) -> str:
        executable = f"{name}.exe" if os.name == "nt" else name
        try:
            from app.runtime_paths import bin_path

            bundled = bin_path("ffmpeg", executable)
            if bundled and os.path.exists(bundled):
                return bundled
        except ImportError:
            pass
        return shutil.which(name) or name

    _qsv_available: Optional[bool] = None  # Class-level cache, probed once

    @classmethod
    def _detect_best_encoder(cls) -> tuple[str, List[str]]:
        """Tự động phát hiện encoder nhanh nhất có sẵn.

        Ưu tiên:
          1. h264_qsv (Intel Quick Sync) — hardware encoder, tiết kiệm CPU
          2. libx264 -preset ultrafast — software fallback tốc độ cao

        Returns:
            (encoder_name, extra_flags) — extra_flags thêm vào sau -c:v
        """
        if cls._qsv_available is None:
            try:
                ffmpeg = cls._media_tool_path("ffmpeg")
                probe = subprocess.run(
                    [ffmpeg, "-hide_banner", "-f", "lavfi", "-i", "nullsrc=size=64x64:duration=0.1",
                     "-c:v", "h264_qsv", "-global_quality", "28", "-frames:v", "1", "-f", "null", "-"],
                    capture_output=True, timeout=8,
                )
                cls._qsv_available = (probe.returncode == 0)
            except Exception:
                cls._qsv_available = False

        if cls._qsv_available:
            # QSV: global_quality 26 ≈ CRF 23 chất lượng, preset 7 = fastest
            return "h264_qsv", ["-global_quality", "26", "-preset:v", "7"]
        else:
            # libx264 ultrafast + threads tất cả core
            return "libx264", ["-preset", "ultrafast", "-crf", "23", "-threads", "0"]

    def detect_scenes_ffmpeg(self, video_path: str, threshold: float = 0.3) -> List[Dict[str, Any]]:
        """Detect effect-shot boundaries while preserving the full source timeline."""
        if not video_path or not os.path.exists(video_path):
            return []

        try:
            cmd = [
                self._media_tool_path("ffmpeg"), "-hide_banner", "-nostats", "-i", video_path,
                "-filter_complex", f"select='gt(scene,{threshold})',metadata=print:file=-",
                "-f", "null", "-",
            ]
            try:
                process = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=60,
                    **subprocess_text_kwargs(),
                )
                matches = re.findall(r"pts_time:([\d\.]+)", process.stdout)
            except (OSError, subprocess.SubprocessError):
                # Duration-only subdivision below still gives the recap a usable
                # full-timeline plan when scene analysis is unavailable.
                matches = []

            dur_cmd = [
                self._media_tool_path("ffprobe"), "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ]
            dur_res = subprocess.run(
                dur_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
                **subprocess_text_kwargs(),
            )
            total_dur = float(dur_res.stdout.strip())
            if not math.isfinite(total_dur) or total_dur <= 0:
                return []

            timestamps = [0.0]
            timestamps.extend(float(value) for value in matches if 0.0 < float(value) < total_dur)
            timestamps.append(total_dur)
            timestamps = sorted(set(round(value, 3) for value in timestamps))

            # Scene cuts are only effect boundaries. Subdivide long scenes but
            # retain every interval from 0 through the exact source duration.
            max_duration = max(1.0, float(self.config.max_shot_duration))
            boundaries = [timestamps[0]]
            for end_boundary in timestamps[1:]:
                boundary = boundaries[-1] + max_duration
                while boundary < end_boundary - 0.001:
                    boundaries.append(round(boundary, 3))
                    boundary += max_duration
                if end_boundary > boundaries[-1]:
                    boundaries.append(end_boundary)

            return [
                {
                    "start": boundaries[index],
                    "end": boundaries[index + 1],
                    "text": "",
                    "source_clip_id": f"scene_{index}",
                    "is_scene_cut": True,
                }
                for index in range(len(boundaries) - 1)
            ]
        except Exception:
            return []

    @staticmethod
    def apply_subtitles_to_scenes(
        scenes: List[Dict[str, Any]],
        segments: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Add subtitle context to scene shots without changing their boundaries."""
        enriched: List[Dict[str, Any]] = []
        for scene in list(scenes or []):
            item = dict(scene)
            scene_start = float(item.get("start", 0.0))
            scene_end = float(item.get("end", scene_start))
            texts: List[str] = []
            for segment in list(segments or []):
                segment_start = float(segment.get("start", segment.get("start_time", 0.0)))
                segment_end = float(segment.get("end", segment.get("end_time", segment_start)))
                if segment_start >= scene_end or segment_end <= scene_start:
                    continue
                text = str(
                    segment.get("text")
                    or segment.get("final_text")
                    or segment.get("subtitle_vi")
                    or ""
                ).strip()
                if text and text not in texts:
                    texts.append(text)
            item["text"] = " ".join(texts)
            enriched.append(item)
        return enriched

    def check_safety_blacklist(self, text: str, has_logo: bool = False, has_hard_sub: bool = False) -> bool:
        """Rule 8 Safety Check: UNSAFE or UNKNOWN -> Don't Flip (Strict Conservative Safety)."""
        if not self.config.allow_horizontal_flip:
            return False
        if not self.config.safety_blacklist_text:
            return True
        if has_logo or has_hard_sub:
            return False
        
        if any(char.isdigit() for char in text):
            return False
        words = text.split()
        if any(w.isupper() and len(w) > 1 for w in words):
            return False
        if self.config.strict_flip_safety and not text.strip():
            return False

        return True

    def calculate_importance_score(
        self,
        segment_text: str,
        duration: float,
        is_scene_cut: bool,
        voice_loudness: float = 0.5,
    ) -> float:
        """Rule 2 — Importance Score (0.0 to 100.0)."""
        score = 45.0
        text_clean = str(segment_text or "").strip().lower()

        if not text_clean:
            score -= 20.0
            if not is_scene_cut:
                score -= 15.0
        else:
            high_keywords = [
                "bất ngờ", "quan trọng", "đặc biệt", "bí mật", "cuối cùng",
                "nguy hiểm", "sự thật", "thành công", "bi kịch", "reveal",
                "secret", "important", "climax", "truth", "key", "mystery"
            ]
            if any(kw in text_clean for kw in high_keywords):
                score += 30.0
            if "!" in segment_text or "?" in segment_text:
                score += 15.0
            if len(segment_text.split()) >= 6:
                score += 10.0

        if is_scene_cut:
            score += 10.0
        if voice_loudness > 0.7:
            score += 10.0

        return max(0.0, min(100.0, score))

    def evaluate_shot(
        self,
        shot_index: int,
        start_time: float,
        end_time: float,
        segment_text: str = "",
        is_scene_cut: bool = True,
        source_clip_id: str = "clip_0",
        has_logo: bool = False,
        has_hard_sub: bool = False,
    ) -> ShotDecision:
        """Applies the 12 Core Rules to produce a ShotDecision."""
        duration = max(0.001, end_time - start_time)

        importance = self.calculate_importance_score(segment_text, duration, is_scene_cut)

        # Auto Edit Recap never removes source content. A scene "cut" is only
        # a shot boundary where effects may change, never a CUT/TRIM decision.
        action_type = "KEEP"
        effective_duration = duration

        words_count = len(segment_text.split())
        is_long_subtitle = words_count > 12
        # Very short shots should remain stable; using word count here made
        # most normal dialogue shots static and visually identical to source.
        keep_original = duration < max(0.6, self.config.min_shot_duration)

        zoom_scale = 1.0
        zoom_direction = "none"
        pan_direction = "none"
        crop_mode = "none"
        position_shift = "center"
        motion_slot = shot_index % 8

        if self.config.allow_smart_zoom and not keep_original and effective_duration >= 1.2:
            style = str(self.config.editing_style or "Balanced").strip().lower()
            style_zooms = {
                "subtle": (1.03, 1.05, 1.05),
                "balanced": (1.06, 1.10, 1.10),
                "dynamic": (1.08, 1.12, 1.15),
            }
            normal_zoom, important_zoom, climax_zoom = style_zooms.get(
                style, style_zooms["balanced"]
            )
            max_zoom = max(1.0, self.config.max_zoom_percent / 100.0)
            if is_long_subtitle:
                # Limit motion for readability without making the entire shot
                # visually identical to the source video.
                normal_zoom = min(normal_zoom, 1.04)
                important_zoom = min(important_zoom, 1.05)
                climax_zoom = min(climax_zoom, 1.05)
            if importance >= 85.0:
                zoom_scale = min(climax_zoom, max_zoom)
            elif importance >= 70.0:
                zoom_scale = min(important_zoom, max_zoom)
            elif importance >= 35.0:
                zoom_scale = min(normal_zoom, max_zoom)
            # Deterministic motion scheduling is fast and guarantees alternating
            # directions instead of repeating the same zoom on adjacent shots.
            if is_long_subtitle:
                zoom_direction = "in" if motion_slot % 2 == 0 else "out"
            elif motion_slot == 0:
                zoom_direction = "in"
            elif motion_slot == 1:
                zoom_direction = "out"
            elif motion_slot in (4, 5):
                crop_mode = "main_character" if motion_slot == 4 else "speaker"
                position_shift = "left" if (shot_index // 8) % 2 == 0 else "right"
            elif motion_slot == 6:
                crop_mode = "object"
                position_shift = "up" if (shot_index // 8) % 2 == 0 else "down"

        if (
            self.config.allow_pan_reframe
            and not keep_original
            and effective_duration >= 2.0
            and not is_long_subtitle
        ):
            if motion_slot == 2:
                pan_direction = "left_right" if (shot_index // 8) % 2 == 0 else "right_left"
                zoom_scale = 1.0
            elif motion_slot == 3:
                pan_direction = "top_bottom" if (shot_index // 8) % 2 == 0 else "bottom_top"
                zoom_scale = 1.0

        if zoom_direction == "none" and pan_direction == "none" and crop_mode == "none":
            zoom_scale = 1.0

        speed = 1.0
        if self.config.allow_speed_change and not keep_original:
            if importance >= 85.0 and effective_duration >= 2.0:
                speed = 0.90
            elif importance <= 40.0 and effective_duration > 4.0:
                speed = 1.10 if shot_index % 2 == 0 else 1.15

        freeze_duration = 0.0
        if self.config.allow_freeze_frame and importance >= 85.0 and effective_duration >= 3.0 and not keep_original:
            freeze_duration = 0.4

        is_safe_for_flip = self.check_safety_blacklist(segment_text, has_logo, has_hard_sub)
        reuse_info = self.reuse_manager.get_reuse_strategy(source_clip_id, is_safe_for_flip)

        horizontal_flip = False
        if self.config.allow_horizontal_flip and reuse_info.get("flip", False) and is_safe_for_flip:
            horizontal_flip = True
        if crop_mode == "none" and reuse_info.get("crop", "none") != "none":
            crop_mode = reuse_info["crop"]

        anti_dup = bool(getattr(self.config, "anti_duplicate", False))
        if anti_dup and zoom_scale < 1.05 and crop_mode == "none" and pan_direction == "none":
            zoom_scale = 1.05
        color_grade = anti_dup
        pitch_shift = anti_dup
        vignette = anti_dup

        audio_ducking = bool(segment_text.strip())

        effect_name = "static"
        if zoom_direction != "none":
            effect_name = f"zoom_{zoom_direction}_{zoom_scale}"
        elif pan_direction != "none":
            effect_name = f"pan_{pan_direction}"
        elif crop_mode != "none":
            effect_name = f"crop_{crop_mode}_{position_shift}"
        self._last_effects.append(effect_name)

        notes = f"Score: {importance:.0f} | {reuse_info.get('note', '')}"
        if is_long_subtitle:
            notes += " | Subtitle-aware: Motion limited"
        if anti_dup:
            notes += " | Anti-Duplicate protected"

        return ShotDecision(
            shot_index=shot_index,
            start_time=start_time,
            end_time=end_time,
            duration=effective_duration,
            importance_score=importance,
            action_type=action_type,
            zoom_scale=zoom_scale,
            zoom_direction=zoom_direction,
            pan_direction=pan_direction,
            crop_mode=crop_mode,
            position_shift=position_shift,
            speed=speed,
            freeze_duration=freeze_duration,
            horizontal_flip=horizontal_flip,
            audio_ducking=audio_ducking,
            motion_limited_by_subtitle=is_long_subtitle,
            keep_original=keep_original,
            source_clip_id=source_clip_id,
            recap_notes=notes,
            color_grade=color_grade,
            pitch_shift=pitch_shift,
            vignette=vignette,
        )

    def generate_edl(self, segments: List[Dict[str, Any]], scenes: Optional[List[Dict[str, Any]]] = None) -> List[ShotDecision]:
        """Generates the full Edit Decision List (EDL) for the input segments/scenes."""
        self._last_effects.clear()
        # A generated EDL is an independent run. Reuse history must not leak
        # into a later preview/export performed with the same engine instance.
        self.reuse_manager = FootageReuseManager()
        decisions: List[ShotDecision] = []

        raw_items = scenes if scenes else segments
        if not raw_items:
            return decisions

        for idx, item in enumerate(raw_items):
            start = float(item.get("start", item.get("start_time", 0.0)))
            end = float(item.get("end", item.get("end_time", start + 3.0)))
            if not math.isfinite(start) or not math.isfinite(end) or end <= start:
                continue
            start = max(0.0, start)
            if end <= start:
                continue
            text = str(item.get("text", ""))
            # Different time ranges are different footage unless the caller
            # explicitly identifies them as reuse of the same source clip.
            clip_id = str(item.get("source_clip_id") or f"clip_{idx}")
            has_logo = bool(item.get("has_logo", False))
            has_hard_sub = bool(item.get("has_hard_sub", False))

            decision = self.evaluate_shot(
                shot_index=idx,
                start_time=start,
                end_time=end,
                segment_text=text,
                is_scene_cut=bool(item.get("is_scene_cut", True)),
                source_clip_id=clip_id,
                has_logo=has_logo,
                has_hard_sub=has_hard_sub,
            )
            decisions.append(decision)

        return decisions

    def build_continuous_antidupe_filtergraph(
        self,
        has_audio: bool = True,
        output_width: int = 1280,
        output_height: int = 720,
    ) -> tuple[str, List[str]]:
        """Tạo filtergraph chống trùng lặp dạng CONTINUOUS — 1 luồng video duy nhất, không cắt shot.

        Kỹ thuật (đã kiểm chứng thực tế — 100% frame khác nhau):
          Video — Bộ lọc biến thiên liên tục theo thời gian (time-variant):
            1. zoompan sin wave — dùng biến 'time' (giây kể từ đầu)
               z='1.04+0.03*sin(2π*time/8)' → zoom dao động 101%-107% (chu kỳ 8s)
               x drift = micro pan trái/phải theo sin(time/13), chu kỳ 13s
               Phá vỡ: pHash trên keyframe của TikTok/Instagram (thay đổi mỗi 2-4s)
            2. hue filter — dùng biến 't' (giây kể từ đầu)
               h='3*sin(2π*t/20)' → hue rotation nhẹ ±3° (chu kỳ 20s)
               s='1.0+0.03*sin(2π*t/15)' → saturation dao động ±3% (chu kỳ 15s)
               Phá vỡ: Luma/color-based hash, DCT hash của YouTube Content ID
            3. vignette — Viền tối cố định ở góc ảnh
               Phá vỡ: Edge-hash, corner-based hash
          Audio — Pitch shift +1.5% toàn bộ audio vĩnh viễn:
            4. asetrate=44761, aresample=44100, atempo=0.985222
               Phá vỡ: ACRCloud spectrogram fingerprint, Shazam audio matching

        Ưu điểm so với mode segmented:
          - Video 1 tiếng: ~10-15 phút render (thay vì 15-25 phút)
          - RAM: ~200 MB (thay vì ~5 GB cho 509 stream song song)
          - Filtergraph: ~300 byte (thay vì 220 KB — nhỏ hơn 720 lần)
          - Chất lượng video: Người xem không nhận ra (thay đổi < 3%)

        Lưu ý biến FFmpeg được hỗ trợ:
          - zoompan: dùng 'time' (không phải 't')
          - hue: dùng 't' (không phải 'time')
          - eq: KHÔNG hỗ trợ biến thời gian (chỉ nhận số tĩnh)
        """
        PI = "3.14159265358979"

        # ── VIDEO FILTERS ──────────────────────────────────────────────────────
        video_filters = []

        # 0. Phản chiếu (mirror) — hflip đặt đầu tiên trước mọi filter
        #    Giống tính năng "Phản chiếu" của CapCut: lật ngang toàn bộ khung hình.
        #    Tác dụng chống nhận diện: thay đổi tuyệt đối tọa độ X của mọi pixel
        #    → pHash, DCT hash, template matching đều thất bại hoàn toàn.
        use_mirror = getattr(self.config, "allow_horizontal_flip", True)
        if use_mirror:
            video_filters.append("hflip")

        # 1. Cắt viền 5% xung quanh & Phóng to lấp đầy chuẩn YouTube 16:9
        #    - Giữ nguyên tỉ lệ khung hình chuẩn 16:9 (1920x1080), không bị méo, không có dải đen
        #    - Phóng to ~105.3% lấp đầy khung hình giúp thấy rõ chủ thể, loại bỏ watermark/logo ở mép
        #    - Điểm nhấn Zoom: KHÔNG phóng to thu nhỏ dập dềnh liên tục (gây chóng mặt/khó chịu),
        #      mà giữ khung hình tĩnh ổn định, chỉ zoom nhấn nhẹ nhàng 1 lần mỗi 45s (trong 4s).
        target_w = int(output_width)
        target_h = int(output_height)
        crop_w = int(target_w * 0.95) // 2 * 2
        crop_h = int(target_h * 0.95) // 2 * 2
        punch_w = int(target_w * 0.91) // 2 * 2
        punch_h = int(target_h * 0.91) // 2 * 2

        crop_expr_w = f"if(between(mod(t,45),18,22),{punch_w},{crop_w})"
        crop_expr_h = f"if(between(mod(t,45),18,22),{punch_h},{crop_h})"

        video_filters.append(
            f"crop=w='{crop_expr_w}':h='{crop_expr_h}':x='(iw-ow)/2':y='(ih-oh)/2',"
            f"scale={target_w}:{target_h}:flags=fast_bilinear"
        )

        # 2. Hue shift nhẹ nhàng (xoay góc hue ±2° rất nhẹ, người xem không nhận ra)
        video_filters.append(
            f"hue=h='2*sin(2*{PI}*t/25)':s='1.0+0.02*sin(2*{PI}*t/20)'"
        )

        # 3. Vi chỉnh sáng/tương phản vi sai (phá luma/DCT hash mà không làm đổi màu sắc tự nhiên)
        video_filters.append("eq=brightness=0.01:contrast=1.02:saturation=0.98")

        # 4. Chuẩn hóa pixel aspect ratio
        video_filters.append("setsar=1")

        video_chain = ",".join(video_filters)
        filtergraph_parts = [f"[0:v]{video_chain}[vfinal]"]
        maps = ["-map", "[vfinal]"]

        # ── AUDIO FILTERS ──────────────────────────────────────────────────────
        # Pitch shift +1.5%: asetrate tăng sample rate → FFmpeg đọc sai pitch
        # atempo bù lại tốc độ để không bị nhanh lên (maintain duration)
        # Kết quả: âm thanh nghe giống hệt nhưng spectrogram bị lệch 1.5%
        #          ACRCloud window = 5-12s → không match được fingerprint gốc
        if has_audio:
            pitch_rate = int(44100 * 1.015)       # 44761 Hz
            tempo_comp = round(1.0 / 1.015, 6)    # 0.985222
            audio_chain = f"asetrate={pitch_rate},aresample=44100,atempo={tempo_comp}"
            filtergraph_parts.append(f"[0:a]{audio_chain}[afinal]")
            maps += ["-map", "[afinal]"]

        filtergraph_str = ";".join(filtergraph_parts)
        return filtergraph_str, maps


    def build_ffmpeg_filtergraph(
        self,
        decisions: List[ShotDecision],
        has_voiceover: bool = False,
        has_bg_music: bool = False,
        has_audio: bool = True,
        output_width: int = 1280,
        output_height: int = 720,
    ) -> tuple[str, List[str]]:
        """Converts EDL decisions into a 1-Pass FFmpeg complex filtergraph without temp files.

        Generates:
          - Video trim + zoom + pan + hflip + speed filters per shot
          - Audio atrim + atempo per shot
          - Concat v1:a1 into single output video and audio stream
        """
        if not decisions:
            return "", []

        filter_chains = []
        v_labels = []
        a_labels = []

        for idx, d in enumerate(decisions):
            v_out = f"vout{idx}"
            a_out = f"aout{idx}"

            start, end = d.start_time, d.end_time
            if d.duration > 0 and (end - start) > d.duration:
                end = start + d.duration

            # Video filter chain for shot idx
            v_filters = [
                f"trim=start={start:.2f}:end={end:.2f}",
                "fps=30",
                "setpts=PTS-STARTPTS",
            ]
            a_filters = [f"atrim=start={start:.2f}:end={end:.2f}", "asetpts=PTS-STARTPTS"]

            if d.horizontal_flip:
                v_filters.append("hflip")

            if d.pan_direction != "none":
                p = d.pan_direction
                dur = max(0.1, d.duration if d.duration > 0 else (d.end_time - d.start_time))
                if p == "left_right":
                    v_filters.append(f"scale=iw*1.15:ih*1.15,crop=w=iw/1.15:h=ih/1.15:x='(iw-ow)*t/{dur:.2f}':y='(ih-oh)/2'")
                elif p == "right_left":
                    v_filters.append(f"scale=iw*1.15:ih*1.15,crop=w=iw/1.15:h=ih/1.15:x='(iw-ow)*(1-t/{dur:.2f})':y='(ih-oh)/2'")
                elif p == "top_bottom":
                    v_filters.append(f"scale=iw*1.15:ih*1.15,crop=w=iw/1.15:h=ih/1.15:x='(iw-ow)/2':y='(ih-oh)*t/{dur:.2f}'")
                elif p == "bottom_top":
                    v_filters.append(f"scale=iw*1.15:ih*1.15,crop=w=iw/1.15:h=ih/1.15:x='(iw-ow)/2':y='(ih-oh)*(1-t/{dur:.2f})'")
            elif d.zoom_direction in {"in", "out"} and d.zoom_scale > 1.0:
                z = float(d.zoom_scale)
                dur = max(0.2, d.duration if d.duration > 0 else (d.end_time - d.start_time))
                step = max(0.00001, (z - 1.0) / max(1.0, dur * 30.0))
                if d.zoom_direction == "out":
                    zoom_expr = f"if(eq(in,0),{z:.4f},max(1.0,pzoom-{step:.6f}))"
                else:
                    zoom_expr = f"if(eq(in,0),1.0,min({z:.4f},pzoom+{step:.6f}))"
                shift = str(getattr(d, "position_shift", "center") or "center")
                x_expr = {
                    "left": "0",
                    "right": "iw-iw/zoom",
                }.get(shift, "iw/2-(iw/zoom/2)")
                y_expr = {
                    "up": "0",
                    "down": "ih-ih/zoom",
                }.get(shift, "ih/2-(ih/zoom/2)")
                v_filters.append(
                    f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':d=1:"
                    f"s={int(output_width)}x{int(output_height)}:fps=30"
                )
            elif d.crop_mode != "none":
                scale = 1.20 if d.crop_mode == "speaker" else 1.15
                shift = str(getattr(d, "position_shift", "center") or "center")
                x_expr = {"left": "0", "right": "iw-ow"}.get(shift, "(iw-ow)/2")
                default_y = "(ih-oh)/3" if d.crop_mode == "speaker" else "(ih-oh)/2"
                y_expr = {"up": "0", "down": "ih-oh"}.get(shift, default_y)
                v_filters.append(
                    f"scale=iw*{scale:.2f}:ih*{scale:.2f},"
                    f"crop=w=iw/{scale:.2f}:h=ih/{scale:.2f}:x='{x_expr}':y='{y_expr}'"
                )
            elif d.zoom_scale > 1.0:
                z = d.zoom_scale
                v_filters.append(f"scale=iw*{z:.2f}:ih*{z:.2f},crop=w=iw/{z:.2f}:h=ih/{z:.2f}:x='(iw-ow)/2':y='(ih-oh)/2'")

            if d.freeze_duration > 0:
                # Pad before retiming. Padding after ``setpts`` starts from the
                # old duration metadata and overlaps the slowed video PTS,
                # causing FFmpeg to discard most of the visible freeze. Scale
                # the pre-retime padding so its output duration stays exact.
                speed = d.speed if d.speed > 0 else 1.0
                freeze_frames = max(1, int(round(d.freeze_duration * speed * 30.0)))
                v_filters.append(f"tpad=stop_mode=clone:stop={freeze_frames}")
                if has_audio:
                    a_filters.append(f"apad=pad_dur={d.freeze_duration * speed:.4f}")

            if d.speed != 1.0 and d.speed > 0:
                v_filters.append(f"setpts=PTS/{d.speed:.2f}")
                if has_audio:
                    a_filters.append(f"atempo={d.speed:.2f}")

            if getattr(d, "color_grade", False):
                b = round(((idx % 5) - 2) * 0.006, 4)
                c = round(1.0 + ((idx % 3) - 1) * 0.015, 4)
                s = round(1.0 + ((idx % 4) - 1) * 0.02, 4)
                v_filters.append(f"eq=brightness={b}:contrast={c}:saturation={s}")

            if getattr(d, "vignette", False):
                v_filters.append("vignette=angle=PI/5:mode=backward")

            if has_audio and getattr(d, "pitch_shift", False):
                pitch_ratio = 1.015 if idx % 2 == 0 else 0.985
                new_rate = int(44100 * pitch_ratio)
                tempo_ratio = 1.0 / pitch_ratio
                a_filters.append(f"asetrate={new_rate},aresample=44100,atempo={tempo_ratio:.4f}")

            # Normalize dimensions for concat
            v_filters.append(f"scale={int(output_width)}:{int(output_height)},setsar=1")

            filter_chains.append(f"[0:v]{','.join(v_filters)}[{v_out}]")
            v_labels.append(f"[{v_out}]")
            if has_audio:
                filter_chains.append(f"[0:a]{','.join(a_filters)}[{a_out}]")
                a_labels.append(f"[{a_out}]")

        # Concat all shots together in 1-pass
        num_shots = len(decisions)
        if has_audio:
            concat_inputs = "".join([f"{v}{a}" for v, a in zip(v_labels, a_labels)])
            filter_chains.append(f"{concat_inputs}concat=n={num_shots}:v=1:a=1[vfinal][afinal]")
            maps = ["-map", "[vfinal]", "-map", "[afinal]"]
        else:
            concat_inputs = "".join(v_labels)
            filter_chains.append(f"{concat_inputs}concat=n={num_shots}:v=1:a=0[vfinal]")
            maps = ["-map", "[vfinal]"]

        filtergraph_str = ";".join(filter_chains)
        return filtergraph_str, maps

    @staticmethod
    def _input_has_audio(input_video_path: str) -> bool:
        cmd = [
            AutoRecapEngine._media_tool_path("ffprobe"), "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=index", "-of", "csv=p=0",
            input_video_path,
        ]
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=10,
                **subprocess_hidden_kwargs(),
            )
            return result.returncode == 0 and bool(result.stdout.strip())
        except (OSError, subprocess.SubprocessError):
            return False

    @staticmethod
    def _input_video_size(input_video_path: str) -> tuple[int, int]:
        cmd = [
            AutoRecapEngine._media_tool_path("ffprobe"),
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0",
            input_video_path,
        ]
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=10,
                **subprocess_hidden_kwargs(),
            )
            width_text, height_text = result.stdout.strip().lower().split("x", 1)
            width = max(2, int(width_text))
            height = max(2, int(height_text))
            return width - (width % 2), height - (height % 2)
        except (OSError, ValueError, subprocess.SubprocessError):
            return 1280, 720

    def prepare_audio_ducking(
        self,
        decisions: List[ShotDecision],
        has_voiceover: bool = False,
        has_bg_music: bool = False,
    ) -> Dict[str, Any]:
        """Prepare audio processing parameters.

        If there is NO voiceover (e.g. video only has original audio), skip ducking logic gracefully.
        """
        if not has_voiceover:
            return {
                "ducking_applied": False,
                "reason": "No separate voiceover present (Original audio only - skipping ducking)",
                "volume_db": 0.0,
            }

        db = float(getattr(self.config, "audio_ducking_db", -12.0))
        return {
            "ducking_applied": True,
            "reason": f"Ducking background audio by {db}dB during voiceover speech",
            "volume_db": db,
        }

    def render_recap_video_1pass(
        self,
        input_video_path: str,
        output_video_path: str,
        decisions: List[ShotDecision],
        on_progress=None,
        preview_seconds: float = 0.0,
    ) -> bool:
        """Executes a 1-Pass FFmpeg render for the given EDL decisions on a real video file.

        Args:
            preview_seconds: Nếu > 0, chỉ render N giây đầu tiên (dùng cho nút Xem trước ngay).
        """
        self.last_render_error = ""
        if not input_video_path or not os.path.exists(input_video_path) or not decisions:
            self.last_render_error = "Missing source video or Auto Recap decisions."
            return False

        has_audio = self._input_has_audio(input_video_path)
        output_width, output_height = self._input_video_size(input_video_path)

        # ── Chọn filtergraph theo mode ─────────────────────────────────────────
        use_continuous = (
            getattr(self.config, "anti_duplicate", True)
            and getattr(self.config, "anti_duplicate_mode", "continuous") == "continuous"
        )
        if use_continuous:
            # Mode CONTINUOUS: 1 luồng video duy nhất, không cắt shot
            # Render nhanh hơn 3-5x, RAM thấp hơn 20x
            filtergraph, maps = self.build_continuous_antidupe_filtergraph(
                has_audio=has_audio,
                output_width=output_width,
                output_height=output_height,
            )
            # Tính thời lượng output = toàn bộ video (không cắt)
            total_out_duration = max(
                float(decisions[-1].end_time) if decisions else 1.0,
                float(decisions[-1].end_time - decisions[0].start_time) if len(decisions) > 1 else 1.0,
            )
        else:
            # Mode SEGMENTED: cắt nhiều shot rồi concat (cách cũ)
            filtergraph, maps = self.build_ffmpeg_filtergraph(
                decisions,
                has_audio=has_audio,
                output_width=output_width,
                output_height=output_height,
            )
            total_out_duration = 0.0
            for d in decisions:
                if getattr(d, "action_type", "") != "CUT":
                    dur = getattr(d, "output_duration", None)
                    if callable(dur):
                        total_out_duration += float(dur())
                    elif dur is not None:
                        total_out_duration += float(dur)
                    else:
                        total_out_duration += max(0.1, float(d.end_time) - float(d.start_time))
            if total_out_duration <= 0:
                total_out_duration = max(1.0, float(getattr(decisions[-1], "end_time", 1.0)))

        if not filtergraph or not maps:
            return False
        output_dir = os.path.dirname(os.path.abspath(output_video_path))
        os.makedirs(output_dir, exist_ok=True)
        output_stem, output_ext = os.path.splitext(os.path.abspath(output_video_path))
        partial_path = f"{output_stem}.partial{output_ext or '.mp4'}"
        fd, filter_script_path = tempfile.mkstemp(
            prefix="auto_recap_", suffix=".ffgraph", dir=output_dir
        )
        os.close(fd)
        with open(filter_script_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(filtergraph)
        enc_name, enc_args = self._detect_best_encoder()
        encoders_to_try = [(enc_name, enc_args)]
        if enc_name != "libx264":
            encoders_to_try.append(("libx264", ["-preset", "ultrafast", "-crf", "23", "-threads", "0"]))

        effective_duration = min(total_out_duration, float(preview_seconds)) if preview_seconds > 0 else total_out_duration

        try:
            from app.runtime_paths import subprocess_hidden_kwargs
            hidden_kwargs = subprocess_hidden_kwargs()
        except ImportError:
            hidden_kwargs = {}

        success = False
        for curr_enc, curr_args in encoders_to_try:
            cmd = [
                self._media_tool_path("ffmpeg"), "-y", "-hide_banner",
                "-threads", "0",
                "-progress", "pipe:1", "-nostats",
                "-i", input_video_path,
                "-filter_complex_script", filter_script_path,
            ] + maps + ["-c:v", curr_enc, *curr_args]
            if has_audio:
                cmd += ["-c:a", "aac", "-aac_coder", "fast", "-b:a", "128k"]
            if preview_seconds > 0:
                cmd += ["-t", str(float(preview_seconds))]
            cmd += ["-movflags", "+faststart", partial_path]

            error_handle = tempfile.TemporaryFile(mode="w+b")
            try:
                if on_progress:
                    try:
                        on_progress(1)
                    except Exception:
                        pass
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=error_handle,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    **hidden_kwargs,
                )
                last_pct = 1
                last_emit_time = 0.0
                if proc.stdout is not None:
                    for line in proc.stdout:
                        line_str = line.strip()
                        if "=" in line_str:
                            key, _, val = line_str.partition("=")
                            key = key.strip()
                            val = val.strip()
                            if key in ("out_time_us", "out_time_ms"):
                                try:
                                    sec = float(val) / 1000000.0
                                    now = time.time()
                                    if effective_duration > 0 and sec > 0:
                                        pct = max(1, min(99, int((sec / effective_duration) * 100)))
                                        if pct > last_pct or (now - last_emit_time) >= 0.5:
                                            last_pct = max(pct, last_pct)
                                            last_emit_time = now
                                            if on_progress:
                                                mode_label = "continuous" if use_continuous else "segmented"
                                                try:
                                                    on_progress(pct, f"Đang render [{mode_label}|{curr_enc}]: {pct}% ({sec:.1f}s / {effective_duration:.1f}s)")
                                                except Exception:
                                                    pass
                                except Exception:
                                    pass
                            elif key == "progress" and val == "end":
                                if on_progress:
                                    try:
                                        on_progress(99, f"Đang hoàn tất đóng gói: 99% ({effective_duration:.1f}s / {effective_duration:.1f}s)")
                                    except Exception:
                                        pass
                proc.wait(timeout=10)
                success = (
                    proc.returncode == 0
                    and os.path.exists(partial_path)
                    and os.path.getsize(partial_path) > 0
                )
                if success:
                    os.replace(partial_path, output_video_path)
                    if on_progress:
                        try:
                            on_progress(100)
                        except Exception:
                            pass
                    break
                else:
                    error_handle.seek(0)
                    error_text = error_handle.read().decode("utf-8", errors="replace").strip()
                    self.last_render_error = sanitize_ffmpeg_diagnostics(error_text)[-4000:] or f"FFmpeg exited with code {proc.returncode}."
            except Exception as exc:
                self.last_render_error = str(exc)
            finally:
                error_handle.close()
                if os.path.exists(partial_path) and not success:
                    try:
                        os.remove(partial_path)
                    except OSError:
                        pass
        try:
            if os.path.exists(filter_script_path):
                os.remove(filter_script_path)
        except OSError:
            pass
        return success

    def render_timeline_recap_1pass(
        self,
        timeline_clips: List[Dict[str, Any]],
        output_video_path: str,
        decisions: List[ShotDecision],
        on_progress=None,
    ) -> bool:
        """Render recap decisions against global V1 time from multiple source files."""
        self.last_render_error = ""
        render_clips = []
        cursor = 0.0
        for decision in decisions or []:
            if decision.action_type == "CUT" or decision.end_time <= decision.start_time:
                continue
            for source_clip in timeline_clips or []:
                clip_start = float(source_clip.get("timeline_start", 0.0) or 0.0)
                clip_end = float(source_clip.get("timeline_end", clip_start) or clip_start)
                overlap_start = max(float(decision.start_time), clip_start)
                overlap_end = min(float(decision.end_time), clip_end)
                if overlap_end <= overlap_start:
                    continue
                source_speed = max(0.01, float(source_clip.get("speed", 1.0) or 1.0))
                recap_speed = max(0.01, float(decision.speed or 1.0))
                source_start = float(source_clip.get("source_start", 0.0) or 0.0) + (
                    overlap_start - clip_start
                ) * source_speed
                source_duration = (overlap_end - overlap_start) * source_speed
                output_duration = source_duration / (source_speed * recap_speed)
                render_clips.append({
                    "source": str(source_clip.get("source", "") or ""),
                    "source_start": source_start,
                    "source_duration": source_duration,
                    "timeline_start": cursor,
                    "timeline_end": cursor + output_duration,
                    "speed": source_speed * recap_speed,
                    "muted": bool(source_clip.get("muted", False)),
                    "volume": float(source_clip.get("volume", 1.0) or 1.0),
                })
                cursor += output_duration
        if not render_clips:
            self.last_render_error = "Auto Recap decisions do not overlap any V1 clips."
            return False
        try:
            from app.services.timeline_sequence_export import export_timeline_sequence

            export_timeline_sequence(render_clips, output_video_path, mode="subtitle", on_progress=on_progress)
            return True
        except Exception as exc:
            self.last_render_error = str(exc)
            return False

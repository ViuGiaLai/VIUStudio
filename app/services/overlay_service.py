"""Translate Movie Review overlay/canvas settings into renderer arguments."""
from __future__ import annotations

from typing import Any
import os
import subprocess

from runtime_paths import subprocess_hidden_kwargs


class OverlayService:
    @staticmethod
    def renderer_config(presentation: dict[str, Any], export_config: dict[str, Any]) -> dict[str, Any]:
        mode = str(export_config.get("canvas_mode", "KEEP_SOURCE"))
        width, height, scale = {
            "PAD_VERTICAL": (1080, 1920, "fit"),
            "CROP_VERTICAL": (1080, 1920, "fill"),
            "CROP_SQUARE": (1080, 1080, "fill"),
            "CUSTOM": (int(export_config.get("custom_width", 1920) or 1920),
                       int(export_config.get("custom_height", 1080) or 1080), "fit"),
        }.get(mode, (None, None, "fit"))
        cleanup = str(presentation.get("source_overlay_mode", "keep")).lower()
        region = {
            "x": float(presentation.get("source_overlay_x", 70)) / 100,
            "y": float(presentation.get("source_overlay_y", 2)) / 100,
            "width": float(presentation.get("source_overlay_width", 27)) / 100,
            "height": float(presentation.get("source_overlay_height", 12)) / 100,
        }
        blur = None
        masks = None
        if cleanup == "blur":
            blur = {**region, "blur_strength": 36, "blur_opacity": 1.0}
        elif cleanup in {"cover", "crop"}:
            # Crop is represented as a cover region unless a face-aware crop
            # has been approved; this never silently changes the composition.
            masks = [{**region, "mode": "solid", "color": "#000000", "opacity": 0.9}]
        return {"target_width": width, "target_height": height, "output_scale_mode": scale,
                "blur_region": blur, "mask_regions": masks}

    @staticmethod
    def prepend_intro(ffmpeg: str, intro: str, main: str, output: str, width: int, height: int) -> None:
        from app.services.auto_recap_engine import AutoRecapEngine
        from app.video_processor import get_video_duration
        inputs = ["-i", intro, "-i", main]
        filters = [
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v0]",
            f"[1:v]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v1]",
        ]
        next_input = 2
        audio_labels = []
        for input_index, path in enumerate((intro, main)):
            if AutoRecapEngine._input_has_audio(path):
                label = f"a{input_index}"
                filters.append(f"[{input_index}:a]aresample=48000,asetpts=PTS-STARTPTS[{label}]")
                audio_labels.append(f"[{label}]")
            else:
                duration = max(0.1, float(get_video_duration(path) or 0.1))
                inputs += ["-f", "lavfi", "-t", f"{duration:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
                label = f"a{input_index}"
                filters.append(f"[{next_input}:a]asetpts=PTS-STARTPTS[{label}]")
                audio_labels.append(f"[{label}]")
                next_input += 1
        filters.append(f"[v0]{audio_labels[0]}[v1]{audio_labels[1]}concat=n=2:v=1:a=1[v][a]")
        from app.video_processor import build_export_h264_encoder_args
        video_enc_args = build_export_h264_encoder_args(ffmpeg, export_preset="fast", allow_hardware=True)
        cmd = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *inputs,
            "-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]",
            *video_enc_args, "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", output,
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3600,
            **subprocess_hidden_kwargs(),
        )
        if (result.returncode != 0 or not os.path.isfile(output)) and any(e in video_enc_args for e in ("h264_nvenc", "h264_qsv", "h264_amf")):
            fallback_enc_args = build_export_h264_encoder_args(ffmpeg, export_preset="fast", allow_hardware=False)
            cmd_fallback = [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *inputs,
                "-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]",
                *fallback_enc_args, "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart", output,
            ]
            result = subprocess.run(
                cmd_fallback,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3600,
                **subprocess_hidden_kwargs(),
            )
        if result.returncode != 0 or not os.path.isfile(output):
            raise RuntimeError("Không thể ghép Intro Bumper vào video review.")

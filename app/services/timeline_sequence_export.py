from __future__ import annotations

import os
import subprocess
import time
import tempfile

from app.runtime_paths import sanitize_ffmpeg_diagnostics, subprocess_text_kwargs


def _atempo(speed: float) -> str:
    value = max(0.01, float(speed or 1.0))
    factors = []
    while value > 2.0:
        factors.append(2.0)
        value /= 2.0
    while value < 0.5:
        factors.append(0.5)
        value /= 0.5
    factors.append(value)
    return ",".join(f"atempo={factor:.8f}" for factor in factors)


def _has_audio(path: str) -> bool:
    from app.runtime_paths import bin_path

    probe = str(bin_path("ffmpeg", "ffprobe.exe"))
    try:
        result = subprocess.run(
            [probe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index", "-of", "csv=p=0", path],
            capture_output=True, check=False, timeout=30, **subprocess_text_kwargs(),
        )
        return result.returncode == 0 and bool((result.stdout or "").strip())
    except Exception:
        return False


def _source_fps(path: str) -> int:
    from app.runtime_paths import bin_path

    probe = str(bin_path("ffmpeg", "ffprobe.exe"))
    try:
        result = subprocess.run(
            [probe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=avg_frame_rate", "-of", "csv=p=0", path],
            capture_output=True, check=False, timeout=30, **subprocess_text_kwargs(),
        )
        numerator, denominator = str(result.stdout or "0/1").strip().split("/", 1)
        return max(1, int(round(float(numerator) / max(1.0, float(denominator)))))
    except Exception:
        return 30


def export_timeline_sequence(
    clips: list[dict],
    output_path: str,
    *,
    mode: str = "subtitle",
    audio_path: str = "",
    ass_path: str = "",
    target_width: int | None = None,
    target_height: int | None = None,
    output_scale_mode: str = "fit",
    output_fill_focus_x: float = 0.5,
    output_fill_focus_y: float = 0.5,
    output_fps: int | None = None,
    video_filter_state: dict | None = None,
    original_audio_gain_db: float = 0.0,
    blur_regions=None,
    mask_regions=None,
    logo_layers=None,
    text_image_layers=None,
    export_preset: str = "balanced",
    video_bitrate_kbps: int = 2000,
    on_progress=None,
    cancellation_check=None,
) -> str:
    """Render sequential V1 clips in one FFmpeg graph, without a merged source file."""
    from video_processor import (
        _ass_filter_expression,
        _build_blur_filter_chain,
        _build_mask_filter_chain,
        _build_video_color_chain,
        _build_video_lut_chain,
        build_export_h264_encoder_args,
        _ffmpeg_path,
        _map_normalized_overlays_to_canvas,
        get_video_dimensions,
        run_ffmpeg_with_progress,
    )

    valid = [dict(clip) for clip in clips or [] if os.path.isfile(str(clip.get("source", "") or ""))]
    if not valid:
        raise ValueError("Timeline has no readable V1 video clips.")
    first_w, first_h = get_video_dimensions(valid[0]["source"])
    width = max(2, int(target_width or first_w or 1920))
    height = max(2, int(target_height or first_h or 1080))
    width -= width % 2
    height -= height % 2
    fps = max(1, int(output_fps or _source_fps(valid[0]["source"])))
    mode = str(mode or "subtitle").strip().lower()
    scale_mode = str(output_scale_mode or "fit").strip().lower()
    focus_x = max(0.0, min(1.0, float(output_fill_focus_x)))
    focus_y = max(0.0, min(1.0, float(output_fill_focus_y)))

    ffmpeg = _ffmpeg_path()
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    for clip in valid:
        command += ["-i", os.path.abspath(str(clip["source"]))]
    external_audio_index = None
    if mode in {"voice", "both"} and audio_path and os.path.isfile(audio_path):
        external_audio_index = len(valid)
        command += ["-i", os.path.abspath(audio_path)]
    use_timeline_audio = external_audio_index is None

    mapped_logo_layers = _map_normalized_overlays_to_canvas(
        logo_layers, first_w, first_h, width, height, scale_mode, focus_x, focus_y
    )
    overlay_inputs = []
    for layer in mapped_logo_layers or []:
        source = str(layer.get("source", "") or "")
        if os.path.isfile(source):
            overlay_inputs.append(("logo", dict(layer, source=source)))
    for layer in text_image_layers or []:
        source = str(layer.get("path", "") or "")
        if os.path.isfile(source):
            overlay_inputs.append(("text", dict(layer, source=source)))
    overlay_start_index = len(valid) + (1 if external_audio_index is not None else 0)
    for _kind, layer in overlay_inputs:
        command += ["-loop", "1", "-framerate", str(fps), "-i", layer["source"]]

    filters = []
    concat_inputs = []
    total_duration = 0.0
    for index, clip in enumerate(valid):
        start = max(0.0, float(clip.get("source_start", 0.0) or 0.0))
        source_duration = max(0.001, float(clip.get("source_duration", 0.0) or 0.0))
        speed = max(0.01, float(clip.get("speed", 1.0) or 1.0))
        timeline_duration = source_duration / speed
        total_duration += timeline_duration
        vlabel, alabel = f"sv{index}", f"sa{index}"
        if scale_mode == "fill":
            canvas_chain = (
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height}:(iw-{width})*{focus_x:.6f}:(ih-{height})*{focus_y:.6f}"
            )
        else:
            canvas_chain = (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black"
            )
        filters.append(
            f"[{index}:v]trim=start={start:.6f}:duration={source_duration:.6f},"
            f"setpts=(PTS-STARTPTS)/{speed:.8f},{canvas_chain},"
            f"setsar=1,fps={fps},format=yuv420p[{vlabel}]"
        )
        if use_timeline_audio:
            volume = 0.0 if bool(clip.get("muted", False)) else max(0.0, float(clip.get("volume", 1.0) or 0.0))
            if _has_audio(str(clip["source"])):
                filters.append(
                    f"[{index}:a]atrim=start={start:.6f}:duration={source_duration:.6f},"
                    f"asetpts=PTS-STARTPTS,{_atempo(speed)},volume={volume:.6f},"
                    f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[{alabel}]"
                )
            else:
                filters.append(
                    f"anullsrc=r=48000:cl=stereo,atrim=duration={timeline_duration:.6f},"
                    f"asetpts=PTS-STARTPTS[{alabel}]"
                )
            concat_inputs.append(f"[{vlabel}][{alabel}]")
        else:
            concat_inputs.append(f"[{vlabel}]")
    if use_timeline_audio:
        filters.append(f"{''.join(concat_inputs)}concat=n={len(valid)}:v=1:a=1[vcat][acat]")
    else:
        filters.append(f"{''.join(concat_inputs)}concat=n={len(valid)}:v=1:a=0[vcat]")

    current = "vcat"
    mapped_blur_regions = _map_normalized_overlays_to_canvas(
        blur_regions, first_w, first_h, width, height, scale_mode, focus_x, focus_y
    )
    mapped_mask_regions = _map_normalized_overlays_to_canvas(
        mask_regions, first_w, first_h, width, height, scale_mode, focus_x, focus_y
    )
    color_chain = _build_video_color_chain(video_filter_state or {})
    if color_chain:
        filters.append(f"[{current}]{color_chain}[vcolor]")
        current = "vcolor"
    blur_chain = _build_blur_filter_chain(mapped_blur_regions, width, height)
    if blur_chain:
        filters.append(f"[{current}]{blur_chain}[vblur]")
        current = "vblur"
    mask_chain = _build_mask_filter_chain(mapped_mask_regions, width, height)
    if mask_chain:
        rewritten = mask_chain.replace("[0:v]", f"[{current}]", 1)
        filters.append(rewritten)
        import re
        labels = re.findall(r"\[m\d+\]", rewritten)
        if labels:
            current = labels[-1].strip("[]")
    lut_chain = _build_video_lut_chain(video_filter_state or {})
    if lut_chain:
        filters.append(f"[{current}]{lut_chain}[vlut]")
        current = "vlut"
    if ass_path and os.path.isfile(ass_path) and mode in {"subtitle", "both"}:
        filters.append(f"[{current}]{_ass_filter_expression(ass_path)}[vsub]")
        current = "vsub"

    for offset, (kind, layer) in enumerate(overlay_inputs):
        input_index = overlay_start_index + offset
        image_label = f"overlay_image_{offset}"
        next_label = f"overlay_video_{offset}"
        if kind == "logo":
            overlay_w = max(1, int(round(float(layer.get("width", 0.2) or 0.2) * width)))
            overlay_h = max(1, int(round(float(layer.get("height", 0.2) or 0.2) * height)))
            x = int(round(float(layer.get("x", 0.0) or 0.0) * width))
            y = int(round(float(layer.get("y", 0.0) or 0.0) * height))
            filters.append(f"[{input_index}:v]scale={overlay_w}:{overlay_h},format=rgba,colorchannelmixer=aa={float(layer.get('opacity', 1.0) or 1.0):.4f}[{image_label}]")
        else:
            x = int(round(float(layer.get("x", 0.0) or 0.0)))
            y = int(round(float(layer.get("y", 0.0) or 0.0)))
            filters.append(f"[{input_index}:v]format=rgba[{image_label}]")
        start = max(0.0, float(layer.get("start", 0.0) or 0.0))
        end = float(layer.get("end", total_duration) or total_duration)
        filters.append(
            f"[{current}][{image_label}]overlay={x}:{y}:shortest=1:"
            f"enable='between(t,{start:.6f},{end:.6f})'[{next_label}]"
        )
        current = next_label
    filters.append(f"[{current}]null[vout]")

    if external_audio_index is not None:
        audio_map = f"{external_audio_index}:a:0"
    else:
        audio_map = "[acat]"
        if abs(float(original_audio_gain_db or 0.0)) > 0.001:
            filters.append(f"[acat]volume={float(original_audio_gain_db):.6f}dB[aout]")
            audio_map = "[aout]"

    video_encoder_args = build_export_h264_encoder_args(
        ffmpeg, export_preset, video_bitrate_kbps
    )
    filter_string = ";".join(filters)
    if len(filter_string) > 8000:
        filter_script_path = os.path.join(tempfile.gettempdir(), f"timeline_export_{int(time.time())}.txt")
        with open(filter_script_path, "w", encoding="utf-8") as f:
            f.write(filter_string)
        command += [
            "-filter_complex_script", filter_script_path, "-map", "[vout]", "-map", audio_map,
            *video_encoder_args,
            "-c:a", "aac", "-b:a", "192k",
            "-t", f"{total_duration:.6f}", "-movflags", "+faststart", output_path,
        ]
    else:
        command += [
            "-filter_complex", filter_string, "-map", "[vout]", "-map", audio_map,
            *video_encoder_args,
            "-c:a", "aac", "-b:a", "192k",
            "-t", f"{total_duration:.6f}", "-movflags", "+faststart", output_path,
        ]
        
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    # Use FFmpeg's machine-readable progress output instead of waiting for a
    # blocking subprocess.  This keeps timeline exports consistent with the
    # regular subtitle export path and reports the actual ``out_time``.
    ok, _stdout, stderr = run_ffmpeg_with_progress(
        command,
        total_duration_seconds=total_duration,
        progress_callback=on_progress,
        cancellation_check=cancellation_check,
        output_path_to_clean=output_path,
    )
    if not ok and "h264_nvenc" in command:
        fallback_args = build_export_h264_encoder_args(
            ffmpeg, export_preset, video_bitrate_kbps, allow_hardware=False
        )
        video_arg_index = command.index("-c:v")
        audio_arg_index = command.index("-c:a", video_arg_index)
        command[video_arg_index:audio_arg_index] = fallback_args
        ok, _stdout, stderr = run_ffmpeg_with_progress(
            command,
            total_duration_seconds=total_duration,
            progress_callback=on_progress,
            cancellation_check=cancellation_check,
            output_path_to_clean=output_path,
        )
    if not ok:
        raise RuntimeError(f"FFmpeg Timeline export failed: {sanitize_ffmpeg_diagnostics(stderr)[-1800:]}")
    if not os.path.isfile(output_path) or os.path.getsize(output_path) <= 0:
        raise RuntimeError("FFmpeg did not create the Timeline output file.")
    return output_path

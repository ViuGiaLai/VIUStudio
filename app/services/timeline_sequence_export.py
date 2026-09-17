from __future__ import annotations

import json
import math
import os
import subprocess
import tempfile
import uuid

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


def _validate_playable_output(path: str, expected_duration: float) -> None:
    """Reject incomplete MP4 files before they replace the requested output.

    FFprobe verifies the container and required streams. FFmpeg then decodes a
    frame near both ends so a present-but-broken video stream is not accepted.
    """
    from app.runtime_paths import bin_path

    output = os.path.abspath(path)
    if not os.path.isfile(output) or os.path.getsize(output) <= 0:
        raise RuntimeError("FFmpeg did not create the Timeline output file.")

    probe = str(bin_path("ffmpeg", "ffprobe.exe"))
    result = subprocess.run(
        [
            probe, "-v", "error",
            "-show_entries", "format=duration:stream=codec_type,width,height,duration",
            "-of", "json", output,
        ],
        capture_output=True,
        check=False,
        timeout=30,
        **subprocess_text_kwargs(),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Exported MP4 could not be opened: {sanitize_ffmpeg_diagnostics(result.stderr)[-800:]}"
        )
    try:
        metadata = json.loads(result.stdout or "{}")
        streams = list(metadata.get("streams") or [])
        duration = float((metadata.get("format") or {}).get("duration") or 0.0)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Exported MP4 has invalid media metadata.") from exc

    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if not video_streams:
        raise RuntimeError("Exported MP4 does not contain a video stream.")
    if not audio_streams:
        raise RuntimeError("Exported MP4 does not contain an audio stream.")
    first_video = video_streams[0]
    if int(first_video.get("width") or 0) <= 0 or int(first_video.get("height") or 0) <= 0:
        raise RuntimeError("Exported MP4 has an invalid video resolution.")
    tolerance = max(0.5, min(5.0, float(expected_duration or 0.0) * 0.002))
    video_duration = float(first_video.get("duration") or duration)
    if (not math.isfinite(duration) or not math.isfinite(video_duration)
            or duration <= 0.0 or video_duration <= 0.0
            or min(duration, video_duration) + tolerance < float(expected_duration or 0.0)):
        raise RuntimeError(
            f"Exported MP4 is incomplete ({duration:.2f}s of {float(expected_duration):.2f}s)."
        )

    ffmpeg = str(bin_path("ffmpeg", "ffmpeg.exe"))
    sample_points = [0.0]
    if video_duration > 2.0:
        sample_points.append(max(0.0, video_duration - 1.0))
    for point in sample_points:
        decoded = subprocess.run(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-xerror",
                "-ss", f"{point:.6f}", "-i", output,
                "-map", "0:v:0", "-frames:v", "1", "-f", "framehash", "-",
            ],
            capture_output=True,
            check=False,
            timeout=45,
            **subprocess_text_kwargs(),
        )
        # FFmpeg can exit successfully after decoding zero frames at EOF.
        # Require an actual frame checksum, not merely a zero exit status.
        has_frame = any(
            line.strip() and not line.lstrip().startswith("#")
            for line in (decoded.stdout or "").splitlines()
        )
        if decoded.returncode != 0 or not has_frame:
            raise RuntimeError(
                "Exported MP4 failed the playback check: "
                f"{sanitize_ffmpeg_diagnostics(decoded.stderr)[-800:]}"
            )


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
    anti_duplicate_enabled: bool = False,
    anti_duplicate_settings=None,
) -> str:
    """Render sequential V1 clips in one FFmpeg graph, without a merged source file."""
    from video_processor import (
        _ass_filter_expression,
        _build_blur_filter_chain,
        _build_mask_filter_chain,
        _build_video_color_chain,
        _build_video_lut_chain,
        _hardware_decode_args,
        _remove_auto_hwaccel,
        build_export_h264_encoder_args,
        _ffmpeg_path,
        _map_normalized_overlays_to_canvas,
        get_video_dimensions,
        run_ffmpeg_with_progress,
    )

    valid = [dict(clip) for clip in clips or [] if os.path.isfile(str(clip.get("source", "") or ""))]
    if not valid:
        raise ValueError("Timeline has no readable V1 video clips.")

    # Defensive sanitization: if sequential clips have end times that overlap
    # past the subsequent clip's start, clamp each clip's duration so total duration remains exact.
    if len(valid) > 1:
        for i in range(len(valid) - 1):
            cur_st = float(valid[i].get("start", 0.0) or 0.0)
            cur_end = float(valid[i].get("end", 0.0) or 0.0)
            nxt_st = float(valid[i + 1].get("start", 0.0) or 0.0)
            if nxt_st > cur_st and cur_end > nxt_st:
                valid[i]["end"] = nxt_st
    try:
        from services.timeline_video_sequence import is_image_file
    except ImportError:
        from app.services.timeline_video_sequence import is_image_file

    first_w, first_h = get_video_dimensions(valid[0]["source"])
    width = max(2, int(target_width or first_w or 1920))
    height = max(2, int(target_height or first_h or 1080))
    width -= width % 2
    height -= height % 2

    detected_fps = None
    for clip in valid:
        if not is_image_file(str(clip.get("source", ""))):
            v_fps = _source_fps(str(clip.get("source", "")))
            if v_fps > 1:
                detected_fps = v_fps
                break
    if not detected_fps:
        detected_fps = _source_fps(valid[0]["source"])
    if detected_fps < 15:
        detected_fps = 30
    fps = max(1, int(output_fps or detected_fps or 30))
    mode = str(mode or "subtitle").strip().lower()
    scale_mode = str(output_scale_mode or "fit").strip().lower()
    focus_x = max(0.0, min(1.0, float(output_fill_focus_x)))
    focus_y = max(0.0, min(1.0, float(output_fill_focus_y)))

    ffmpeg = _ffmpeg_path()
    video_encoder_args = build_export_h264_encoder_args(
        ffmpeg, export_preset, video_bitrate_kbps
    )
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-threads", "0", "-filter_threads", "0", "-filter_complex_threads", "0"]
    hw_decode = _hardware_decode_args(video_encoder_args)
    for clip in valid:
        source_path = os.path.abspath(str(clip["source"]))
        if hw_decode and not is_image_file(source_path):
            command += list(hw_decode)
        command += ["-i", source_path]
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
        is_clip_img = is_image_file(str(clip.get("source", "")))
        if is_clip_img:
            v_trim_chain = f"[{index}:v]loop=loop=-1:size=1:start=0,trim=start={start:.6f}:duration={source_duration:.6f}"
        else:
            v_trim_chain = f"[{index}:v]trim=start={start:.6f}:duration={source_duration:.6f}"
        filters.append(
            f"{v_trim_chain},"
            f"setpts=(PTS-STARTPTS)/{speed:.8f},{canvas_chain},"
            f"setsar=1,fps={fps},format=yuv420p[{vlabel}]"
        )
        if use_timeline_audio:
            volume = 0.0 if bool(clip.get("muted", False)) else max(0.0, float(clip.get("volume", 1.0) or 0.0))
            if not is_clip_img and _has_audio(str(clip["source"])):
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

    if anti_duplicate_enabled:
        from anti_duplicate import build_anti_duplicate_video_chain, AntiDuplicateSettings
        ad_cfg = anti_duplicate_settings or AntiDuplicateSettings(
            enabled=True, continuous_mode=True, allow_horizontal_flip=True,
            target_width=width, target_height=height,
        )
        ad_chain = build_anti_duplicate_video_chain(ad_cfg, target_w=width, target_h=height)
        if ad_chain:
            filters.append(f"[{current}]{ad_chain}[vad]")
            current = "vad"

    if ass_path and os.path.isfile(ass_path) and mode in {"subtitle", "both"}:
        filters.append(f"[{current}]{_ass_filter_expression(ass_path)}[vsub]")
        current = "vsub"

    for offset, (kind, layer) in enumerate(overlay_inputs):
        input_index = overlay_start_index + offset
        image_label = f"overlay_image_{offset}"
        next_label = f"overlay_video_{offset}"
        if kind == "logo":
            source_file = str(layer.get("source", "") or "").strip()
            box_w = max(2, (int(round(float(layer.get("width", 0.2) or 0.2) * width)) // 2) * 2)
            box_h = max(2, (int(round(float(layer.get("height", 0.2) or 0.2) * height)) // 2) * 2)
            img_w, img_h = None, None
            if source_file and os.path.exists(source_file):
                try:
                    from PIL import Image
                    with Image.open(source_file) as img:
                        img_w, img_h = img.size
                except Exception:
                    pass
            if img_w and img_h and img_w > 0 and img_h > 0:
                img_aspect = img_w / float(img_h)
                fit_w = min(box_w, int(round(box_h * img_aspect)))
                fit_h = min(box_h, int(round(box_w / img_aspect)))
                overlay_w = max(2, (fit_w // 2) * 2)
                overlay_h = max(2, (fit_h // 2) * 2)
            else:
                overlay_w = box_w
                overlay_h = box_h

            x = max(0, min(width - overlay_w, (int(round(float(layer.get("x", 0.0) or 0.0) * width)) // 2) * 2))
            y = max(0, min(height - overlay_h, (int(round(float(layer.get("y", 0.0) or 0.0) * height)) // 2) * 2))
            rot = float(layer.get("rotation", 0.0) or 0.0)
            rot_chain = ""
            if abs(rot) > 0.1:
                rot_rad = rot * 3.141592653589793 / 180.0
                rot_chain = f",rotate={rot_rad:.6f}:c=none:ow={overlay_w}:oh={overlay_h}"
            filters.append(
                f"[{input_index}:v]format=rgba,scale={overlay_w}:{overlay_h}:force_original_aspect_ratio=decrease:flags=lanczos"
                f"{rot_chain},colorchannelmixer=aa={float(layer.get('opacity', 1.0) or 1.0):.4f}[{image_label}]"
            )
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
        current_audio = "acat"
        if anti_duplicate_enabled:
            from anti_duplicate import build_anti_duplicate_audio_filter, AntiDuplicateSettings
            ad_cfg = anti_duplicate_settings or AntiDuplicateSettings(enabled=True, continuous_mode=True)
            ad_af = build_anti_duplicate_audio_filter(ad_cfg)
            if ad_af:
                filters.append(f"[{current_audio}]{ad_af}[aad]")
                current_audio = "aad"
        if abs(float(original_audio_gain_db or 0.0)) > 0.001:
            filters.append(f"[{current_audio}]volume={float(original_audio_gain_db):.6f}dB[aout]")
            current_audio = "aout"
        audio_map = f"[{current_audio}]"

    output_abs = os.path.abspath(output_path)
    input_paths = [str(clip["source"]) for clip in valid]
    if external_audio_index is not None:
        input_paths.append(audio_path)
    input_paths.extend(layer["source"] for _kind, layer in overlay_inputs)
    if any(os.path.normcase(output_abs) == os.path.normcase(os.path.abspath(path)) for path in input_paths):
        raise ValueError("Choose a different output filename from the Timeline source video.")
    os.makedirs(os.path.dirname(output_abs), exist_ok=True)
    partial_path = os.path.join(
        os.path.dirname(output_abs),
        f".{os.path.basename(output_abs)}.{uuid.uuid4().hex}.partial.mp4",
    )
    filter_string = ";".join(filters)
    filter_script_path = ""
    if len(filter_string) > 8000:
        filter_script_path = os.path.join(tempfile.gettempdir(), f"timeline_export_{uuid.uuid4().hex}.txt")
        with open(filter_script_path, "w", encoding="utf-8") as f:
            f.write(filter_string)
        command += [
            "-filter_complex_script", filter_script_path, "-map", "[vout]", "-map", audio_map,
            *video_encoder_args,
            "-c:a", "aac", "-b:a", "192k",
            "-t", f"{total_duration:.6f}", "-movflags", "+faststart", partial_path,
        ]
    else:
        command += [
            "-filter_complex", filter_string, "-map", "[vout]", "-map", audio_map,
            *video_encoder_args,
            "-c:a", "aac", "-b:a", "192k",
            "-t", f"{total_duration:.6f}", "-movflags", "+faststart", partial_path,
        ]

    # Use FFmpeg's machine-readable progress output instead of waiting for a
    # blocking subprocess.  This keeps timeline exports consistent with the
    # regular subtitle export path and reports the actual ``out_time``.
    try:
        ok, _stdout, stderr = run_ffmpeg_with_progress(
            command,
            total_duration_seconds=total_duration,
            progress_callback=on_progress,
            cancellation_check=cancellation_check,
            output_path_to_clean=partial_path,
        )
        if not ok and any(e in command for e in ("h264_nvenc", "h264_qsv", "h264_amf")):
            fallback_args = build_export_h264_encoder_args(
                ffmpeg, export_preset, video_bitrate_kbps, allow_hardware=False
            )
            _remove_auto_hwaccel(command)
            video_arg_index = command.index("-c:v")
            audio_arg_index = command.index("-c:a", video_arg_index)
            command[video_arg_index:audio_arg_index] = fallback_args
            ok, _stdout, stderr = run_ffmpeg_with_progress(
                command,
                total_duration_seconds=total_duration,
                progress_callback=on_progress,
                cancellation_check=cancellation_check,
                output_path_to_clean=partial_path,
            )
        if not ok:
            raise RuntimeError(f"FFmpeg Timeline export failed: {sanitize_ffmpeg_diagnostics(stderr)[-1800:]}")
        _validate_playable_output(partial_path, total_duration)
        if cancellation_check and cancellation_check():
            raise InterruptedError("Export cancelled by user")
        os.replace(partial_path, output_abs)
        return output_abs
    finally:
        if os.path.exists(partial_path):
            try:
                os.remove(partial_path)
            except OSError:
                pass
        if filter_script_path and os.path.exists(filter_script_path):
            try:
                os.remove(filter_script_path)
            except OSError:
                pass

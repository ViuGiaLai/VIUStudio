import os
import math
import subprocess
import tempfile
import wave

from runtime_paths import bin_path, sanitize_ffmpeg_diagnostics, subprocess_text_kwargs


VOICE_TRACK_IN_MEMORY_MAX_SECONDS = 30 * 60
VOICE_TRACK_WRITE_CHUNK_SAMPLES = 1_000_000


def voice_track_storage_plan(duration_seconds: float, sample_rate: int = 16000) -> dict:
    """Describe the bounded storage strategy used by voice-track assembly."""
    samples = max(0, int(float(duration_seconds) * int(sample_rate))) + int(sample_rate)
    use_disk = float(duration_seconds) > VOICE_TRACK_IN_MEMORY_MAX_SECONDS
    return {
        "samples": samples,
        "backend": "disk_chunks" if use_disk else "memory",
        "temporary_disk_bytes": samples * 4 if use_disk else 0,
        "memory_buffer_bytes": 0 if use_disk else samples * 4,
        "peak_chunk_bytes": min(samples, VOICE_TRACK_WRITE_CHUNK_SAMPLES) * 6,
    }


def mute_voice_windows(
    *,
    input_wav_path: str,
    segments: list,
    changed_indices: set[int] | list[int],
    output_wav_path: str,
) -> str:
    """Create a temporary voice track with only edited cue windows muted.

    Subtitle edits should not make every previously generated cue disappear.
    Until the user regenerates TTS, this preserves the unchanged speech and
    silences only the cue whose text is now stale.
    """
    if not input_wav_path or not os.path.exists(input_wav_path):
        raise FileNotFoundError(input_wav_path)
    _require_pydub()
    from pydub import AudioSegment

    audio = AudioSegment.from_file(input_wav_path)
    windows: list[tuple[int, int]] = []
    by_index = {}
    for position, segment in enumerate(list(segments or [])):
        if not isinstance(segment, dict):
            continue
        try:
            index = int(segment.get("_seg_index", position))
        except (TypeError, ValueError):
            index = position
        by_index[index] = segment
    for raw_index in set(changed_indices or []):
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            continue
        segment = by_index.get(index)
        if not segment:
            continue
        try:
            start = float(segment.get("_audio_start", segment.get("start", 0.0)))
            end = float(segment.get("_audio_end", segment.get("end", start)))
        except (TypeError, ValueError):
            continue
        if end > start + 0.005:
            windows.append((max(0, int(round(start * 1000))), max(0, int(round(end * 1000)))))
    if not windows:
        raise ValueError("No valid voice window matched the edited subtitle cues.")
    for start_ms, end_ms in sorted(windows, reverse=True):
        start_ms = min(start_ms, len(audio))
        end_ms = min(max(start_ms, end_ms), len(audio))
        if end_ms <= start_ms:
            continue
        audio = audio[:start_ms] + AudioSegment.silent(duration=end_ms - start_ms, frame_rate=audio.frame_rate) + audio[end_ms:]
    os.makedirs(os.path.dirname(os.path.abspath(output_wav_path)) or ".", exist_ok=True)
    audio.export(output_wav_path, format="wav")
    return output_wav_path


def _ffmpeg_path():
    return bin_path("ffmpeg", "ffmpeg.exe")


def _ffprobe_path():
    return bin_path("ffmpeg", "ffprobe.exe")


def extract_audio_from_video(video_path: str, output_wav_path: str, sample_rate: int = 44100) -> str:
    """Extract audio track from a video file to a WAV file using ffmpeg.

    Args:
        video_path: Path to the source video file.
        output_wav_path: Destination WAV path.
        sample_rate: Output sample rate (default 44100 to preserve quality).

    Returns:
        output_wav_path on success, raises RuntimeError on failure.
    """
    ffmpeg = _ffmpeg_path()
    if not os.path.exists(ffmpeg):
        raise FileNotFoundError(f"FFmpeg not found at {ffmpeg}")
    os.makedirs(os.path.dirname(output_wav_path) or ".", exist_ok=True)
    cmd = [
        ffmpeg, "-y",
        "-i", video_path,
        "-vn",               # strip video
        "-ar", str(sample_rate),
        "-ac", "2",          # stereo
        "-sample_fmt", "s16",
        output_wav_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, **subprocess_text_kwargs())
    if proc.returncode != 0:
        raise RuntimeError(
            f"FFmpeg audio extraction failed:\n{sanitize_ffmpeg_diagnostics(proc.stderr) or proc.stdout}"
        )
    return output_wav_path


def _subprocess_run_kwargs() -> dict:
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs["startupinfo"] = startupinfo
    return kwargs


def _probe_wav_duration_seconds(wav_path: str) -> float:
    with wave.open(wav_path, "rb") as wav_file:
        frame_rate = wav_file.getframerate() or 16000
        frame_count = wav_file.getnframes()
    return max(0.0, float(frame_count) / float(frame_rate))


def ffprobe_wav_duration(wav_path: str) -> float:
    """Return the actual duration of a wav file via ffprobe.

    Uses ffprobe's `format=duration` for the most accurate reading —
    important for segment preview/regenerate flows where the wav
    may have been re-encoded and the wave header is stale. Returns
    0.0 if ffprobe is missing or the call fails.
    """
    ffprobe = _ffprobe_path()
    if not os.path.exists(ffprobe):
        return 0.0
    try:
        out = subprocess.run(
            [
                ffprobe, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                wav_path,
            ],
            capture_output=True, timeout=10,
            **subprocess_text_kwargs(),
        )
        if out.returncode != 0:
            return 0.0
        return max(0.0, float(out.stdout.strip()))
    except (ValueError, subprocess.TimeoutExpired, OSError):
        return 0.0


def _build_atempo_filter(speed_ratio: float) -> str:
    ratio = max(0.01, float(speed_ratio))
    filters = []
    while ratio < 0.5 or ratio > 2.0:
        if ratio < 0.5:
            filters.append("atempo=0.5")
            ratio /= 0.5
        else:
            filters.append("atempo=2.0")
            ratio /= 2.0
    filters.append(f"atempo={ratio:.6f}")
    return ",".join(filters)


def fit_wav_to_duration(
    *,
    input_wav_path: str,
    output_wav_path: str,
    target_duration_seconds: float,
    mode: str = "off",
    smart_min_ratio: float = 0.77,
    smart_max_ratio: float = 1.15,
) -> str:
    mode_key = (mode or "off").strip().lower()
    if mode_key == "force fit":
        mode_key = "force"
    if mode_key not in {"smart", "force", "timeline"}:
        return input_wav_path
    if not os.path.exists(input_wav_path):
        raise FileNotFoundError(f"Input wav not found: {input_wav_path}")

    source_duration = _probe_wav_duration_seconds(input_wav_path)
    target_duration = max(0.0, float(target_duration_seconds))
    if source_duration <= 0.0 or target_duration <= 0.0:
        return input_wav_path

    fit_ratio = target_duration / source_duration
    ffmpeg = _ffmpeg_path()
    if not os.path.exists(ffmpeg):
        raise FileNotFoundError(f"FFmpeg not found at {ffmpeg}")

    os.makedirs(os.path.dirname(output_wav_path) or ".", exist_ok=True)

    if mode_key == "timeline":
        # Timeline Priority used to call FFmpeg with ``-t`` here, which
        # discarded every word after the cue deadline. Fit only inside the
        # same natural-sounding band as Smart; an extreme overrun is returned
        # intact and the voice scheduler queues the following cue instead.
        if abs(fit_ratio - 1.0) < 0.02:
            return input_wav_path
        source_to_target_ratio = source_duration / target_duration
        if source_duration > target_duration:
            if fit_ratio < smart_min_ratio:
                return input_wav_path
        elif source_to_target_ratio < smart_min_ratio:
            return input_wav_path
        filter_chain = _build_atempo_filter(source_to_target_ratio)
        cmd = [
            ffmpeg, "-y", "-i", input_wav_path,
            "-filter:a", filter_chain,
            "-ar", "16000", "-ac", "1",
            output_wav_path,
        ]
    elif mode_key == "smart":
        # ``fit_ratio`` is target/source.  The old branches treated it as
        # source/target, so short speech was sent through ``-t`` (which cannot
        # add duration) and the subtitle stayed visible after speech ended.
        # Use atempo in both directions, but only inside the natural-sounding
        # safety band.
        if abs(fit_ratio - 1.0) < 0.02:
            return input_wav_path
        source_to_target_ratio = source_duration / target_duration
        if source_duration > target_duration:
            # Speech is longer: speed it up only when the required change is
            # within the configured safe range.
            if fit_ratio < smart_min_ratio:
                return input_wav_path
            atempo_ratio = source_to_target_ratio
        else:
            # Speech is shorter: slow it down to fill the subtitle window.
            # Very large slow-downs sound robotic, so those are handled later
            # by aligning the visual subtitle end to the real speech end.
            if source_to_target_ratio < smart_min_ratio:
                return input_wav_path
            atempo_ratio = source_to_target_ratio
        filter_chain = _build_atempo_filter(atempo_ratio)
        cmd = [
            ffmpeg, "-y", "-i", input_wav_path,
            "-filter:a", filter_chain,
            "-ar", "16000", "-ac", "1",
            output_wav_path,
        ]
    else:
        # Force mode: use atempo to speed up the audio so it fits the
        # target duration. This is the legacy behaviour.
        if abs(fit_ratio - 1.0) < 0.02:
            return input_wav_path
        if fit_ratio > 1.0 and fit_ratio > smart_max_ratio:
            return input_wav_path
        filter_chain = _build_atempo_filter(1.0 / fit_ratio)
        cmd = [
            ffmpeg, "-y", "-i", input_wav_path,
            "-filter:a", filter_chain,
            "-ar", "16000", "-ac", "1",
            output_wav_path,
        ]

    proc = subprocess.run(cmd, capture_output=True, timeout=120, **subprocess_text_kwargs())
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg fit failed:\n{proc.stderr or proc.stdout}")
    return output_wav_path


def cap_wav_to_duration(
    *,
    input_wav_path: str,
    output_wav_path: str,
    target_duration_seconds: float,
    fade_out_seconds: float = 0.06,
) -> str:
    """Hard-limit a WAV without changing its speaking rate.

    This is a last-resort collision guard used only after the natural timing
    and rewrite passes.  A short fade removes the click that a raw sample cut
    would otherwise create.
    """
    if not os.path.exists(input_wav_path):
        raise FileNotFoundError(f"Input wav not found: {input_wav_path}")

    source_duration = _probe_wav_duration_seconds(input_wav_path)
    target_duration = max(0.0, float(target_duration_seconds))
    if source_duration <= 0.0 or target_duration <= 0.0:
        return input_wav_path
    if source_duration <= target_duration + 0.01:
        return input_wav_path

    ffmpeg = _ffmpeg_path()
    if not os.path.exists(ffmpeg):
        raise FileNotFoundError(f"FFmpeg not found at {ffmpeg}")

    fade_duration = min(max(0.015, float(fade_out_seconds)), target_duration / 3.0)
    fade_start = max(0.0, target_duration - fade_duration)
    filter_chain = (
        f"afade=t=out:st={fade_start:.6f}:d={fade_duration:.6f},"
        f"atrim=end={target_duration:.6f},asetpts=N/SR/TB"
    )
    os.makedirs(os.path.dirname(output_wav_path) or ".", exist_ok=True)
    cmd = [
        ffmpeg, "-y", "-i", input_wav_path,
        "-filter:a", filter_chain,
        "-ar", "16000", "-ac", "1",
        output_wav_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, timeout=120, **subprocess_text_kwargs())
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg duration cap failed:\n{proc.stderr or proc.stdout}")
    return output_wav_path


def change_wav_speed(
    *,
    input_wav_path: str,
    output_wav_path: str,
    speed_ratio: float,
) -> str:
    if not os.path.exists(input_wav_path):
        raise FileNotFoundError(f"Input wav not found: {input_wav_path}")

    ratio = max(0.01, float(speed_ratio))
    if abs(ratio - 1.0) < 0.02:
        return input_wav_path

    ffmpeg = _ffmpeg_path()
    if not os.path.exists(ffmpeg):
        raise FileNotFoundError(f"FFmpeg not found at {ffmpeg}")

    os.makedirs(os.path.dirname(output_wav_path) or ".", exist_ok=True)
    filter_chain = _build_atempo_filter(ratio)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        input_wav_path,
        "-filter:a",
        filter_chain,
        "-ar",
        "16000",
        "-ac",
        "1",
        output_wav_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, timeout=120, **subprocess_text_kwargs())
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg speed adjustment failed:\n{proc.stderr or proc.stdout}")
    return output_wav_path


def trim_trailing_silence(
    *,
    input_wav_path: str,
    output_wav_path: str,
    silence_threshold: float = -40.0,
    min_silence_duration: float = 0.5,
) -> str:
    """Remove trailing silence from a wav file using ffmpeg
    silencedetect. Keeps audio up to the last detected sound, then
    trims after a short padding. Returns output_wav_path if trimming
    was applied, or input_wav_path if the file has no trailing silence.
    """
    if not os.path.exists(input_wav_path):
        return input_wav_path
    ffmpeg = _ffmpeg_path()
    if not os.path.exists(ffmpeg):
        return input_wav_path
    os.makedirs(os.path.dirname(output_wav_path) or ".", exist_ok=True)
    detect_cmd = [
        ffmpeg, "-y", "-i", input_wav_path,
        "-af", f"silencedetect=noise={silence_threshold}dB:d={min_silence_duration}",
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(
            detect_cmd, capture_output=True, timeout=60,
            **subprocess_text_kwargs(),
        )
    except subprocess.TimeoutExpired:
        return input_wav_path
    if proc.returncode != 0:
        return input_wav_path

    last_end = 0.0
    for line in proc.stderr.splitlines():
        if "silence_end" in line:
            try:
                parts = line.split()
                for i, p in enumerate(parts):
                    if p == "silence_end":
                        last_end = float(parts[i + 1])
                        break
            except (ValueError, IndexError):
                continue
    if last_end <= 0.0:
        return input_wav_path

    padding = 0.1
    trim_to = last_end + padding
    cmd = [
        ffmpeg, "-y", "-i", input_wav_path,
        "-t", str(trim_to),
        "-ar", "16000", "-ac", "1",
        output_wav_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, timeout=120, **subprocess_text_kwargs())
    if proc.returncode != 0:
        return input_wav_path
    return output_wav_path


def _require_pydub():
    try:
        ffmpeg = _ffmpeg_path()
        ffprobe = _ffprobe_path()
        ffmpeg_dir = os.path.dirname(ffmpeg)
        if ffmpeg_dir and os.path.isdir(ffmpeg_dir):
            current_path = os.environ.get("PATH", "")
            path_entries = current_path.split(os.pathsep) if current_path else []
            normalized_dir = os.path.normcase(os.path.normpath(ffmpeg_dir))
            normalized_entries = {
                os.path.normcase(os.path.normpath(entry))
                for entry in path_entries
                if entry
            }
            if normalized_dir not in normalized_entries:
                os.environ["PATH"] = ffmpeg_dir + os.pathsep + current_path if current_path else ffmpeg_dir

        from pydub import AudioSegment
        # Point pydub to our bundled ffmpeg to avoid PATH warnings on Windows.
        if os.path.exists(ffmpeg):
            AudioSegment.converter = ffmpeg
            AudioSegment.ffmpeg = ffmpeg
        if os.path.exists(ffprobe):
            AudioSegment.ffprobe = ffprobe
    except Exception as e:
        raise ImportError(
            "Missing dependency 'pydub'.\n"
            "Please run:\n"
            "python -m pip install pydub\n"
            f"Original error: {e}"
        ) from e


def _merge_ducking_ranges(
    *,
    segments: list,
    audio_length_ms: int,
    attack_ms: int,
    release_ms: int,
) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for seg in segments or []:
        try:
            start_ms = int(max(0.0, float(seg.get("start", 0.0))) * 1000.0)
            end_ms = int(max(0.0, float(seg.get("end", 0.0))) * 1000.0)
        except (TypeError, ValueError, AttributeError):
            continue
        if end_ms <= start_ms:
            continue
        duck_start = max(0, start_ms - max(0, attack_ms))
        duck_end = min(audio_length_ms, end_ms + max(0, release_ms))
        if duck_end <= duck_start:
            continue
        if not ranges or duck_start > ranges[-1][1]:
            ranges.append((duck_start, duck_end))
        else:
            prev_start, prev_end = ranges[-1]
            ranges[-1] = (prev_start, max(prev_end, duck_end))
    return ranges


def _apply_timeline_ducking(
    *,
    background_audio,
    ducking_ranges: list[tuple[int, int]],
    duck_amount_db: float,
    attack_ms: int,
    release_ms: int,
):
    if not ducking_ranges:
        return background_audio

    processed = background_audio
    for duck_start, duck_end in ducking_ranges:
        clip = processed[duck_start:duck_end]
        if len(clip) <= 0:
            continue

        attenuated = clip + float(duck_amount_db)
        fade_in_ms = min(max(0, attack_ms), len(attenuated))
        fade_out_ms = min(max(0, release_ms), len(attenuated))
        if fade_in_ms > 0:
            attenuated = attenuated.fade(from_gain=0.0, to_gain=float(duck_amount_db), start=0, duration=fade_in_ms)
        if fade_out_ms > 0:
            fade_out_start = max(0, len(attenuated) - fade_out_ms)
            attenuated = attenuated.fade(
                from_gain=float(duck_amount_db),
                to_gain=0.0,
                start=fade_out_start,
                duration=fade_out_ms,
            )
        processed = processed[:duck_start] + attenuated + processed[duck_end:]
    return processed


def build_voice_track_from_srt_segments(
    *,
    segments: list,
    tts_wav_paths: list,
    output_wav_path: str,
    total_duration_ms: int | None = None,
    gain_db: float = 0.0,
) -> str:
    """
    Build a single voice track by overlaying each segment wav at its start time.

    Long projects use a random-access temporary PCM store and chunked output;
    short projects use a pre-allocated numpy buffer for maximum speed.
    """
    _require_pydub()
    from pydub import AudioSegment
    import numpy as np

    if len(segments) != len(tts_wav_paths):
        raise ValueError("segments and tts_wav_paths length mismatch")

    def _seg_val(s, key, default=0.0):
        if isinstance(s, dict):
            return s.get(key, default)
        return getattr(s, key, default)

    # Assembly consumes an already fitted schedule. Never queue a late sentence
    # here: that used to compound into seconds of drift across dense cues.
    placements: list[float] = []
    previous_audio_end = 0.0
    max_end = 0.0
    for seg, wav_path in zip(segments, tts_wav_paths):
        requested_start = float(_seg_val(seg, "start", 0.0) or 0.0)
        declared_end = float(_seg_val(seg, "end", 0.0) or 0.0)
        if not math.isfinite(requested_start) or not math.isfinite(declared_end):
            raise ValueError("Voice cue timing must be finite.")
        if requested_start < 0 or declared_end <= requested_start:
            raise ValueError("Voice cue has an invalid subtitle window.")
        start = requested_start
        placements.append(start)
        actual_end = declared_end
        cue_text = str(_seg_val(seg, "dubbing_vi", "") or _seg_val(seg, "text", "") or "").strip()
        if cue_text and not wav_path and not bool(_seg_val(seg, "tts_suppressed", False)):
            raise ValueError("A spoken subtitle cue has no generated voice clip.")
        if wav_path:
            if not os.path.isfile(wav_path):
                raise FileNotFoundError(f"Voice clip not found: {wav_path}")
            if start < previous_audio_end - 0.002:
                raise ValueError("Voice clips overlap. Align voice to subtitle timing before export.")
            measured_end = start + _probe_wav_duration_seconds(wav_path)
            if measured_end > declared_end + 0.002:
                raise ValueError("Voice exceeds subtitle end. Regenerate voice with timing alignment.")
            actual_end = max(actual_end, measured_end)
            previous_audio_end = measured_end
        max_end = max(max_end, declared_end, actual_end)
    if total_duration_ms is None:
        total_duration_ms = int(round(max_end * 1000))
    else:
        # A regenerated TTS clip may be slightly longer than its subtitle slot.
        # Size once before allocating so a disk memmap never needs a costly copy.
        if int(total_duration_ms) < int(round(max_end * 1000)):
            raise ValueError("Output duration would cut off subtitle speech.")

    sr = 16000
    total_samples = int(round(max(0, total_duration_ms) * sr / 1000))
    os.makedirs(os.path.dirname(output_wav_path) or ".", exist_ok=True)
    duration_seconds = total_samples / sr
    use_disk = duration_seconds > VOICE_TRACK_IN_MEMORY_MAX_SECONDS
    storage_path = ""
    storage_file = None
    if use_disk:
        temp_file = tempfile.NamedTemporaryFile(
            prefix=".viustudio_voice_",
            suffix=".i32",
            dir=os.path.dirname(os.path.abspath(output_wav_path)),
            delete=False,
        )
        storage_path = temp_file.name
        temp_file.seek(total_samples * 4 - 1)
        temp_file.write(b"\0")
        temp_file.close()
        storage_file = open(storage_path, "r+b", buffering=0)
        audio_buffer = None
    else:
        audio_buffer = np.zeros(total_samples, dtype=np.int32)

    try:
        for idx, (seg, wav_path) in enumerate(zip(segments, tts_wav_paths)):
            if not wav_path or not os.path.exists(wav_path):
                continue
            start_ms = placements[idx] * 1000
            try:
                clip = AudioSegment.from_file(wav_path)
                clip = clip.set_frame_rate(sr).set_channels(1).set_sample_width(2)
                if gain_db:
                    clip = clip + gain_db

                # The destination is already silent between cues. Do not fade
                # sentence endings or append padding that changes scheduling.
                clip_samples = np.frombuffer(clip.raw_data, dtype=np.int16)
                start_sample = int(round(max(0, start_ms) * sr / 1000))
                end_sample = min(total_samples, start_sample + len(clip_samples))
                if end_sample > start_sample:
                    usable = end_sample - start_sample
                    incoming = clip_samples[:usable].astype(np.int32)
                    if storage_file is not None:
                        storage_file.seek(start_sample * 4)
                        existing_raw = storage_file.read(usable * 4)
                        existing = np.frombuffer(existing_raw, dtype=np.int32).copy()
                        existing += incoming
                        storage_file.seek(start_sample * 4)
                        storage_file.write(existing.tobytes())
                    else:
                        audio_buffer[start_sample:end_sample] += incoming
            except Exception as e:
                raise RuntimeError(f"Could not assemble voice cue {idx + 1}: {e}") from e

        # Write in small chunks.  The previous full-buffer astype().tobytes()
        # temporarily allocated another ~550 MB for a five-hour mono track.
        with wave.open(output_wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            if storage_file is not None:
                storage_file.seek(0)
            for start in range(0, total_samples, VOICE_TRACK_WRITE_CHUNK_SAMPLES):
                count = min(VOICE_TRACK_WRITE_CHUNK_SAMPLES, total_samples - start)
                if storage_file is not None:
                    raw = storage_file.read(count * 4)
                    chunk = np.frombuffer(raw, dtype=np.int32)
                else:
                    chunk = np.asarray(audio_buffer[start:start + count])
                pcm = np.clip(chunk, -32768, 32767).astype(np.int16)
                wf.writeframes(pcm.tobytes())
    finally:
        if storage_file is not None:
            storage_file.close()
        if storage_path:
            try:
                os.remove(storage_path)
            except OSError:
                pass

    return output_wav_path


def _long_audio_timeout_seconds(*paths: str) -> int:
    duration = 0.0
    for path in paths:
        try:
            duration = max(duration, _probe_wav_duration_seconds(path))
        except (OSError, wave.Error):
            continue
    # Audio-only FFmpeg is normally much faster than real time.  Scale the
    # guard for slow disks while retaining an upper bound for a hung process.
    return int(max(300, min(86400, duration * 0.25 + 300)))


def _stream_mix_with_ffmpeg(
    *,
    first_path: str,
    second_path: str,
    output_path: str,
    first_gain_db: float,
    second_gain_db: float,
    sidechain: bool = False,
    threshold: float = 0.015,
    ratio: float = 10.0,
    attack_ms: float = 15.0,
    release_ms: float = 350.0,
) -> str:
    """Mix two audio files with bounded RAM through FFmpeg streaming."""
    ffmpeg = _ffmpeg_path()
    if not os.path.exists(ffmpeg):
        raise FileNotFoundError(f"FFmpeg not found at {ffmpeg}")
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    first_volume = f"volume={float(first_gain_db):+.2f}dB"
    second_volume = f"volume={float(second_gain_db):+.2f}dB"
    if sidechain:
        filter_complex = (
            f"[0:a]{first_volume}[first];"
            f"[1:a]{second_volume},asplit=2[second_sc][second_mix];"
            f"[first][second_sc]sidechaincompress="
            f"threshold={max(0.0001, float(threshold)):.4f}:"
            f"ratio={max(1.0, float(ratio)):.2f}:"
            f"attack={max(0.0, float(attack_ms)):.1f}:"
            f"release={max(0.0, float(release_ms)):.1f}:makeup=1[ducked];"
            "[ducked][second_mix]amix=inputs=2:duration=longest:"
            "dropout_transition=0:normalize=0[mixed]"
        )
    else:
        filter_complex = (
            f"[0:a]{first_volume}[first];[1:a]{second_volume}[second];"
            "[first][second]amix=inputs=2:duration=longest:"
            "dropout_transition=0:normalize=0[mixed]"
        )
    command = [
        ffmpeg, "-y", "-loglevel", "error", "-i", first_path, "-i", second_path,
        "-filter_complex", filter_complex, "-map", "[mixed]",
        "-c:a", "pcm_s16le", "-ar", "16000", "-ac", "1", output_path,
    ]
    proc = subprocess.run(
        command,
        capture_output=True,
        timeout=_long_audio_timeout_seconds(first_path, second_path),
        **subprocess_text_kwargs(),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg streaming audio mix failed:\n{proc.stderr or proc.stdout}")
    return output_path


def mix_voice_with_background(
    *,
    background_wav_path: str,
    voice_wav_path: str,
    output_wav_path: str,
    background_gain_db: float = 0.0,
    voice_gain_db: float = 0.0,
    ducking_mode: str = "off",
    ducking_segments: list | None = None,
    ducking_amount_db: float = 0.0,
    ducking_threshold: float = 0.015,
    ducking_ratio: float = 10.0,
    ducking_attack_ms: float = 15.0,
    ducking_release_ms: float = 350.0,
) -> str:
    if not os.path.exists(background_wav_path):
        raise FileNotFoundError(f"Background file not found: {background_wav_path}")
    if not os.path.exists(voice_wav_path):
        raise FileNotFoundError(f"Voice file not found: {voice_wav_path}")

    mode_key = str(ducking_mode or "off").strip().lower()
    if mode_key in {"timeline", "segments", "subtitle"}:
        try:
            long_duration = max(
                _probe_wav_duration_seconds(background_wav_path),
                _probe_wav_duration_seconds(voice_wav_path),
            )
        except (OSError, wave.Error):
            long_duration = 0.0
        if long_duration > VOICE_TRACK_IN_MEMORY_MAX_SECONDS:
            # Exact timeline ducking uses pydub slicing and copies the complete
            # track repeatedly.  For long projects use its streaming sidechain
            # equivalent; voice activity itself drives the same audible result.
            return _stream_mix_with_ffmpeg(
                first_path=background_wav_path,
                second_path=voice_wav_path,
                output_path=output_wav_path,
                first_gain_db=background_gain_db,
                second_gain_db=voice_gain_db,
                sidechain=True,
                threshold=ducking_threshold,
                ratio=ducking_ratio,
                attack_ms=ducking_attack_ms,
                release_ms=ducking_release_ms,
            )
        _require_pydub()
        from pydub import AudioSegment

        bg = AudioSegment.from_file(background_wav_path).set_frame_rate(16000).set_channels(1)
        vc = AudioSegment.from_file(voice_wav_path).set_frame_rate(16000).set_channels(1)

        if background_gain_db:
            bg = bg + background_gain_db
        if voice_gain_db:
            vc = vc + voice_gain_db

        if len(vc) > len(bg):
            bg = bg + AudioSegment.silent(duration=(len(vc) - len(bg)), frame_rate=16000)
        elif len(bg) > len(vc):
            vc = vc + AudioSegment.silent(duration=(len(bg) - len(vc)), frame_rate=16000)

        ducking_ranges = _merge_ducking_ranges(
            segments=list(ducking_segments or []),
            audio_length_ms=len(bg),
            attack_ms=int(max(0.0, float(ducking_attack_ms))),
            release_ms=int(max(0.0, float(ducking_release_ms))),
        )
        ducked_bg = _apply_timeline_ducking(
            background_audio=bg,
            ducking_ranges=ducking_ranges,
            duck_amount_db=float(ducking_amount_db),
            attack_ms=int(max(0.0, float(ducking_attack_ms))),
            release_ms=int(max(0.0, float(ducking_release_ms))),
        )

        mixed = ducked_bg.overlay(vc)
        os.makedirs(os.path.dirname(output_wav_path) or ".", exist_ok=True)
        mixed.export(output_wav_path, format="wav")
        return output_wav_path

    if mode_key in {"auto", "duck", "ducking", "sidechain"}:
        return _stream_mix_with_ffmpeg(
            first_path=background_wav_path,
            second_path=voice_wav_path,
            output_path=output_wav_path,
            first_gain_db=background_gain_db,
            second_gain_db=voice_gain_db,
            sidechain=True,
            threshold=ducking_threshold,
            ratio=ducking_ratio,
            attack_ms=ducking_attack_ms,
            release_ms=ducking_release_ms,
        )

    return _stream_mix_with_ffmpeg(
        first_path=background_wav_path,
        second_path=voice_wav_path,
        output_path=output_wav_path,
        first_gain_db=background_gain_db,
        second_gain_db=voice_gain_db,
    )


def mix_original_with_dub(
    *,
    original_wav_path: str,
    dub_wav_path: str,
    output_wav_path: str,
    original_gain_db: float = 0.0,
    dub_gain_db: float = 0.0,
) -> str:
    """Mix original audio (A1) with dub audio (A2) at specified gain levels."""
    if not os.path.exists(original_wav_path):
        raise FileNotFoundError(f"Original file not found: {original_wav_path}")
    if not os.path.exists(dub_wav_path):
        raise FileNotFoundError(f"Dub file not found: {dub_wav_path}")

    return _stream_mix_with_ffmpeg(
        first_path=original_wav_path,
        second_path=dub_wav_path,
        output_path=output_wav_path,
        first_gain_db=original_gain_db,
        second_gain_db=dub_gain_db,
    )


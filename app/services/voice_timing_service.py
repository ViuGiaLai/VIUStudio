"""Anchor complete speech clips to subtitle time, never accumulate a queue."""
from __future__ import annotations

import math
import os
import wave


VOICE_TIMING_REVISION = 7


def wav_duration(path: str) -> float:
    with wave.open(path, "rb") as stream:
        return stream.getnframes() / stream.getframerate()


def cue_windows(segments: list[dict]) -> list[tuple[float, float]]:
    windows = []
    for index, segment in enumerate(segments):
        start, end = float(segment["start"]), float(segment["end"])
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            raise ValueError(f"Cue {index + 1}: invalid subtitle timing ({start}, {end}).")
        if windows and start < windows[-1][0]:
            raise ValueError(f"Cue {index + 1}: subtitles must be ordered by start time.")
        windows.append((start, end))
    return windows


def align_voice_clips(*, segments, wavs, engine, tmp_dir, mode="smart",
                      requested_speed=1.0, provider_speed=1.0, cancellation_check=None):
    """Keep text and subtitle timestamps unchanged; fit only overflowing audio.

    Smart automatically increases speed just enough to meet every deadline.
    It never shifts the next sentence or trims words. Short clips remain at
    their chosen speaking speed, followed by silence.
    """
    if len(segments) != len(wavs):
        raise ValueError("Subtitle and voice clip counts differ.")
    windows = cue_windows(segments)
    fitted = list(wavs)
    mode = str(mode or "off").strip().lower()
    problems = []
    next_spoken = [None] * len(wavs)
    following = None
    for index in range(len(wavs) - 1, -1, -1):
        next_spoken[index] = following
        if wavs[index]:
            following = index
    for index, (seg, path) in enumerate(zip(segments, wavs)):
        if cancellation_check and cancellation_check():
            raise InterruptedError("Voice alignment cancelled.")
        for key in ("_audio_start", "_audio_end"):
            seg.pop(key, None)
        if not path:
            if (not seg.get("tts_suppressed") and
                    str(seg.get("dubbing_vi") or seg.get("text") or "").strip()):
                raise ValueError(f"Cue {index + 1}: voice audio is missing.")
            continue
        if not os.path.isfile(path) or wav_duration(path) <= 0:
            raise ValueError(f"Cue {index + 1}: invalid voice audio.")
        start, end = windows[index]
        # Empty cues do not reserve an audio slot. Source-overlapping spoken
        # cues still have a deadline at the following spoken cue's onset.
        next_index = next_spoken[index]
        deadline = min(end, windows[next_index][0]) if next_index is not None else end
        available = deadline - start
        if available <= 0:
            problems.append(f"Cue {index + 1}: overlapping speech starts at {start:.3f}s")
            continue
        speed = float(seg.get("voice_speed") or requested_speed)
        if not math.isfinite(speed) or speed <= 0:
            raise ValueError(f"Cue {index + 1}: invalid voice speed.")
        residual = speed / float(provider_speed)
        current = path
        if abs(residual - 1.0) >= 0.02:
            current = engine.change_wav_speed(
                input_wav_path=current,
                output_wav_path=os.path.join(tmp_dir, f"aligned_{index:04d}_speed.wav"),
                speed_ratio=residual,
            )
        if mode != "off":
            current = engine.trim_trailing_silence(
                input_wav_path=current,
                output_wav_path=os.path.join(tmp_dir, f"aligned_{index:04d}_trim.wav"),
            )
        duration = wav_duration(current)
        ratio = duration / available
        if duration > available + 0.002:
            if mode == "off":
                problems.append(
                    f"Cue {index + 1} [{start:.3f}-{end:.3f}s]: speech {duration:.3f}s, "
                    f"slot {available:.3f}s, needs {ratio:.2f}x"
                )
                continue
            # A small margin covers atempo's sample rounding. Never use -t or
            # atrim to discard speech at the end of the sentence.
            # FFmpeg atempo rounds at packet/sample boundaries. Re-measure and
            # make one correction so milliseconds cannot accumulate per cue.
            for attempt in range(2):
                target = max(0.001, available - max(0.012, available * 0.01))
                current = engine.change_wav_speed(
                    input_wav_path=current,
                    output_wav_path=os.path.join(tmp_dir, f"aligned_{index:04d}_fit_{attempt}.wav"),
                    # change_wav_speed intentionally treats <2% as a no-op;
                    # force a real correction when packet rounding overruns.
                    speed_ratio=max(1.021, duration / target),
                )
                duration = wav_duration(current)
                if duration <= available + 0.002:
                    break
            if duration > available + 0.002:
                problems.append(f"Cue {index + 1}: fitted speech still exceeds its subtitle window.")
                continue
        fitted[index] = current
        seg["_audio_start"] = start
        seg["_audio_end"] = start + duration
        seg["tts_duration"] = round(duration, 6)
        seg["ratio"] = round(duration / (end - start), 6)
        seg["action_taken"] = "anchored_fit" if ratio > 1 else "anchored"
        metrics = dict(seg.get("_tts_metrics") or {})
        metrics.pop("voice_queue_delay", None)
        metrics.update(scheduled_audio_start=start, scheduled_audio_end=start + duration,
                       timing_revision=VOICE_TIMING_REVISION, fit_speed_ratio=max(1.0, ratio))
        seg["_tts_metrics"] = metrics
    if problems:
        details = "\n".join(problems)
        report = os.path.join(tmp_dir, "voice_timing_issues.txt")
        with open(report, "w", encoding="utf-8") as stream:
            stream.write(details)
        raise ValueError(
            f"{len(problems)} cue(s) cannot fit their subtitle timing at a natural speed. "
            "Check these subtitle windows or generated WAV files. "
            "No speech was cut or shifted.\n" + "\n".join(problems[:5]) + f"\nFull report: {report}"
        )
    return fitted

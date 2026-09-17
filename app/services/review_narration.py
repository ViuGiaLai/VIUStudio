"""Measured narration assets shared by the editor, captions and export.

No GUI dependencies. Every caption interval is measured from the WAV that
actually gets mixed; source timestamps remain a separate coordinate system.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import wave
from array import array
from pathlib import Path


def _trim_outer_pcm_silence(path: Path) -> None:
    """Remove provider padding, preserving natural pauses inside narration."""
    with wave.open(str(path), "rb") as source:
        params = source.getparams()
        frames = source.readframes(source.getnframes())
    if params.sampwidth != 2 or not frames:
        return
    samples = array("h")
    samples.frombytes(frames)
    channels = max(1, params.nchannels)
    frame_count = len(samples) // channels
    peak = max((abs(value) for value in samples), default=0)
    threshold = max(80, int(peak * 0.012))
    first_sample = next((index for index, value in enumerate(samples) if abs(value) >= threshold), None)
    if first_sample is None:
        return
    last_sample = len(samples) - 1 - next(
        index for index, value in enumerate(reversed(samples)) if abs(value) >= threshold
    )
    padding = int(params.framerate * 0.035)
    start = max(0, first_sample // channels - padding)
    end = min(frame_count, last_sample // channels + padding + 1)
    if start == 0 and end == frame_count:
        return
    trimmed = samples[start * channels:end * channels].tobytes()
    replacement = path.with_suffix(".trim.wav")
    with wave.open(str(replacement), "wb") as output:
        output.setparams(params)
        output.writeframes(trimmed)
    os.replace(replacement, path)


def narration_signature(plan, voice_speed=1.0):
    return hashlib.sha256(json.dumps(
        {"version": "continuous-paragraph-v4", "plan": plan, "voice_speed": voice_speed},
        ensure_ascii=False, sort_keys=True, allow_nan=False,
    ).encode("utf-8")).hexdigest()


def render_narration(plan, output_path, *, voice, voice_speed=1.0,
                     synthesize, cancelled=lambda: False):
    return render_paragraph(plan, output_path, voice=voice, voice_speed=voice_speed,
                            synthesize=synthesize, cancelled=cancelled)


def render_paragraph(plan, output_path, *, voice, voice_speed=1.0,
                     synthesize, cancelled=lambda: False):
    """One synthesis request per paragraph; no cue/sentence WAV joins.

    Caption offsets are estimates within measured paragraph audio, not forced
    alignment. The synthesis model controls internal pauses from punctuation.
    """
    rows = [row for row in plan if str(row.get("text", "")).strip()]
    if not rows:
        raise ValueError("Chưa có đoạn lời kể.")
    if cancelled():
        raise InterruptedError("Đã hủy tạo giọng.")
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    weights = [max(1, len(row["text"].split())) for row in rows]
    total = sum(weights)
    speed = sum(float(row.get("speed", 1)) * weight for row, weight in zip(rows, weights)) / total
    speed = max(0.92, min(1.08, speed * float(voice_speed)))
    spoken_parts = []
    for index, row in enumerate(rows):
        text = str(row.get("tts_text") or row["text"]).strip()
        if index:
            pause = max(int(rows[index - 1].get("pause_after_ms", 0) or 0),
                        int(row.get("pause_before_ms", 0) or 0))
            previous_text = str(rows[index - 1].get("tts_text") or rows[index - 1]["text"]).rstrip()
            separator = " … " if pause >= 500 else (
                ", " if pause >= 220 and not previous_text.endswith((".", "!", "?", "…", ",", ";", ":")) else " "
            )
            text = separator + text
        spoken_parts.append(text)
    with tempfile.TemporaryDirectory(prefix="narrative-", dir=target.parent) as scratch:
        path = Path(scratch) / "paragraph.wav"
        synthesize(text="".join(spoken_parts), wav_path=str(path),
                   voice=voice, speed=speed, tmp_dir=scratch)
        if cancelled():
            raise InterruptedError("Đã hủy tạo giọng.")
        _trim_outer_pcm_silence(path)
        with wave.open(str(path), "rb") as audio:
            if audio.getcomptype() != "NONE" or audio.getnframes() <= 0:
                raise ValueError("TTS phải trả WAV PCM có âm thanh.")
            duration = audio.getnframes() / audio.getframerate()
        os.replace(path, target)
    timings, cursor = [], 0
    for row, weight in zip(rows, weights):
        timings.append({"text": row["text"], "start": duration * cursor / total,
                        "end": duration * (cursor + weight) / total,
                        "source_cue_ids": row.get("source_cue_ids", []),
                        "alignment": "estimated_within_paragraph"})
        cursor += weight
    return duration, timings

"""Shared ZeroTTS metadata used by the UI and synthesis runtime."""

import os

ZEROTTS_MODEL_ID = "zeroweight-ai/ZeroTTS"

#: ZeroTTS decodes one frame per ONNX call (T=1) and then runs a separate codec
#: pass, so a session gains almost nothing from a wide thread pool while a whole
#: cue gains a lot from other cues running next to it.  Measured on a 12-thread
#: CPU, spending the same thread budget per second of audio: 3 cues with 4
#: threads per session needed 1.8s, 6 cues with 2 threads needed 1.25s.  The win
#: is spreading the budget over cues instead of over synchronisation inside one
#: session.
MAX_SYNTH_WORKERS = 6
SYNTH_THREADS = 2


def _env_int(name: str) -> int | None:
    raw = str(os.getenv(name, "") or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def synth_workers(job_count: int) -> int:
    """How many cues to synthesize at once.

    Half the logical CPUs, capped by :data:`MAX_SYNTH_WORKERS`, because each cue
    already occupies more than one thread.  ``VIUSTUDIO_ZEROTTS_WORKERS``
    overrides the measurement when a machine behaves differently.
    """
    if job_count <= 0:
        return 0
    cpu_count = os.cpu_count() or 4
    configured = _env_int("VIUSTUDIO_ZEROTTS_WORKERS")
    if configured is None:
        configured = min(MAX_SYNTH_WORKERS, cpu_count // 2)
    return max(1, min(configured, job_count, cpu_count))


def synth_threads() -> int:
    """ONNX threads per session for the frame/step graphs.

    Kept small on purpose: oversubscribing these sessions costs more in
    synchronisation than it returns, and the freed CPU goes to other cues.
    """
    configured = _env_int("VIUSTUDIO_ZEROTTS_THREADS")
    if configured is not None:
        return configured
    return SYNTH_THREADS if (os.cpu_count() or 4) >= 4 else 1


def codec_threads() -> int:
    """ONNX threads for the waveform codec, measured best at the step count."""
    configured = _env_int("VIUSTUDIO_ZEROTTS_CODEC_THREADS")
    return configured if configured is not None else synth_threads()


ZEROTTS_VOICES = (
    ("maichi", "Mai Chi", "female", ("young", "gentle", "storytelling")),
    ("baotrang", "Bảo Trang", "female", ("mature", "clear", "news")),
    ("kimoanh", "Kim Oanh", "female", ("warm", "emotional", "storytelling")),
    ("hamy", "Hà My", "female", ("young", "expressive", "animation")),
    ("giahuy", "Gia Huy", "male", ("young", "warm", "storytelling")),
    ("huuduc", "Hữu Đức", "male", ("deep", "calm", "storytelling")),
    ("quangminh", "Quang Minh", "male", ("young", "clear", "news")),
    ("tiendat", "Tiến Đạt", "male", ("young", "lively", "commentary")),
)


def catalog_entries() -> list[dict]:
    return [
        {
            "id": f"zerotts:{voice_id}",
            "name": f"{display_name} (ZeroTTS)",
            "provider": "zerotts",
            "provider_voice": voice_id,
            "language": "vi",
            "gender": gender,
            "tier": "free",
            "preview_video_url": "",
            "preview_video_path": "",
            "preview_audio_url": "",
            "preview_audio_path": "",
            "enabled": True,
            "tags": ["local", "zerotts", *tags],
        }
        for voice_id, display_name, gender, tags in ZEROTTS_VOICES
    ]

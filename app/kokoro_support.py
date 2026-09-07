"""Local Kokoro-82M resource discovery shared by UI and TTS runtime."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from runtime_paths import models_path


MODEL_FILENAME = "kokoro-v1_0.pth"
CONFIG_FILENAME = "config.json"
VOICE_METADATA = {
    "af_heart": ("Heart (Kokoro · US)", "female"),
    "am_michael": ("Michael (Kokoro · US)", "male"),
}


def model_root() -> str:
    return models_path("kokoro")


def config_path() -> str:
    return os.path.join(model_root(), CONFIG_FILENAME)


def model_path() -> str:
    return os.path.join(model_root(), MODEL_FILENAME)


def voices_dir() -> str:
    return os.path.join(model_root(), "voices")


def voice_path(voice_id: str) -> str:
    """Resolve a voice by id and tolerate the legacy flat folder layout."""
    voice_name = os.path.basename(str(voice_id or "").strip())
    if voice_name.lower().endswith(".pt"):
        voice_name = voice_name[:-3]
    if not voice_name:
        return ""
    for candidate in (
        os.path.join(voices_dir(), f"{voice_name}.pt"),
        os.path.join(model_root(), f"{voice_name}.pt"),
    ):
        if os.path.isfile(candidate) and os.path.getsize(candidate) > 0:
            return candidate
    return os.path.join(voices_dir(), f"{voice_name}.pt")


def discovered_voice_ids() -> list[str]:
    found: set[str] = set()
    for directory in (voices_dir(), model_root()):
        if not os.path.isdir(directory):
            continue
        try:
            for path in Path(directory).glob("*.pt"):
                if path.is_file() and path.stat().st_size > 0:
                    found.add(path.stem)
        except OSError:
            continue
    return sorted(found)


def catalog_entries() -> list[dict]:
    entries: list[dict] = []
    for voice_id in discovered_voice_ids():
        default_name = voice_id.replace("_", " ").title()
        name, gender = VOICE_METADATA.get(voice_id, (default_name, ""))
        entries.append(
            {
                "id": f"kokoro_{voice_id}",
                "name": name,
                "provider": "kokoro",
                "provider_voice": voice_id,
                "language": "en",
                "gender": gender,
                "tier": "free",
                "enabled": True,
                "tags": ["local", "kokoro", "english"],
            }
        )
    return entries


def model_files_ready() -> bool:
    return all(
        os.path.isfile(path) and os.path.getsize(path) > 0
        for path in (config_path(), model_path())
    )


def runtime_available() -> bool:
    try:
        return importlib.util.find_spec("kokoro") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def english_g2p_available() -> bool:
    try:
        return importlib.util.find_spec("en_core_web_sm") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def installation_ready() -> bool:
    return (
        runtime_available()
        and english_g2p_available()
        and model_files_ready()
        and bool(discovered_voice_ids())
    )

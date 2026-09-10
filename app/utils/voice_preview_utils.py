import hashlib
import json
import os
import tempfile

from runtime_paths import app_path


def manifest_path(tmp_dir: str) -> str:
    return os.path.join(tmp_dir, "tts_cache_manifest.json")


def load_manifest(tmp_dir: str) -> dict:
    path = manifest_path(tmp_dir)
    if not os.path.exists(path):
        return {"segments": {}, "by_cache_key": {}}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            payload.setdefault("segments", {})
            payload.setdefault("by_cache_key", {})
            return payload
    except Exception as exc:
        print(f"[VoicePreviewUtils] load_manifest failed: {exc}")
    return {"segments": {}, "by_cache_key": {}}


def save_manifest(tmp_dir: str, manifest: dict) -> None:
    path = manifest_path(tmp_dir)
    os.makedirs(tmp_dir, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=tmp_dir,
                                     suffix=".json", delete=False) as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        staging = handle.name
    os.replace(staging, path)


def segment_cache_key(*, text: str, voice_name: str, provider_speed: float) -> str:
    # v2 retires positional WAVs and silence cached as successful synthesis.
    payload = f"content-v2|{voice_name}|{provider_speed:.6f}|{text.strip()}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def voice_provider(voice_name: str) -> str:
    raw = str(voice_name or "").strip()
    if raw.lower().startswith("f5:"):
        return "f5"
    if ":" in raw:
        provider, _ = raw.split(":", 1)
        return provider.strip().lower() or "edge"
    catalog_paths = [
        app_path("voice_preview_catalog.json"),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "voice_preview_catalog.json"),
        os.path.join(os.getcwd(), "app", "voice_preview_catalog.json"),
    ]
    for catalog_path in catalog_paths:
        try:
            if os.path.exists(catalog_path):
                with open(catalog_path, "r", encoding="utf-8") as f:
                    catalog = json.load(f)
                for voice in catalog.get("voices", []):
                    if voice.get("id") == raw:
                        return voice.get("provider", "edge").strip().lower()
        except Exception as exc:
            print(f"[VoicePreviewUtils] catalog read error {catalog_path}: {exc}")
    return "piper"


def provider_native_speed(*, provider: str, requested_speed: float) -> float:
    if provider in {"edge", "f5", "zerotts", "kokoro"}:
        return float(requested_speed)
    return 1.0


def clamp_requested_speed(requested_speed: float) -> float:
    speed_value = max(0.5, float(requested_speed or 1.0))
    if speed_value > 1.30:
        print(f"[VoicePreviewUtils] Requested speed {speed_value:.2f} exceeds safe cap. Clamping to 1.30.")
        return 1.30
    return speed_value

from __future__ import annotations

import json
import importlib.util
import ensurepip
import fnmatch
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
import stat
from pathlib import Path

from runtime_paths import app_path, bin_path, bundle_root, join_root, models_path, subprocess_hidden_kwargs, subprocess_text_kwargs


class ResourceDownloadService:
    WHISPER_ZIP_FILES = {
        "base": "models--Systran--faster-whisper-base.zip",
        "small": "models--Systran--faster-whisper-small.zip",
        "medium": "models--Systran--faster-whisper-medium.zip",
    }

    HF_RESOURCE_REPO = os.getenv("VIUSTUDIO_RESOURCE_REPO", "Hacht/CapCapResource").strip() or "Hacht/CapCapResource"
    HF_RESOURCE_REVISION = os.getenv("VIUSTUDIO_RESOURCE_REVISION", "main").strip() or "main"
    SENSEVOICE_REPO = os.getenv(
        "SENSEVOICE_MODEL_REPO",
        "csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2025-09-09",
    ).strip() or "csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2025-09-09"
    SENSEVOICE_MODEL_URL = (
        "https://huggingface.co/csukuangfj/"
        "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2025-09-09/"
        "resolve/main/model.int8.onnx?download=true"
    )
    SENSEVOICE_TOKENS_URL = (
        "https://huggingface.co/csukuangfj/"
        "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2025-09-09/"
        "resolve/main/tokens.txt?download=true"
    )
    SILERO_VAD_URL = (
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
        "asr-models/silero_vad.onnx"
    )

    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.repo_id = self.HF_RESOURCE_REPO
        self.revision = self.HF_RESOURCE_REVISION

    def _catalog_path(self) -> str:
        download_catalog = app_path("voice_download_catalog.json")
        if os.path.exists(download_catalog):
            return download_catalog
        release_catalog = app_path("voice_preview_catalog.release.json")
        if os.path.exists(release_catalog):
            return release_catalog
        return app_path("voice_preview_catalog.json")

    def _read_catalog(self) -> dict:
        path = self._catalog_path()
        if not os.path.exists(path):
            return {"voices": []}
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
        return {"voices": []}

    def _voice_local_paths(self, voice_entry: dict) -> tuple[str, str]:
        provider_voice = str(voice_entry.get("provider_voice", "")).strip().replace("/", os.sep)
        normalized = os.path.normpath(provider_voice)
        filename = os.path.basename(normalized)
        if normalized.startswith(f"models{os.sep}"):
            relative = normalized[len("models" + os.sep):]
            model_path = models_path(*Path(relative).parts)
        else:
            model_path = models_path("piper", filename)
        # Voice-pack archives commonly contain one wrapper directory with the
        # same name as their destination (piper/piper or piper-en/piper-en).
        # Resolve both layouts. The previous hard-coded Vietnamese-only
        # fallback made a successfully extracted English pack fail verification
        # and later made TTS unable to load the models it had just installed.
        parent_dir = os.path.dirname(model_path)
        parent_name = os.path.basename(parent_dir)
        candidates = [model_path]
        if parent_name:
            candidates.append(os.path.join(parent_dir, parent_name, filename))
        candidates.append(models_path("piper", "piper", filename))  # legacy bundle layout
        seen: set[str] = set()
        for candidate in candidates:
            normalized_candidate = os.path.normcase(os.path.abspath(candidate))
            if normalized_candidate in seen:
                continue
            seen.add(normalized_candidate)
            config_path = f"{candidate}.json"
            if os.path.isfile(candidate) or os.path.isfile(config_path):
                return candidate, config_path
        return model_path, f"{model_path}.json"

    def _voice_remote_paths(self, voice_entry: dict) -> tuple[str, str]:
        provider_voice = str(voice_entry.get("provider_voice", "")).strip().replace("\\", "/")
        model_name = os.path.basename(provider_voice)
        remote_model = provider_voice
        if remote_model.startswith("models/"):
            remote_model = remote_model[len("models/"):]
        if not remote_model:
            remote_model = f"piper/{model_name}"
        return (
            remote_model,
            f"{remote_model}.json",
        )

    def _finalize_voice_download(self, downloaded_path: str, voice_entry: dict, *, is_config: bool) -> str:
        source_path = str(downloaded_path or "").strip()
        if not source_path or not os.path.exists(source_path):
            return source_path
        model_path, config_path = self._voice_local_paths(voice_entry)
        target_path = config_path if is_config else model_path
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        normalized_source = os.path.normcase(os.path.abspath(source_path))
        normalized_target = os.path.normcase(os.path.abspath(target_path))
        if normalized_source != normalized_target:
            if os.path.exists(target_path):
                os.remove(target_path)
            shutil.move(source_path, target_path)
            self._cleanup_empty_voice_cache_dirs(os.path.dirname(source_path))
        return target_path

    def _download_hf_file(
        self,
        *,
        repo_id: str,
        revision: str,
        filename: str,
        local_dir: str,
        hf_hub_download,
        hf_hub_url,
        get_hf_file_metadata,
        progress_cb=None,
        start_percent: int = 0,
        end_percent: int = 100,
        label: str = "Downloading file...",
    ) -> str:
        expected_path = os.path.join(local_dir, filename.replace("/", os.sep))
        try:
            file_url = hf_hub_url(repo_id=repo_id, filename=filename, revision=revision)
            metadata = get_hf_file_metadata(url=file_url)
            expected_size = int(getattr(metadata, "size", 0) or 0)
        except Exception:
            expected_size = 0

        stop_event = threading.Event()

        def _emit_progress(raw_percent: int, message: str) -> None:
            if not progress_cb:
                return
            scaled = start_percent + int(((end_percent - start_percent) * max(0, min(100, raw_percent))) / 100)
            progress_cb(scaled, message)

        def _watch_file() -> None:
            last_percent = -1
            while not stop_event.is_set():
                current_size = 0
                try:
                    if os.path.exists(expected_path):
                        current_size = os.path.getsize(expected_path)
                    elif os.path.exists(expected_path + ".incomplete"):
                        current_size = os.path.getsize(expected_path + ".incomplete")
                except Exception:
                    current_size = 0
                if expected_size > 0:
                    raw_percent = int((current_size / expected_size) * 100)
                    raw_percent = max(0, min(99, raw_percent))
                    if raw_percent != last_percent:
                        _emit_progress(raw_percent, f"{label} ({raw_percent}%)")
                        last_percent = raw_percent
                elif last_percent != -2:
                    if progress_cb:
                        progress_cb(-1, label)
                    last_percent = -2
                time.sleep(0.2)

        watcher = threading.Thread(target=_watch_file, daemon=True)
        watcher.start()
        try:
            downloaded = hf_hub_download(
                repo_id=repo_id,
                revision=revision,
                filename=filename,
                local_dir=local_dir,
            )
        finally:
            stop_event.set()
            watcher.join(timeout=1.0)
        _emit_progress(100, f"{label} (100%)")
        return downloaded

    def _cleanup_empty_voice_cache_dirs(self, start_dir: str) -> None:
        base_dir = os.path.normcase(os.path.abspath(join_root("models")))
        current = os.path.abspath(str(start_dir or ""))
        while current and os.path.normcase(current).startswith(base_dir):
            try:
                if os.path.isdir(current) and not os.listdir(current):
                    os.rmdir(current)
                    parent = os.path.dirname(current)
                    if parent == current:
                        break
                    current = parent
                    continue
            except Exception:
                break
            break

    def _piper_voice_entries(self, language: str = "") -> list[dict]:
        payload = self._read_catalog()
        items: list[dict] = []
        language = str(language or "").strip().lower()
        for voice in payload.get("voices", []) or []:
            if not isinstance(voice, dict):
                continue
            if str(voice.get("provider", "")).strip().lower() != "piper":
                continue
            voice_id = str(voice.get("id", "")).strip()
            if not voice_id:
                continue
            voice_language = str(voice.get("language", "")).strip().lower().split("-", 1)[0]
            if language and voice_language != language:
                continue
            items.append(voice)
        return items

    def _voice_pack_status(self, language: str = "") -> str:
        entries = self._piper_voice_entries(language)
        if not entries:
            return "missing"
        installed = sum(1 for entry in entries if self.is_resource_installed(f"voice:{str(entry.get('id', '')).strip()}"))
        if installed <= 0:
            return "missing"
        if installed >= len(entries):
            return "installed"
        return "partial"

    def _usable_piper_voice_count(self, language: str = "") -> int:
        """Count local Piper voices that can actually be loaded.

        Resource-pack completeness is not meaningful to users: they may
        intentionally install only a subset or add their own voices. A voice
        is usable when its ONNX model and matching JSON config are both
        present in the language's storage folder.
        """
        normalized_language = str(language or "").strip().lower().split("-", 1)[0]
        folder_name = "piper-en" if normalized_language == "en" else "piper"
        roots = [
            os.path.join(self.workspace_root, "models", folder_name),
            os.path.join(bundle_root(), "models", folder_name),
        ]
        seen_names: set[str] = set()
        for root in roots:
            if not os.path.isdir(root):
                continue
            try:
                for model_path in Path(root).rglob("*.onnx"):
                    if not model_path.is_file() or model_path.stat().st_size <= 0:
                        continue
                    config_path = Path(f"{model_path}.json")
                    if not config_path.is_file() or config_path.stat().st_size <= 0:
                        continue
                    seen_names.add(str(model_path.name).lower())
            except OSError:
                continue
        return len(seen_names)

    def _whisper_cache_root(self) -> str:
        return models_path("faster_whisper")

    def _speaker_diarization_root(self) -> str:
        return models_path("pyannote")

    def _speaker_diarization_segmentation_path(self) -> str:
        return os.path.join(
            self._speaker_diarization_root(),
            "model.int8.onnx",
        )

    def _speaker_diarization_embedding_path(self) -> str:
        return os.path.join(
            self._speaker_diarization_root(),
            "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx",
        )

    def _whisper_cache_dirs(self, model_name: str) -> list[str]:
        root = Path(self._whisper_cache_root())
        if not root.exists():
            return []
        normalized = str(model_name or "").strip().lower()
        matches: list[str] = []
        for child in root.iterdir():
            if not child.is_dir():
                continue
            name = child.name.lower()
            if normalized == name:
                matches.append(str(child))
                continue
            if name.startswith("models--") and normalized in name:
                matches.append(str(child))
        return matches

    _OCR_MODEL_SETS = [
        ("ch_PP-OCRv4_det_mobile.onnx", "ch_PP-OCRv4_rec_mobile.onnx"),
        ("PP-OCRv6_det_small.onnx", "PP-OCRv6_rec_small.onnx"),
    ]
    _OCR_CLASSIFIER_MODEL = "ch_ppocr_mobile_v2.0_cls_mobile.onnx"

    def _ocr_model_dir(self) -> str:
        # Do not make a lightweight availability check depend on importing the
        # entire RapidOCR runtime. In a frozen build a missing lazy submodule
        # used to turn an import exception into the misleading message
        # "Rapid OCR engine missing", even when all bundled models existed.
        candidates = [
            os.path.join(bundle_root(), "rapidocr"),
            os.path.join(self.workspace_root, "rapidocr"),
        ]
        import sys
        meipass = getattr(sys, "_MEIPASS", "") or ""
        if meipass:
            candidates.append(os.path.join(meipass, "rapidocr"))
        for candidate in candidates:
            if os.path.isdir(os.path.join(candidate, "models")):
                return candidate
        try:
            import rapidocr
            models_dir = os.path.dirname(rapidocr.__file__)
            if models_dir and os.path.isdir(os.path.join(models_dir, "models")):
                return models_dir
        except Exception:
            pass
        return ""

    def _ocr_model_status(self) -> str:
        models_dir = self._ocr_model_dir()
        if not models_dir:
            return "missing"
        models_path_dir = os.path.join(models_dir, "models")
        detector_and_recognizer_ready = any(
            all(os.path.isfile(os.path.join(models_path_dir, name)) for name in model_set)
            for model_set in self._OCR_MODEL_SETS
        )
        classifier_ready = os.path.isfile(
            os.path.join(models_path_dir, self._OCR_CLASSIFIER_MODEL)
        )
        return "installed" if detector_and_recognizer_ready and classifier_ready else "missing"

    def is_ocr_ready(self) -> bool:
        return self._ocr_model_status() == "installed"

    @staticmethod
    def is_sensevoice_runtime_ready() -> bool:
        """Verify the bundled runtime can be imported before entering editor."""
        try:
            import sherpa_onnx  # noqa: F401
            return True
        except Exception:
            return False

    def validate_sensevoice_runtime(self) -> list[tuple[str, str]]:
        """Return actionable first-run checks for the bundled default ASR."""
        issues: list[tuple[str, str]] = []
        model_dir = models_path("sensevoice")
        model_path = os.path.join(model_dir, "model.int8.onnx")
        tokens_path = os.path.join(model_dir, "tokens.txt")
        if not os.path.isfile(model_path):
            issues.append(("sensevoice:model", f"SenseVoice model is missing: {model_path}"))
        if not os.path.isfile(tokens_path):
            issues.append(("sensevoice:tokens", f"SenseVoice tokens file is missing: {tokens_path}"))
        try:
            import sherpa_onnx  # noqa: F401
        except Exception as exc:
            issues.append(("sensevoice:runtime", f"SenseVoice runtime could not load: {exc}"))
        silero_path = bin_path("silero_vad.onnx")
        if not os.path.isfile(silero_path):
            issues.append(("sensevoice:vad", f"Silero VAD model is missing: {silero_path}"))
        return issues

    def validate_ocr_runtime(self) -> list[tuple[str, str]]:
        """Verify selected OCR can start, not just that a model folder exists."""
        issues: list[tuple[str, str]] = []
        model_dir = self._ocr_model_dir()
        if self._ocr_model_status() != "installed":
            issues.append(("ocr:models", f"RapidOCR models are missing from: {model_dir or 'bundled OCR resources'}"))
        try:
            from rapidocr import RapidOCR  # noqa: F401
        except Exception as exc:
            issues.append(("ocr:runtime", f"RapidOCR runtime could not load: {exc}"))
        return issues

    def validate_piper_voice_runtime(self, voice_id: str) -> list[tuple[str, str]]:
        """Check the chosen local Piper voice before a default Both run."""
        voice_id = str(voice_id or "").strip()
        if not voice_id or voice_id.startswith(("edge:", "f5:")):
            return []
        issues: list[tuple[str, str]] = []
        entry = self._find_voice_entry(voice_id)
        if not entry:
            return [(f"voice:{voice_id}", f"Selected local voice is not available: {voice_id}")]
        model_path, config_path = self._voice_local_paths(entry)
        if not os.path.isfile(model_path):
            issues.append((f"voice:{voice_id}:model", f"Piper voice model is missing: {model_path}"))
        if not os.path.isfile(config_path):
            issues.append((f"voice:{voice_id}:config", f"Piper voice config is missing: {config_path}"))
        try:
            from piper import PiperVoice  # noqa: F401
        except Exception as exc:
            issues.append(("piper:runtime", f"Piper runtime could not load: {exc}"))
        return issues

    def validate_tts_voice_runtime(self, voice_id: str) -> list[tuple[str, str]]:
        """Validate the selected provider without treating every local voice as Piper."""
        voice_id = str(voice_id or "").strip()
        if not voice_id or voice_id.startswith("f5:"):
            return []
        if voice_id.startswith("edge:"):
            try:
                if importlib.util.find_spec("edge_tts") is None:
                    raise ModuleNotFoundError("edge_tts")
            except (ImportError, ModuleNotFoundError, ValueError):
                return [
                    (
                        "tts:edge",
                        "Edge TTS runtime is unavailable. Install requirements-local.txt, then try again.",
                    )
                ]
            return []
        if voice_id.startswith("zerotts:"):
            try:
                if importlib.util.find_spec("zerotts") is None:
                    raise ModuleNotFoundError("zerotts")
            except (ImportError, ModuleNotFoundError, ValueError):
                return [
                    (
                        "tts:zerotts",
                        "ZeroTTS runtime is not installed. Install it from Manage Resources.",
                    )
                ]
            return []
        if voice_id.startswith("kokoro:"):
            from kokoro_support import config_path, english_g2p_available, model_path, runtime_available, voice_path

            selected_voice = voice_id.split(":", 1)[1].strip() or "af_heart"
            issues: list[tuple[str, str]] = []
            if not runtime_available():
                issues.append(("tts:kokoro", "Kokoro runtime is not installed. Install it from Manage Resources."))
            if not english_g2p_available():
                issues.append(("tts:kokoro:g2p", "Kokoro English pronunciation model is not installed."))
            if not os.path.isfile(config_path()):
                issues.append(("tts:kokoro:config", f"Kokoro config is missing: {config_path()}"))
            if not os.path.isfile(model_path()):
                issues.append(("tts:kokoro:model", f"Kokoro model is missing: {model_path()}"))
            if not os.path.isfile(voice_path(selected_voice)):
                issues.append((f"voice:{selected_voice}", f"Kokoro voice is missing: {voice_path(selected_voice)}"))
            return issues
        return self.validate_piper_voice_runtime(voice_id)

    @staticmethod
    def _zerotts_model_ready() -> bool:
        model_dir = models_path("zerotts")
        required = (
            "config.json",
            "null_voice_emb.npy",
            os.path.join("onnx", "text_encoder.onnx"),
            os.path.join("onnx", "prefix_step.onnx"),
            os.path.join("onnx", "local_frame_decode.onnx"),
        )
        return all(os.path.isfile(os.path.join(model_dir, relative)) for relative in required)

    def validate_pipeline_runtime(self) -> list[tuple[str, str]]:
        """Check local executables and writable working folders before a worker starts."""
        issues: list[tuple[str, str]] = []
        ffmpeg_path = bin_path("ffmpeg", "ffmpeg.exe")
        if not os.path.isfile(ffmpeg_path):
            issues.append(("ffmpeg", f"FFmpeg is missing: {ffmpeg_path}"))
        else:
            try:
                result = subprocess.run(
                    [ffmpeg_path, "-version"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                    **subprocess_hidden_kwargs(),
                )
                if result.returncode != 0:
                    issues.append(("ffmpeg", "FFmpeg could not start. Reinstall or re-extract VIUStudio."))
            except Exception as exc:
                issues.append(("ffmpeg", f"FFmpeg could not start: {exc}"))

        # A GUI can launch from a protected folder, then fail only when the
        # worker first writes project/temp output. Detect that exact case up
        # front and give the user a recovery path instead of a generic 500.
        for directory_name in ("projects", "temp"):
            target_dir = os.path.join(self.workspace_root, directory_name)
            probe_path = os.path.join(target_dir, f".viustudio_write_probe_{uuid.uuid4().hex}")
            try:
                os.makedirs(target_dir, exist_ok=True)
                with open(probe_path, "x", encoding="utf-8") as handle:
                    handle.write("ok")
                os.remove(probe_path)
            except OSError as exc:
                try:
                    if os.path.exists(probe_path):
                        os.remove(probe_path)
                except OSError:
                    pass
                issues.append((
                    f"workspace:{directory_name}",
                    f"VIUStudio cannot write its {directory_name} folder ({target_dir}): {exc}. "
                    "Move VIUStudio to a writable folder or adjust folder permissions.",
                ))
        return issues

    @staticmethod
    def is_nvidia_driver_available() -> bool:
        import subprocess
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, timeout=10,
                **subprocess_text_kwargs(),
            )
            if result.returncode == 0 and result.stdout.strip():
                return True
        except Exception:
            pass
        try:
            import torch
            if torch.cuda.is_available():
                return True
        except Exception:
            pass
        return False

    def get_device_requirements(self, device: str) -> list[tuple[str, str]]:
        dev = str(device or "").strip().lower()
        if dev == "cpu":
            return [
                # SenseVoice is the bundled default transcription engine.
                # RapidOCR is validated only when the user explicitly picks
                # OCR as the subtitle source.
                ("sensevoice:model", "SenseVoice model"),
                ("sensevoice:runtime", "SenseVoice runtime"),
                ("sensevoice:vad", "Silero VAD"),
            ]
        return [
            ("sensevoice:model", "SenseVoice model"),
            ("sensevoice:runtime", "SenseVoice runtime"),
            ("sensevoice:vad", "Silero VAD"),
            ("cuda:whisper", "CUDA runtime pack"),
            ("nvidia_driver", "NVIDIA driver"),
        ]

    def is_requirement_met(self, requirement_id: str) -> bool:
        rid = str(requirement_id or "").strip()
        if rid == "ocr":
            return self.is_ocr_ready()
        if rid == "sensevoice:runtime":
            return self.is_sensevoice_runtime_ready()
        if rid == "nvidia_driver":
            return self.is_nvidia_driver_available()
        return self.is_resource_installed(rid)

    def validate_device(self, device: str) -> tuple[bool, list[tuple[str, str]]]:
        missing: list[tuple[str, str]] = []
        for rid, label in self.get_device_requirements(device):
            if not self.is_requirement_met(rid):
                missing.append((rid, label))
        return (len(missing) == 0, missing)

    def _hf_blob_url(self, filename: str) -> str:
        return (
            f"https://huggingface.co/{self.HF_RESOURCE_REPO}/"
            f"resolve/{self.HF_RESOURCE_REVISION}/{filename.lstrip('/')}"
        )

    def list_resources(self) -> list[dict]:
        resources: list[dict] = [
            {
                "id": "preview:mpv",
                "name": "Advanced Video Preview (MPV)",
                "kind": "preview",
                "status": "installed" if self.is_resource_installed("preview:mpv") else "missing",
                "target_dir": bin_path("mpv"),
                "expected_filename": "libmpv-2.dll (or mpv-2.dll) and its DLL dependencies",
                "download_url": "https://mpv.io/installation/",
                "auto_download_supported": False,
                "description": (
                    "Optional advanced preview runtime. Without it VIUStudio uses the compatible "
                    "Qt preview; editing and export remain available. Extract a Windows libmpv "
                    "build and its DLLs into the target folder, then click Refresh."
                ),
            },
            {
                "id": "separation:uvr_mdx",
                "name": "Voice / Music Separation (UVR MDX)",
                "kind": "separation",
                "status": "installed" if self.is_resource_installed("separation:uvr_mdx") else "missing",
                "target_dir": bin_path(),
                "expected_filename": "UVR-MDX-NET-Inst_HQ_3.onnx",
                "download_url": "https://huggingface.co/Politrees/UVR_resources/resolve/main/models/MDXNet/UVR-MDX-NET-Inst_HQ_3.onnx?download=true",
                "auto_download_supported": True,
                "description": "Optional local model for separating Voice.wav and Music.wav.",
            },
            {
                "id": "sensevoice:model",
                "name": "SenseVoice (Required)",
                "kind": "sensevoice",
                "required_for": "CPU Mode",
                "status": "installed" if self.is_resource_installed("sensevoice:model") else "missing",
                "target_dir": models_path("sensevoice"),
                "expected_filename": "model.int8.onnx and tokens.txt",
                "download_links": [
                    {"label": "Download model (237 MB)", "url": self.SENSEVOICE_MODEL_URL},
                    {"label": "Download tokens.txt", "url": self.SENSEVOICE_TOKENS_URL},
                ],
                "auto_download_supported": True,
                "description": (
                    "Required for CPU transcription. VIUStudio can download and install both files automatically."
                ),
            },
            {
                "id": "sensevoice:vad",
                "name": "Silero VAD (Required)",
                "kind": "sensevoice",
                "required_for": "SenseVoice transcription",
                "status": "installed" if self.is_resource_installed("sensevoice:vad") else "missing",
                "target_dir": bin_path(),
                "expected_filename": "silero_vad.onnx",
                "download_links": [
                    {"label": "Download silero_vad.onnx", "url": self.SILERO_VAD_URL},
                ],
                "auto_download_supported": True,
                "description": (
                    "Detects speech segments before transcription. VIUStudio can download it automatically."
                ),
            },
            {
                "id": "whisper:base",
                "name": "Whisper Base",
                "kind": "whisper_cpu",
                "status": "installed" if self.is_resource_installed("whisper:base") else "missing",
                "target_dir": self._whisper_cache_root(),
                "download_url": "https://huggingface.co/Hacht/CapCapResource/blob/main/zipResource/models--Systran--faster-whisper-base.zip",
                "expected_filename": self.WHISPER_ZIP_FILES["base"],
                "auto_download_supported": False,
                "description": "Speech-recognition model for CPU transcription.",
            },
            {
                "id": "whisper:small",
                "name": "Whisper Small",
                "kind": "whisper_cpu",
                "status": "installed" if self.is_resource_installed("whisper:small") else "missing",
                "target_dir": self._whisper_cache_root(),
                "download_url": "https://huggingface.co/Hacht/CapCapResource/blob/main/zipResource/models--Systran--faster-whisper-small.zip",
                "expected_filename": self.WHISPER_ZIP_FILES["small"],
                "auto_download_supported": False,
                "description": "Faster speech-recognition model for CPU transcription.",
            },
            {
                "id": "whisper:medium",
                "name": "Whisper Medium",
                "kind": "whisper",
                "status": "installed" if self.is_resource_installed("whisper:medium") else "missing",
                "target_dir": self._whisper_cache_root(),
                "download_url": self._hf_blob_url("zipResource/models--Systran--faster-whisper-medium.zip"),
                "expected_filename": "models--Systran--faster-whisper-medium.zip",
                "auto_download_supported": False,
                "description": "Speech-recognition model used to create the original transcript.",
            },
            {
                "id": "cuda:whisper",
                "name": "GPU Acceleration Pack (CUDA 12, ~1.6 GB)",
                "kind": "cuda",
                "required_for": "GPU Mode",
                "status": "installed" if self.is_resource_installed("cuda:whisper") else "missing",
                "target_dir": join_root("bin", "cuda12_fw"),
                "download_url": self._hf_blob_url("zipResource/cuda12_fw.zip"),
                "expected_filename": "cuda12_fw.zip",
                "auto_download_supported": True,
                "description": "Required for GPU Mode. Provides the CUDA runtime used to accelerate supported local processing.",
            },
            {
                "id": "diarization:segmentation",
                "name": "Speaker Diarization Segmentation (Sherpa-ONNX)",
                "kind": "diarization",
                "status": "installed" if self.is_resource_installed("diarization:segmentation") else "missing",
                "target_dir": self._speaker_diarization_root(),
                "download_url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2",
                "expected_filename": "sherpa-onnx-pyannote-segmentation-3-0.tar.bz2",
                "auto_download_supported": False,
                "description": "ONNX model that detects potential speaker changes.",
            },
            {
                "id": "diarization:embedding",
                "name": "Speaker Diarization Embedding (3D-Speaker)",
                "kind": "diarization",
                "status": "installed" if self.is_resource_installed("diarization:embedding") else "missing",
                "target_dir": self._speaker_diarization_root(),
                "download_url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx",
                "expected_filename": "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx",
                "auto_download_supported": False,
                "description": "ONNX model that identifies and groups speaker voices.",
            },
            {
                "id": "llama:engine",
                "name": "Llama.cpp Engine (llama-server.exe)",
                "kind": "llama",
                "status": "installed" if self.is_resource_installed("llama:engine") else "missing",
                "target_dir": bin_path("llama_cpp"),
                "expected_filename": "llama-server.exe",
                "download_links": [
                    {
                        "label": "Open llama.cpp releases (win-cpu-x64 zip)",
                        "url": "https://github.com/ggml-org/llama.cpp/releases",
                    },
                ],
                "auto_download_supported": False,
                "description": (
                    "Local translation engine used by the Llama.cpp provider. Download the "
                    "win-cpu-x64 build (llama-b*-bin-win-cpu-x64.zip), then extract "
                    "llama-server.exe and its DLLs into the target folder and click Refresh."
                ),
            },
        ]

        vietnamese_entries = self._piper_voice_entries("vi")
        vietnamese_count = self._usable_piper_voice_count("vi")
        if vietnamese_entries or vietnamese_count:
            count = vietnamese_count
            resources.append(
                {
                    "id": "voice:pack",
                    "name": "Vietnamese Voices (Piper)",
                    "kind": "voice",
                    "status": "installed" if count else "missing",
                    "status_label": f"{count} voice{'s' if count != 1 else ''} available",
                    "target_dir": models_path("piper"),
                    "download_url": self._hf_blob_url("zipResource/piper.zip"),
                    "expected_filename": "piper.zip",
                    "auto_download_supported": True,
                    "description": "Offline Vietnamese voices detected in the Piper storage folder.",
                }
            )
        english_entries = self._piper_voice_entries("en")
        english_count = self._usable_piper_voice_count("en")
        if english_entries or english_count:
            count = english_count
            resources.append(
                {
                    "id": "voice:pack-en",
                    "name": "English Voices (Piper)",
                    "kind": "voice",
                    "status": "installed" if count else "missing",
                    "status_label": f"{count} voice{'s' if count != 1 else ''} available",
                    "target_dir": models_path("piper-en"),
                    "download_url": self._hf_blob_url("zipResource/piper-en.zip"),
                    "expected_filename": "piper-en.zip",
                    "auto_download_supported": True,
                    "description": "Offline English voices detected in the Piper storage folder.",
                }
            )
        external_tts = (
            (
                "tts:zerotts",
                "ZeroTTS [VI]",
                "zerotts",
                "https://pypi.org/project/zerotts/",
                models_path("zerotts"),
                "Natural Vietnamese TTS. Install downloads and verifies both the runtime and local model with visible progress.",
            ),
            (
                "tts:korvatts",
                "KorvaTTS [VI/EN]",
                "korva_tts",
                "https://huggingface.co/nghiakvnvsd/korva-tts-v1",
                models_path("korvatts"),
                "Local Vietnamese and English ONNX TTS. Runtime integration is not yet available in VIUStudio.",
            ),
            (
                "tts:kokoro",
                "Kokoro-82M [EN]",
                "kokoro",
                "https://huggingface.co/hexgrad/Kokoro-82M",
                models_path("kokoro"),
                "Natural local English TTS. Install downloads and verifies the runtime and base model; local .pt voices are discovered automatically.",
            ),
        )
        for resource_id, name, module_name, download_url, target_dir, description in external_tts:
            try:
                runtime_found = importlib.util.find_spec(module_name) is not None
            except (ImportError, ModuleNotFoundError, ValueError):
                runtime_found = False
            integrated = resource_id in {"tts:zerotts", "tts:kokoro"}
            if resource_id == "tts:zerotts":
                model_ready = self._zerotts_model_ready()
            elif resource_id == "tts:kokoro":
                from kokoro_support import model_files_ready, discovered_voice_ids, english_g2p_available
                model_ready = model_files_ready() and bool(discovered_voice_ids()) and english_g2p_available()
            else:
                model_ready = False
            resources.append(
                {
                    "id": resource_id,
                    "name": name,
                    "kind": "voice",
                    "status": (
                        "installed"
                        if runtime_found and integrated and model_ready
                        else ("partial" if runtime_found else "missing")
                    ),
                    "status_label": (
                        "Runtime and model ready"
                        if runtime_found and integrated and model_ready
                        else "Runtime ready; model download required"
                        if runtime_found and integrated
                        else ("Runtime found; adapter pending" if runtime_found else "Not installed")
                    ),
                    "target_dir": target_dir,
                    "download_url": download_url,
                    "auto_download_supported": integrated,
                    "description": description,
                }
            )
        return resources

    def is_resource_installed(self, resource_id: str) -> bool:
        if resource_id == "preview:mpv":
            mpv_dir = bin_path("mpv")
            dll_path = next(
                (
                    path
                    for path in (
                        os.path.join(mpv_dir, "libmpv-2.dll"),
                        os.path.join(mpv_dir, "mpv-2.dll"),
                    )
                    if os.path.isfile(path)
                ),
                "",
            )
            if not dll_path:
                return False
            try:
                if importlib.util.find_spec("mpv") is None:
                    return False
                if os.name == "nt":
                    import ctypes

                    dll_directory = os.add_dll_directory(mpv_dir) if hasattr(os, "add_dll_directory") else None
                    try:
                        ctypes.WinDLL(dll_path)
                    finally:
                        if dll_directory is not None:
                            dll_directory.close()
                return True
            except (ImportError, OSError, RuntimeError, ValueError):
                # A DLL file by itself is not a usable runtime; missing VC
                # runtime/codec dependencies must remain visible as missing.
                return False
        if resource_id == "separation:uvr_mdx":
            return os.path.isfile(bin_path("UVR-MDX-NET-Inst_HQ_3.onnx"))
        if resource_id == "ocr:engine":
            return self.is_ocr_ready()
        if resource_id == "cuda:whisper":
            fw_dir = join_root("bin", "cuda12_fw")
            return os.path.exists(os.path.join(fw_dir, "cublas64_12.dll"))
        if resource_id == "sensevoice:model":
            sensevoice_dir = models_path("sensevoice")
            return (
                os.path.isfile(os.path.join(sensevoice_dir, "model.int8.onnx"))
                and os.path.isfile(os.path.join(sensevoice_dir, "tokens.txt"))
            )
        if resource_id == "sensevoice:vad":
            return os.path.isfile(bin_path("silero_vad.onnx"))
        if resource_id == "diarization:segmentation":
            return os.path.isfile(self._speaker_diarization_segmentation_path())
        if resource_id == "diarization:embedding":
            return os.path.isfile(self._speaker_diarization_embedding_path())
        if resource_id.startswith("whisper:"):
            model_name = resource_id.split(":", 1)[1].strip().lower()
            for model_dir in self._whisper_cache_dirs(model_name):
                try:
                    if os.path.isdir(model_dir) and any(Path(model_dir).iterdir()):
                        return True
                except Exception:
                    continue
            return False
        if resource_id == "voice:pack":
            return self._usable_piper_voice_count("vi") > 0
        if resource_id == "voice:pack-en":
            return self._usable_piper_voice_count("en") > 0
        if resource_id in {"tts:zerotts", "tts:korvatts", "tts:kokoro"}:
            module_name = {
                "tts:zerotts": "zerotts",
                "tts:korvatts": "korva_tts",
                "tts:kokoro": "kokoro",
            }[resource_id]
            try:
                runtime_found = importlib.util.find_spec(module_name) is not None
            except (ImportError, ModuleNotFoundError, ValueError):
                return False
            if resource_id == "tts:zerotts":
                return runtime_found and self._zerotts_model_ready()
            if resource_id == "tts:kokoro":
                from kokoro_support import installation_ready
                return installation_ready()
            return runtime_found
        if resource_id.startswith("voice:"):
            voice_id = resource_id.split(":", 1)[1].strip()
            voice_entry = self._find_voice_entry(voice_id)
            if not voice_entry:
                return False
            model_path, config_path = self._voice_local_paths(voice_entry)
            return os.path.exists(model_path) and os.path.exists(config_path)
        if resource_id == "cuda:ort":
            try:
                import onnxruntime
                return os.path.isfile(
                    os.path.join(os.path.dirname(onnxruntime.__file__), "capi", "onnxruntime_providers_cuda.dll")
                )
            except Exception:
                return False
        if resource_id == "llama:engine":
            return os.path.isfile(bin_path("llama_cpp", "llama-server.exe"))
        return False

    def _find_voice_entry(self, voice_id: str) -> dict | None:
        payload = self._read_catalog()
        for voice in payload.get("voices", []) or []:
            if isinstance(voice, dict) and str(voice.get("id", "")).strip() == voice_id:
                return voice
        # Downloadable packs and locally discovered voices intentionally use
        # separate catalogs. A model added from the official Piper repository
        # is written to the preview catalog by the UI, so runtime validation
        # must consult it as well. Previously those voices appeared selectable
        # but every Preview/Generate preflight rejected them as unavailable.
        preview_catalog = app_path("voice_preview_catalog.json")
        if os.path.normcase(os.path.abspath(preview_catalog)) == os.path.normcase(os.path.abspath(self._catalog_path())):
            return None
        try:
            with open(preview_catalog, "r", encoding="utf-8-sig") as handle:
                preview_payload = json.load(handle) or {}
        except (OSError, ValueError, TypeError):
            return None
        for voice in preview_payload.get("voices", []) or []:
            if (
                isinstance(voice, dict)
                and str(voice.get("provider", "")).strip().lower() == "piper"
                and str(voice.get("id", "")).strip() == voice_id
            ):
                return voice
        return None

    def _download_and_extract_zip(self, zip_url: str, extract_to: str, progress_cb=None) -> None:
        import tempfile
        import urllib.request
        import zipfile

        print(f"[Download] Starting download: {zip_url}")
        print(f"[Download] Target directory: {extract_to}")
        os.makedirs(extract_to, exist_ok=True)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
            tmp_path = tmp_file.name

        try:
            if progress_cb:
                progress_cb(-1, "Downloading zip file...")

            def _report_progress(block_num, block_size, total_size):
                if progress_cb and total_size > 0:
                    downloaded = block_num * block_size
                    percent = min(99, int((downloaded / total_size) * 100))
                    progress_cb(percent, f"Downloading... ({percent}%)")
                if block_num % 10 == 0:  # Log every 10 blocks
                    print(f"[Download] Progress: block {block_num}, size {block_size}, total {total_size}")

            print("[Download] Calling urlretrieve...")
            urllib.request.urlretrieve(zip_url, tmp_path, reporthook=_report_progress)
            print(f"[Download] Download complete. File size: {os.path.getsize(tmp_path)} bytes")

            if progress_cb:
                progress_cb(90, "Extracting zip file...")

            print(f"[Download] Extracting zip to {extract_to}...")
            with zipfile.ZipFile(tmp_path, "r") as zip_ref:
                self._safe_extract_zip(zip_ref, extract_to)
            print("[Download] Extraction complete.")

            if progress_cb:
                progress_cb(100, "Extraction complete.")
        except Exception as e:
            print(f"[Download] ERROR: {e}")
            raise
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    @staticmethod
    def _download_file(url: str, target_path: str, progress_cb=None, *, label: str = "Downloading file...") -> str:
        """Download one model file atomically while reporting 0-100 progress."""
        import urllib.request

        target = os.path.abspath(str(target_path))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        temporary = f"{target}.part"
        if progress_cb:
            progress_cb(0, label)

        def _report(block_num, block_size, total_size):
            if progress_cb and total_size > 0:
                progress_cb(min(99, int(block_num * block_size * 100 / total_size)), label)

        try:
            urllib.request.urlretrieve(url, temporary, reporthook=_report)
            if not os.path.isfile(temporary) or os.path.getsize(temporary) <= 0:
                raise IOError(f"Downloaded file is empty: {url}")
            os.replace(temporary, target)
            if progress_cb:
                progress_cb(100, f"{label} ready")
            return target
        finally:
            if os.path.exists(temporary):
                try:
                    os.remove(temporary)
                except OSError:
                    pass

    @staticmethod
    def _safe_extract_zip(zip_ref, extract_to: str) -> None:
        """Extract a trusted resource archive without allowing path escapes.

        Resource URLs are configurable through environment variables and can
        be changed outside the application.  ``ZipFile.extractall`` accepts
        ``../`` paths and symlink entries, which could overwrite arbitrary
        files when a compromised archive is downloaded.  Validate every
        member before writing anything, then extract manually beneath the
        resolved destination.
        """
        destination = Path(extract_to).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        members = zip_ref.infolist()
        resolved_members: list[tuple[object, Path, bool]] = []
        seen_targets: set[Path] = set()
        for member in members:
            raw_name = str(member.filename or "")
            if not raw_name or "\x00" in raw_name:
                raise ValueError("Resource archive contains an invalid filename.")
            # ZIP names are POSIX paths even on Windows.  Reject absolute
            # drive/UNC paths as well as traversal components before resolve.
            normalized_name = raw_name.replace("\\", "/")
            candidate = Path(normalized_name)
            if candidate.is_absolute() or (len(normalized_name) >= 2 and normalized_name[1] == ":"):
                raise ValueError(f"Resource archive contains an absolute path: {raw_name}")
            relative_parts = [part for part in normalized_name.split("/") if part not in {"", "."}]
            if not relative_parts:
                raise ValueError(f"Resource archive contains an invalid root entry: {raw_name}")
            if any(part == ".." for part in relative_parts):
                raise ValueError(f"Resource archive contains a path traversal entry: {raw_name}")
            target = (destination.joinpath(*relative_parts)).resolve()
            try:
                target.relative_to(destination)
            except ValueError as exc:
                raise ValueError(f"Resource archive entry escapes target directory: {raw_name}") from exc
            is_directory = raw_name.endswith(("/", "\\"))
            mode = (int(member.external_attr) >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise ValueError(f"Resource archive contains a symlink entry: {raw_name}")
            if target in seen_targets:
                raise ValueError(f"Resource archive contains duplicate entries: {raw_name}")
            seen_targets.add(target)
            resolved_members.append((member, target, is_directory))

        for member, target, is_directory in resolved_members:
            if is_directory:
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zip_ref.open(member, "r") as source, open(target, "wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)

    def download_resource(self, resource_id: str, progress_cb=None) -> None:
        if resource_id == "separation:uvr_mdx":
            self._download_file(
                "https://huggingface.co/Politrees/UVR_resources/resolve/main/models/MDXNet/UVR-MDX-NET-Inst_HQ_3.onnx?download=true",
                bin_path("UVR-MDX-NET-Inst_HQ_3.onnx"),
                progress_cb,
                label="Downloading Voice / Music Separation model",
            )
            return
        if resource_id == "tts:zerotts":
            self._install_zerotts_runtime(progress_cb)
            importlib.invalidate_caches()
            if not self._python_module_imports("zerotts"):
                raise RuntimeError(
                    "ZeroTTS installation command finished, but the runtime could not be imported. "
                    "Use Retry; VIUStudio will repair pip automatically if necessary."
                )
            self._install_zerotts_model(progress_cb)
            if progress_cb:
                progress_cb(100, "ZeroTTS runtime and model installed and verified.")
            return
        if resource_id == "tts:kokoro":
            self._install_kokoro_runtime(progress_cb)
            importlib.invalidate_caches()
            if not self._python_module_imports("kokoro"):
                raise RuntimeError(
                    "Kokoro installation command finished, but the runtime could not be imported. "
                    "Use Retry; VIUStudio will repair pip automatically if necessary."
                )
            self._install_kokoro_english_g2p(progress_cb)
            self._install_kokoro_model(progress_cb)
            from kokoro_support import installation_ready
            if not installation_ready():
                raise RuntimeError(
                    "Kokoro runtime/model was installed, but no local voice was found in models/kokoro/voices."
                )
            if progress_cb:
                progress_cb(100, "Kokoro runtime, model, and voices installed and verified.")
            return

        if resource_id == "sensevoice:model":
            target_dir = models_path("sensevoice")
            self._download_file(
                self.SENSEVOICE_MODEL_URL,
                os.path.join(target_dir, "model.int8.onnx"),
                progress_cb,
                label="Downloading SenseVoice model",
            )
            self._download_file(
                self.SENSEVOICE_TOKENS_URL,
                os.path.join(target_dir, "tokens.txt"),
                progress_cb,
                label="Downloading SenseVoice tokens",
            )
            return

        if resource_id == "sensevoice:vad":
            self._download_file(
                self.SILERO_VAD_URL,
                bin_path("silero_vad.onnx"),
                progress_cb,
                label="Downloading Silero VAD",
            )
            return

        if resource_id.startswith("whisper:"):
            raise ValueError(
                "Whisper models are downloaded manually. Use Open Download Page, then extract the ZIP into models/faster_whisper."
            )

        if resource_id == "cuda:whisper":
            zip_url = self._hf_blob_url("zipResource/cuda12_fw.zip")
            target_dir = join_root("bin")
            self._download_and_extract_zip(zip_url, target_dir, progress_cb)
            try:
                from huggingface_hub import hf_hub_download, hf_hub_url
                from huggingface_hub.file_download import get_hf_file_metadata
            except Exception:
                pass
            ort_dir = ""
            try:
                import onnxruntime
                ort_dir = os.path.join(os.path.dirname(onnxruntime.__file__), "capi")
            except Exception:
                pass
            if ort_dir and os.path.isdir(ort_dir):
                target_ort = os.path.join(ort_dir, "onnxruntime_providers_cuda.dll")
                if not os.path.isfile(target_ort):
                    try:
                        downloaded = self._download_hf_file(
                            repo_id=self.repo_id,
                            revision=self.revision,
                            filename="onnxruntime/capi/onnxruntime_providers_cuda.dll",
                            local_dir=os.path.dirname(os.path.dirname(ort_dir)),
                            hf_hub_download=hf_hub_download,
                            hf_hub_url=hf_hub_url,
                            get_hf_file_metadata=get_hf_file_metadata,
                            progress_cb=progress_cb,
                            start_percent=0,
                            end_percent=100,
                            label="Downloading onnxruntime_providers_cuda.dll",
                        )
                        if downloaded and os.path.isfile(downloaded):
                            norm_src = os.path.normcase(os.path.abspath(downloaded))
                            norm_dst = os.path.normcase(os.path.abspath(target_ort))
                            if norm_src != norm_dst:
                                if os.path.exists(target_ort):
                                    os.remove(target_ort)
                                os.makedirs(ort_dir, exist_ok=True)
                                shutil.move(downloaded, target_ort)
                    except Exception as exc:
                        print(f"[CUDA] Failed to download ONNX GPU provider: {exc}")
            if progress_cb:
                progress_cb(100, "GPU runtime is ready.")
            return

        if resource_id.startswith("voice:"):
            if resource_id == "voice:pack":
                zip_url = self._hf_blob_url("zipResource/piper.zip")
                target_dir = models_path("piper")
                self._download_and_extract_zip(zip_url, target_dir, progress_cb)
                return
            if resource_id == "voice:pack-en":
                zip_url = self._hf_blob_url("zipResource/piper-en.zip")
                target_dir = models_path("piper-en")
                self._download_and_extract_zip(zip_url, target_dir, progress_cb)
                return

            voice_id = resource_id.split(":", 1)[1].strip()
            voice_entry = self._find_voice_entry(voice_id)
            if not voice_entry:
                raise ValueError(f"Voice '{voice_id}' was not found in catalog.")
            remote_model, remote_config = self._voice_remote_paths(voice_entry)
            if progress_cb:
                progress_cb(10, f"Downloading voice model: {voice_id}...")
            try:
                from huggingface_hub import hf_hub_download
            except Exception as exc:
                raise ImportError(
                    "huggingface_hub is not installed. Run `pip install huggingface_hub` first."
                ) from exc
            model_download = hf_hub_download(
                repo_id=self.repo_id,
                revision=self.revision,
                filename=remote_model,
                local_dir=join_root("models"),
            )
            self._finalize_voice_download(model_download, voice_entry, is_config=False)
            if progress_cb:
                progress_cb(60, f"Downloading voice config: {voice_id}...")
            config_download = hf_hub_download(
                repo_id=self.repo_id,
                revision=self.revision,
                filename=remote_config,
                local_dir=join_root("models"),
            )
            self._finalize_voice_download(config_download, voice_entry, is_config=True)
            if progress_cb:
                progress_cb(100, f"Voice {voice_id} is ready.")
            return

        if resource_id == "llama:engine":
            raise ValueError(
                "The llama.cpp engine is downloaded manually. Use 'Open Download Page', "
                "then extract llama-server.exe and its DLLs into the target folder."
            )

        if resource_id in {self.NORMAL_AI_RESOURCE_ID, self.HIGH_AI_RESOURCE_ID}:
            raise ValueError(
                f"Auto download is not supported for '{resource_id}'. Use 'Open Download Page' to get the file manually."
            )

        raise ValueError(f"Unsupported resource: {resource_id}")

    @staticmethod
    def _python_module_imports(module_name: str) -> bool:
        result = subprocess.run(
            [sys.executable, "-c", f"import {module_name}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            **subprocess_hidden_kwargs(),
        )
        return result.returncode == 0

    @staticmethod
    def _pip_runtime_usable() -> bool:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True,
            timeout=60,
            **subprocess_text_kwargs(),
        )
        return result.returncode == 0 and "pip " in str(result.stdout or "").lower()

    @staticmethod
    def _repair_pip_runtime(progress_cb=None) -> None:
        wheel_dir = os.path.join(os.path.dirname(ensurepip.__file__), "_bundled")
        wheel_path = os.path.join(wheel_dir, f"pip-{ensurepip.version()}-py3-none-any.whl")
        if not os.path.isfile(wheel_path):
            raise RuntimeError(f"Bundled pip repair wheel is missing: {wheel_path}")
        if progress_cb:
            progress_cb(5, "Repairing the Python package installer (pip)...")
        repair_script = (
            "import sys; w=sys.argv[1]; sys.path.insert(0,w); "
            "from pip._internal.cli.main import main; "
            "raise SystemExit(main(['install','--force-reinstall','--no-index',w]))"
        )
        result = subprocess.run(
            [sys.executable, "-c", repair_script, wheel_path],
            capture_output=True,
            timeout=600,
            **subprocess_text_kwargs(),
        )
        if result.returncode != 0:
            raise RuntimeError("Could not repair pip:\n" + str(result.stderr or result.stdout or "Unknown error"))

    def _install_zerotts_runtime(self, progress_cb=None) -> None:
        if progress_cb:
            progress_cb(2, "Checking Python package installer...")
        if not self._pip_runtime_usable():
            self._repair_pip_runtime(progress_cb)
        if not self._pip_runtime_usable():
            raise RuntimeError("pip is still unavailable after automatic repair.")

        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "zerotts",
            "--disable-pip-version-check",
            "--progress-bar",
            "off",
        ]
        if progress_cb:
            progress_cb(10, "Resolving ZeroTTS dependencies...")
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            **subprocess_text_kwargs(),
        )
        output_lines: list[str] = []
        current_percent = 10
        for raw_line in process.stdout or ():
            line = str(raw_line or "").strip()
            if not line:
                continue
            output_lines.append(line)
            lower = line.lower()
            if lower.startswith("collecting"):
                current_percent = max(current_percent, 12)
                message = "Resolving ZeroTTS package..."
            elif lower.startswith("downloading"):
                current_percent = max(current_percent, 15)
                message = "Downloading ZeroTTS runtime..."
            elif "installing collected packages" in lower:
                current_percent = max(current_percent, 18)
                message = "Installing ZeroTTS runtime..."
            elif "successfully installed" in lower or "requirement already satisfied: zerotts" in lower:
                current_percent = 20
                message = "Verifying ZeroTTS runtime..."
            else:
                continue
            if progress_cb:
                progress_cb(current_percent, message)
        return_code = process.wait(timeout=1800)
        if return_code != 0:
            details = "\n".join(output_lines[-30:]) or "Unknown pip error"
            raise RuntimeError("ZeroTTS installation failed:\n" + details)

    def _install_kokoro_runtime(self, progress_cb=None) -> None:
        if progress_cb:
            progress_cb(2, "Checking Python package installer...")
        if not self._pip_runtime_usable():
            self._repair_pip_runtime(progress_cb)
        if not self._pip_runtime_usable():
            raise RuntimeError("pip is still unavailable after automatic repair.")
        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "kokoro==0.9.4",
            "--disable-pip-version-check",
            "--progress-bar",
            "off",
        ]
        if progress_cb:
            progress_cb(8, "Resolving Kokoro dependencies...")
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            **subprocess_text_kwargs(),
        )
        output_lines: list[str] = []
        for raw_line in process.stdout or ():
            line = str(raw_line or "").strip()
            if not line:
                continue
            output_lines.append(line)
            lower = line.lower()
            if progress_cb and lower.startswith("downloading"):
                progress_cb(12, "Downloading Kokoro runtime...")
            elif progress_cb and "installing collected packages" in lower:
                progress_cb(17, "Installing Kokoro runtime...")
            elif progress_cb and ("successfully installed" in lower or "requirement already satisfied: kokoro" in lower):
                progress_cb(20, "Verifying Kokoro runtime...")
        return_code = process.wait(timeout=1800)
        if return_code != 0:
            details = "\n".join(output_lines[-30:]) or "Unknown pip error"
            raise RuntimeError("Kokoro installation failed:\n" + details)

    def _install_kokoro_model(self, progress_cb=None) -> None:
        from kokoro_support import CONFIG_FILENAME, MODEL_FILENAME, model_files_ready, model_root

        if model_files_ready():
            if progress_cb:
                progress_cb(100, "Kokoro model is already available.")
            return
        try:
            from huggingface_hub import hf_hub_download, hf_hub_url
            from huggingface_hub.file_download import get_hf_file_metadata
        except Exception as exc:
            raise RuntimeError(f"Kokoro model downloader is unavailable: {exc}") from exc
        target_dir = model_root()
        os.makedirs(target_dir, exist_ok=True)
        for filename, start, end in (
            (CONFIG_FILENAME, 20, 25),
            (MODEL_FILENAME, 25, 99),
        ):
            self._download_hf_file(
                repo_id="hexgrad/Kokoro-82M",
                revision="main",
                filename=filename,
                local_dir=target_dir,
                hf_hub_download=hf_hub_download,
                hf_hub_url=hf_hub_url,
                get_hf_file_metadata=get_hf_file_metadata,
                progress_cb=progress_cb,
                start_percent=start,
                end_percent=end,
                label=f"Downloading Kokoro {filename}",
            )
        if not model_files_ready():
            raise RuntimeError("Kokoro model download completed but required files are missing.")

    def _install_kokoro_english_g2p(self, progress_cb=None) -> None:
        from kokoro_support import english_g2p_available

        if english_g2p_available():
            return
        if progress_cb:
            progress_cb(20, "Installing Kokoro English pronunciation data...")
        process = subprocess.run(
            [sys.executable, "-m", "spacy", "download", "en_core_web_sm"],
            capture_output=True,
            timeout=900,
            **subprocess_text_kwargs(),
        )
        importlib.invalidate_caches()
        if process.returncode != 0 or not english_g2p_available():
            details = str(process.stderr or process.stdout or "Unknown spaCy model error")
            raise RuntimeError("Kokoro English pronunciation data installation failed:\n" + details[-4000:])

    def _install_zerotts_model(self, progress_cb=None) -> None:
        if self._zerotts_model_ready():
            if progress_cb:
                progress_cb(100, "ZeroTTS model is already available.")
            return
        if progress_cb:
            progress_cb(20, "Reading ZeroTTS model manifest...")
        try:
            from huggingface_hub import HfApi, hf_hub_download, hf_hub_url
            from huggingface_hub.file_download import get_hf_file_metadata
            from zerotts.hub import _ALLOW_PATTERNS
        except Exception as exc:
            raise RuntimeError(f"ZeroTTS model downloader is unavailable: {exc}") from exc

        repo_id = "zeroweight-ai/ZeroTTS"
        files = HfApi().list_repo_files(repo_id=repo_id)
        selected = [
            filename for filename in files
            if any(fnmatch.fnmatch(filename, pattern) for pattern in _ALLOW_PATTERNS)
        ]
        if not selected:
            raise RuntimeError("ZeroTTS model manifest did not contain any supported files.")
        target_dir = models_path("zerotts")
        os.makedirs(target_dir, exist_ok=True)
        total = len(selected)
        for index, filename in enumerate(selected):
            start = 20 + int(index * 78 / total)
            end = 20 + int((index + 1) * 78 / total)
            self._download_hf_file(
                repo_id=repo_id,
                revision="main",
                filename=filename,
                local_dir=target_dir,
                hf_hub_download=hf_hub_download,
                hf_hub_url=hf_hub_url,
                get_hf_file_metadata=get_hf_file_metadata,
                progress_cb=progress_cb,
                start_percent=start,
                end_percent=end,
                label=f"Downloading ZeroTTS model ({index + 1}/{total}): {os.path.basename(filename)}",
            )
        if not self._zerotts_model_ready():
            raise RuntimeError("ZeroTTS model download completed but required ONNX files are missing.")

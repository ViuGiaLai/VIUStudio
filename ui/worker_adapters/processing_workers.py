import hashlib
import math
import os
import shutil
import subprocess
import sys
import traceback
import uuid
from pathlib import Path

from PySide6.QtCore import QThread, Signal

APP_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "app")
if APP_PATH not in sys.path:
    sys.path.insert(0, APP_PATH)

from runtime_paths import bin_path, subprocess_hidden_kwargs
from services import EngineRuntime, ResourceDownloadService
try:
    from app.utils.voice_preview_utils import (
        clamp_requested_speed,
        load_manifest,
        provider_native_speed,
        save_manifest,
        segment_cache_key,
        voice_provider,
    )
except ImportError:
    import importlib.util
    _vpu_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "app", "utils", "voice_preview_utils.py")
    if os.path.exists(_vpu_path):
        _spec = importlib.util.spec_from_file_location("viustudio_voice_preview_utils", _vpu_path)
        _vpu = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_vpu)
        clamp_requested_speed = _vpu.clamp_requested_speed
        load_manifest = _vpu.load_manifest
        provider_native_speed = _vpu.provider_native_speed
        save_manifest = _vpu.save_manifest
        segment_cache_key = _vpu.segment_cache_key
        voice_provider = _vpu.voice_provider
    else:
        from utils.voice_preview_utils import (
            clamp_requested_speed,
            load_manifest,
            provider_native_speed,
            save_manifest,
            segment_cache_key,
            voice_provider,
        )


class VocalSeparationWorker(QThread):
    finished = Signal(str, str, str)
    progress = Signal(int, str)

    def __init__(self, audio_path, output_dir, video_path=None):
        super().__init__()
        self.audio_path = audio_path
        self.output_dir = output_dir
        self.video_path = video_path
        self._stop_requested = False

    def stop(self):
        self._stop_requested = True

    def run(self):
        try:
            engine = EngineRuntime()
            if (not self.audio_path or not os.path.exists(self.audio_path)) and self.video_path and os.path.exists(self.video_path):
                self.progress.emit(1, "Extracting audio from video...")
                if self.audio_path:
                    os.makedirs(os.path.dirname(self.audio_path), exist_ok=True)
                extract_ok = engine.extract_audio(self.video_path, self.audio_path)
                if not extract_ok or not os.path.exists(self.audio_path):
                    self.finished.emit("", "", f"Failed to extract audio from {os.path.basename(self.video_path)}")
                    return
                if self._stop_requested:
                    self.finished.emit("", "", "Vocal separation was stopped by user.")
                    return

            vocal_path, music_path = engine.separate_vocals(
                self.audio_path,
                self.output_dir,
                progress_callback=self.progress.emit,
                is_cancelled=lambda: self._stop_requested,
            )
            if self._stop_requested:
                self.finished.emit("", "", "Vocal separation was stopped by user.")
            elif vocal_path and music_path:
                self.finished.emit(vocal_path, music_path, "")
            else:
                self.finished.emit("", "", "Failed to separate audio stems.")
        except ImportError as exc:
            self.finished.emit("", "", str(exc))
        except Exception as exc:
            self.finished.emit("", "", f"Unexpected error: {str(exc)}")


class ExtractionWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, video_path, audio_output_path):
        super().__init__()
        self.video_path = video_path
        self.audio_output_path = audio_output_path

    def run(self):
        try:
            engine = EngineRuntime()
            success = engine.extract_audio(self.video_path, self.audio_output_path)
            self.finished.emit(success, self.audio_output_path)
        except Exception as exc:
            self.finished.emit(False, str(exc))


class TranscriptionWorker(QThread):
    finished = Signal(list, str)

    def __init__(self, audio_path, model_path, language):
        super().__init__()
        self.audio_path = audio_path
        self.model_path = model_path
        self.language = language

    def run(self):
        try:
            engine = EngineRuntime()
            segments = engine.transcribe_audio(self.audio_path, self.model_path, language=self.language)
            self.finished.emit(segments if segments else [], "")
        except Exception as exc:
            details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
            print(f"Transcription Thread Error:\n{details}")
            self.finished.emit([], details or str(exc))


class AlternateRangeTranscriptionWorker(QThread):
    """One-shot alternate-engine transcription for a timeline selection."""
    # Do not shadow QThread.finished.  The native signal is needed to retain
    # and safely dispose of the worker only after run() has actually exited.
    completed = Signal(list, str)

    def __init__(
        self,
        video_path,
        start,
        end,
        engine_name,
        model_path="",
        language="auto",
        *,
        ocr_region="bottom",
        ocr_fps=None,
    ):
        super().__init__()
        self.video_path, self.start_time, self.end_time = video_path, float(start), float(end)
        self.engine_name, self.model_path, self.language = engine_name, model_path, language
        self.ocr_region = str(ocr_region or "bottom")
        self.ocr_fps = float(ocr_fps) if ocr_fps is not None else None

    def run(self):
        temp_audio = ""
        try:
            engine = EngineRuntime()
            if self.engine_name == "ocr":
                segments = engine.transcribe_video_ocr(
                    self.video_path,
                    region=self.ocr_region,
                    fps=self.ocr_fps,
                    start_seconds=self.start_time,
                    end_seconds=self.end_time,
                )
            else:
                import tempfile
                temp_audio = os.path.join(tempfile.gettempdir(), f"viustudio_range_{int(self.start_time * 1000)}_{int(self.end_time * 1000)}.wav")
                ffmpeg = bin_path("ffmpeg", "ffmpeg.exe")
                subprocess.run([
                    ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", str(self.start_time),
                    "-t", str(max(0.1, self.end_time - self.start_time)), "-i", self.video_path,
                    "-vn", "-ac", "1", "-ar", "16000", temp_audio,
                ], check=True, **subprocess_hidden_kwargs())
                segments = engine.transcribe_audio(temp_audio, self.model_path, language=self.language)
                for segment in segments or []:
                    segment["start"] = float(segment.get("start", 0.0)) + self.start_time
                    segment["end"] = float(segment.get("end", 0.0)) + self.start_time
            self.completed.emit(list(segments or []), "")
        except Exception as exc:
            self.completed.emit([], str(exc))
        finally:
            if temp_audio:
                try: os.remove(temp_audio)
                except OSError: pass


class TranslationWorker(QThread):
    finished = Signal(str, str, str)
    progress = Signal(object)

    def __init__(self, srt_text, model_path, src_lang, target_lang, enable_polish):
        super().__init__()
        self.srt_text = srt_text
        self.model_path = model_path
        self.src_lang = src_lang
        self.target_lang = target_lang
        self.enable_polish = enable_polish

    def run(self):
        try:
            try:
                from translation import TranslationOrchestrator
                orch = TranslationOrchestrator()
                provider_type, polisher = orch._resolve_ai_provider()
                print(f"[Translate] Using AI: {orch._describe_ai_provider(provider_type, polisher)}")
                result = orch.translate_srt(
                    self.srt_text,
                    src_lang=self.src_lang,
                    target_lang=self.target_lang,
                    enable_polish=self.enable_polish,
                    on_progress=self.progress.emit,
                    cancellation_check=self.isInterruptionRequested,
                )
                if not result.success:
                    raise RuntimeError("; ".join(result.errors) or "Translation failed.")
                translated_srt = orch.result_to_srt(result)
                fallback_notice = "\n".join(result.warnings or []) if result.used_fallback else ""
            except Exception:
                raise
            self.finished.emit(translated_srt, "", fallback_notice)
        except InterruptedError:
            print("[TranslationWorker] Cancelled by user.")
            self.finished.emit("", "Operation cancelled by user", "")
        except Exception as exc:
            print(f"Translation Thread Error: {exc}")
            self.finished.emit("", str(exc), "")


class OllamaStatusWorker(QThread):
    """Probe the local Ollama server without blocking the Settings dialog."""
    finished = Signal(bool, str)

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = str(base_url or "http://localhost:11434/v1")

    def run(self):
        try:
            import requests

            endpoint = self.base_url.rstrip("/")
            if endpoint.endswith("/v1"):
                endpoint = endpoint[:-3]
            response = requests.get(f"{endpoint}/api/tags", timeout=2.5)
            response.raise_for_status()
            self.finished.emit(True, "Connected")
        except Exception as exc:
            self.finished.emit(False, f"Not connected: {exc}")


class OcrTranslatorCaptureWorker(QThread):
    """One-shot OCR capture used by the editor utility, never by ASR."""
    finished = Signal(str, str)

    def __init__(self, video_path, position_seconds, normalized_rect):
        super().__init__()
        self.video_path = video_path
        self.position_seconds = float(position_seconds or 0.0)
        self.normalized_rect = tuple(normalized_rect or ())

    def run(self):
        try:
            from ocr_processor import extract_ocr_text_from_video_region
            text = extract_ocr_text_from_video_region(
                self.video_path, self.position_seconds, self.normalized_rect
            )
            self.finished.emit(text, "")
        except Exception as exc:
            self.finished.emit("", str(exc))


class OcrTranslatorTranslationWorker(QThread):
    """Translate a captured OCR value with the configured app provider."""
    finished = Signal(str, str)

    def __init__(self, text, source_lang, target_lang):
        super().__init__()
        self.text = str(text or "")
        self.source_lang = str(source_lang or "auto")
        self.target_lang = str(target_lang or "vi")

    def run(self):
        try:
            engine = EngineRuntime()
            selected_provider = str(os.getenv("OPENAI_PROVIDER") or "google").strip().lower()
            print(f"[OCR Translator] Translating with selected provider: {selected_provider}")
            result = engine.translate_segments(
                [{"start": 0.0, "end": 1.0, "text": self.text}],
                src_lang=self.source_lang,
                target_lang=self.target_lang,
                # This utility must follow the same selected cloud/API
                # provider as the main translation pipeline.  Passing False
                # bypasses it and always takes the Google fallback path.
                enable_polish=True,
                optimize_subtitles=False,
                style_instruction="[mode=ocr_capture]",
            )
            first = (result or [None])[0]
            if isinstance(first, dict):
                translated = first.get("text", "")
                actual_provider = first.get("provider", "")
            else:
                translated = getattr(first, "text", "")
                actual_provider = getattr(first, "provider", "")
            translated = str(translated or "").strip()
            if not translated:
                raise RuntimeError("The translator returned no text.")
            actual_provider = str(actual_provider or selected_provider).strip()
            print(f"[OCR Translator] Translation completed using: {actual_provider}")
            self.finished.emit(translated, "")
        except Exception as exc:
            self.finished.emit("", str(exc))


class RewriteTranslationWorker(QThread):
    finished = Signal(str, str)

    def __init__(self, source_segments, translated_segments, src_lang, style_instruction=""):
        super().__init__()
        self.source_segments = source_segments
        self.translated_segments = translated_segments
        self.src_lang = src_lang
        self.style_instruction = style_instruction

    def run(self):
        try:
            engine = EngineRuntime()
            try:
                from translation import TranslationOrchestrator
                orch = TranslationOrchestrator()
                provider_type, polisher = orch._resolve_ai_provider()
                print(f"[Rewrite] Using AI: {orch._describe_ai_provider(provider_type, polisher)}")
            except Exception:
                pass
            rewritten_segments = engine.rewrite_translation_segments(
                self.source_segments,
                self.translated_segments,
                src_lang=self.src_lang,
                style_instruction=self.style_instruction,
            )
            from translation.srt_utils import to_srt

            self.finished.emit(to_srt(rewritten_segments), "")
        except Exception as exc:
            print(f"Rewrite Thread Error: {exc}")
            self.finished.emit("", str(exc))


class RuntimeAssetsWorker(QThread):
    finished = Signal(str, str)
    progress = Signal(int, str)  # percent (0-100) or -1 for indeterminate, message

    def __init__(self, workspace_root, whisper_model_name="medium", demucs_model_name="htdemucs"):
        super().__init__()
        self.workspace_root = workspace_root
        self.whisper_model_name = whisper_model_name
        self.demucs_model_name = demucs_model_name

    def run(self):
        try:
            details = []

            self.progress.emit(5, "Checking bundled runtime assets...")
            ffmpeg_path = Path(bin_path("ffmpeg", "ffmpeg.exe"))
            if not ffmpeg_path.exists():
                raise FileNotFoundError(f"Bundled FFmpeg is missing: {ffmpeg_path}")
            details.append(f"FFmpeg ready: {ffmpeg_path}")
            self.progress.emit(12, "FFmpeg is ready.")

            mpv_path = Path(bin_path("mpv", "libmpv-2.dll"))
            if not mpv_path.exists():
                alt_mpv_path = Path(bin_path("mpv", "mpv-2.dll"))
                if not alt_mpv_path.exists():
                    raise FileNotFoundError(f"Bundled libmpv is missing: {mpv_path}")
                mpv_path = alt_mpv_path
            details.append(f"libmpv ready: {mpv_path}")
            self.progress.emit(20, "Preview runtime is ready.")

            from whisper_processor import load_whisper_model

            whisper_cache_dir = Path(self.workspace_root) / "models" / "faster_whisper"
            whisper_cache_dir.mkdir(parents=True, exist_ok=True)
            cached = any(
                p.is_dir() and self.whisper_model_name in p.name.lower()
                for p in whisper_cache_dir.glob("models--*")
            )
            if cached:
                self.progress.emit(35, f"Loading Whisper model: {self.whisper_model_name} ...")
            else:
                self.progress.emit(-1, f"Downloading Whisper model: {self.whisper_model_name} ...")
            load_whisper_model(self.whisper_model_name)
            details.append(f"Whisper model ready: {self.whisper_model_name}")

            self.progress.emit(80, f"Whisper model ready: {self.whisper_model_name}")
            from demucs.pretrained import get_model

            try:
                self.progress.emit(-1, f"Downloading Demucs model: {self.demucs_model_name} ...")
                get_model(self.demucs_model_name)
                details.append(f"Demucs model ready: {self.demucs_model_name}")
            except Exception as demucs_exc:
                warning = f"Demucs preload skipped: {demucs_exc}"
                print(f"RuntimeAssetsWorker Warning: {warning}")
                details.append(warning)

            self.progress.emit(100, "All models ready.")
            self.finished.emit("\n".join(details), "")
        except Exception as exc:
            details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
            print(f"RuntimeAssetsWorker Error:\n{details}")
            self.finished.emit("", details or str(exc))


class ResourceDownloadWorker(QThread):
    finished = Signal(str, str)
    progress = Signal(int, str)

    def __init__(self, workspace_root, resource_id):
        super().__init__()
        self.workspace_root = workspace_root
        self.resource_id = resource_id

    def run(self):
        try:
            service = ResourceDownloadService(self.workspace_root)
            service.download_resource(self.resource_id, progress_cb=self.progress.emit)
            self.finished.emit(self.resource_id, "")
        except Exception as exc:
            details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
            print(f"ResourceDownloadWorker Error:\n{details}")
            self.finished.emit(self.resource_id, details or str(exc))


class TimelineWaveformWorker(QThread):
    finished = Signal(object, object, float, str)

    def __init__(self, request_signature, video_path, audio_path, temp_audio_path, timeline_clips=None):
        super().__init__()
        self.request_signature = request_signature
        self.video_path = str(video_path or "").strip()
        self.audio_path = str(audio_path or "").strip()
        self.temp_audio_path = str(temp_audio_path or "").strip()
        self.timeline_clips = [dict(clip) for clip in (timeline_clips or [])]

    def run(self):
        try:
            audio_path = self.audio_path if self.audio_path and os.path.exists(self.audio_path) else ""
            if not audio_path and self.video_path and os.path.exists(self.video_path):
                temp_audio = self.temp_audio_path
                if temp_audio and not os.path.exists(temp_audio):
                    os.makedirs(os.path.dirname(temp_audio), exist_ok=True)
                    ffmpeg = os.path.join(bin_path("ffmpeg"), "ffmpeg.exe")
                    if self.timeline_clips:
                        from audio_mixer import _build_atempo_filter

                        command = [ffmpeg, "-y", "-loglevel", "error"]
                        filters, labels = [], []
                        for index, clip in enumerate(self.timeline_clips):
                            command += ["-i", str(clip["source"])]
                            start = max(0.0, float(clip.get("source_start", 0.0) or 0.0))
                            duration = max(0.001, float(clip.get("source_duration", 0.0) or 0.0))
                            speed = max(0.01, float(clip.get("speed", 1.0) or 1.0))
                            label = f"wa{index}"
                            filters.append(
                                f"[{index}:a]atrim=start={start:.6f}:duration={duration:.6f},"
                                f"asetpts=PTS-STARTPTS,{_build_atempo_filter(speed)},aresample=16000,"
                                f"aformat=sample_fmts=s16:channel_layouts=mono[{label}]"
                            )
                            labels.append(f"[{label}]")
                        filters.append(f"{''.join(labels)}concat=n={len(labels)}:v=0:a=1[wave]")
                        command += ["-filter_complex", ";".join(filters), "-map", "[wave]", "-c:a", "pcm_s16le", temp_audio]
                    else:
                        command = [
                            ffmpeg, "-y", "-loglevel", "error", "-i", self.video_path,
                            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", temp_audio,
                        ]
                    # Long media extraction is streaming and memory bounded.  A
                    # five-hour source can legitimately take more than the old
                    # fixed five-minute timeout on slower disks.
                    subprocess.run(command, check=True, timeout=86400, **subprocess_hidden_kwargs())
                if temp_audio and os.path.exists(temp_audio):
                    audio_path = temp_audio

            if not audio_path or not os.path.exists(audio_path):
                self.finished.emit(self.request_signature, [], 0.0, "")
                return

            from audio_waveform import build_waveform_envelope

            waveform, duration_s = build_waveform_envelope(audio_path)

            self.finished.emit(self.request_signature, waveform, duration_s, "")
        except Exception as exc:
            details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
            self.finished.emit(self.request_signature, [], 0.0, details or str(exc))


class TimelineThumbnailWorker(QThread):
    finished = Signal(object, object, str)

    def __init__(self, request_signature, video_path, duration_s, thumb_dir, timeline_clips=None):
        super().__init__()
        self.request_signature = request_signature
        self.video_path = str(video_path or "").strip()
        self.duration_s = max(0.0, float(duration_s or 0.0))
        self.thumb_dir = str(thumb_dir or "").strip()
        self.timeline_clips = [dict(clip) for clip in (timeline_clips or [])]

    def run(self):
        try:
            if not self.video_path or not os.path.exists(self.video_path) or self.duration_s <= 0.0:
                self.finished.emit(self.request_signature, [], "")
                return

            ffmpeg_candidates = [
                bin_path("ffmpeg", "ffmpeg.exe"),
                bin_path("ffmpeg.exe"),
                shutil.which("ffmpeg"),
                shutil.which("ffmpeg.exe"),
            ]
            ffmpeg_path = ""
            for candidate in ffmpeg_candidates:
                if candidate and os.path.isfile(candidate):
                    ffmpeg_path = candidate
                    break

            if not ffmpeg_path:
                self.finished.emit(self.request_signature, [], "")
                return

            ffmpeg_candidates = [
                bin_path("ffmpeg", "ffmpeg.exe"),
                bin_path("ffmpeg.exe"),
                shutil.which("ffmpeg"),
                shutil.which("ffmpeg.exe"),
            ]
            ffmpeg_path = ""
            for candidate in ffmpeg_candidates:
                if candidate and os.path.isfile(candidate):
                    ffmpeg_path = candidate
                    break

            if not ffmpeg_path:
                self.finished.emit(self.request_signature, [], "")
                return

            # Adapt density to media length: short clips need frequent visual
            # landmarks, while long videos stay bounded for fast preparation.
            if self.duration_s <= 60.0:
                interval_s = max(1.5, self.duration_s / 20.0)
            elif self.duration_s <= 300.0:
                interval_s = max(3.0, self.duration_s / 45.0)
            else:
                interval_s = max(5.0, self.duration_s / 90.0)
            thumb_count = max(1, min(150, int(math.ceil(self.duration_s / interval_s))))
            if self.duration_s <= 1.0:
                timestamps = [0.0]
            else:
                timestamps = [
                    min(self.duration_s - 0.05, max(0.0, idx * interval_s))
                    for idx in range(thumb_count)
                ]

            os.makedirs(self.thumb_dir, exist_ok=True)
            digest = hashlib.md5(
                f"{self.video_path}|{self.request_signature}".encode("utf-8", errors="replace")
            ).hexdigest()[:16]

            startupinfo = None
            creationflags = 0
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

            requests = []
            if self.timeline_clips:
                for clip in self.timeline_clips:
                    clip_duration = max(0.0, float(clip.get("timeline_end", 0.0)) - float(clip.get("timeline_start", 0.0)))
                    count = max(6, min(60, int(math.ceil(clip_duration / max(3.0, interval_s)))))
                    for part in range(count):
                        offset = min(max(0.0, clip_duration - 0.05), part * clip_duration / count)
                        requests.append((
                            str(clip.get("source", "") or ""),
                            float(clip.get("source_start", 0.0) or 0.0) + offset * max(0.01, float(clip.get("speed", 1.0) or 1.0)),
                            float(clip.get("timeline_start", 0.0) or 0.0) + offset,
                        ))
            else:
                requests = [(self.video_path, timestamp, timestamp) for timestamp in timestamps]

            thumbnails = []
            for idx, (source_path, source_timestamp, timeline_timestamp) in enumerate(requests):
                output_path = os.path.join(self.thumb_dir, f"{digest}_{idx:02d}.jpg")
                if not os.path.exists(output_path):
                    cmd = [
                        ffmpeg_path,
                        "-y",
                        "-ss",
                        f"{source_timestamp:.3f}",
                        "-i",
                        source_path,
                        "-frames:v",
                        "1",
                        "-q:v",
                        "4",
                        "-vf",
                        "scale=180:-1:force_original_aspect_ratio=decrease",
                        output_path,
                    ]
                    try:
                        subprocess.run(
                            cmd,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            check=False,
                            timeout=20,
                            startupinfo=startupinfo,
                            creationflags=creationflags,
                        )
                    except Exception:
                        continue
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    thumbnails.append((float(timeline_timestamp), output_path))

            self.finished.emit(self.request_signature, thumbnails, "")
        except Exception as exc:
            details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
            self.finished.emit(self.request_signature, [], details or str(exc))


class PrepareWorkflowWorker(QThread):
    # Do not shadow QThread.finished.  A result signal emitted from inside
    # run() fires slightly before the native thread has fully stopped; using
    # the name ``finished`` previously let UI cleanup destroy this object
    # during that unwind and crash the entire application.
    result_ready = Signal(str, str)
    step_started = Signal(str)

    def __init__(
        self,
        workspace_root,
        video_path,
        mode,
        audio_handling_mode,
        source_language,
        target_language,
        translator_ai,
        optimize_subtitles,
        translator_style,
        whisper_model_name,
        transcription_engine="whisper",
        speaker_diarization=False,
        speaker_diarization_num_speakers=-1,
        skip_translation=False,
        repair_asr_with_ocr=True,
        prefetch_voice_name="",
        prefetch_voice_speed=1.0,
        remote_api_url="",
        remote_api_token="",
        force_remote_api=False,
        timeline_clips=None,
    ):
        super().__init__()
        self.workspace_root = workspace_root
        self.video_path = video_path
        self.mode = mode
        self.audio_handling_mode = audio_handling_mode
        self.source_language = source_language
        self.target_language = str(target_language or "vi").strip().lower()
        self.translator_ai = translator_ai
        self.optimize_subtitles = False
        self.translator_style = translator_style
        self.whisper_model_name = whisper_model_name
        self.transcription_engine = transcription_engine
        self.speaker_diarization = bool(speaker_diarization)
        self.speaker_diarization_num_speakers = int(speaker_diarization_num_speakers or -1)
        self.skip_translation = skip_translation
        self.repair_asr_with_ocr = bool(repair_asr_with_ocr)
        self.prefetch_voice_name = prefetch_voice_name
        self.prefetch_voice_speed = float(prefetch_voice_speed or 1.0)
        self.remote_api_url = str(remote_api_url or "").strip()
        self.remote_api_token = str(remote_api_token or "").strip()
        self.force_remote_api = bool(force_remote_api)
        self.timeline_clips = [dict(clip) for clip in (timeline_clips or [])]

    def run(self):
        try:
            from runtime_profile import is_remote_profile
            if self.force_remote_api or is_remote_profile():
                from remote_api import remote_api_post
                old_url = os.environ.get("VIUSTUDIO_REMOTE_API_URL")
                old_token = os.environ.get("VIUSTUDIO_REMOTE_API_TOKEN")
                try:
                    if self.remote_api_url:
                        os.environ["VIUSTUDIO_REMOTE_API_URL"] = self.remote_api_url
                    if self.remote_api_token:
                        os.environ["VIUSTUDIO_REMOTE_API_TOKEN"] = self.remote_api_token
                    response = remote_api_post(
                        "/v1/prepare",
                        {
                            "workspace_root": self.workspace_root,
                            "video_path": self.video_path,
                            "source_language": self.source_language,
                            "target_language": self.target_language,
                            "mode": self.mode,
                            "audio_handling_mode": self.audio_handling_mode,
                            "translator_ai": self.translator_ai,
                            "optimize_subtitles": self.optimize_subtitles,
                            "translator_style": self.translator_style,
                            "whisper_model_name": self.whisper_model_name,
                            "transcription_engine": self.transcription_engine,
                            "speaker_diarization": self.speaker_diarization,
                            "speaker_diarization_num_speakers": self.speaker_diarization_num_speakers,
                            "skip_translation": self.skip_translation,
                            "repair_asr_with_ocr": self.repair_asr_with_ocr,
                            "prefetch_voice_name": self.prefetch_voice_name,
                            "prefetch_voice_speed": self.prefetch_voice_speed,
                            "timeline_clips": self.timeline_clips,
                        },
                        timeout=3600,
                        retries=1 if self.force_remote_api else 3,
                    )
                    self.result_ready.emit(str(response.get("project_state_path", "")), "")
                finally:
                    if old_url is None:
                        os.environ.pop("VIUSTUDIO_REMOTE_API_URL", None)
                    else:
                        os.environ["VIUSTUDIO_REMOTE_API_URL"] = old_url
                    if old_token is None:
                        os.environ.pop("VIUSTUDIO_REMOTE_API_TOKEN", None)
                    else:
                        os.environ["VIUSTUDIO_REMOTE_API_TOKEN"] = old_token
            else:
                from workflows.prepare_workflow import PrepareWorkflow
                workflow = PrepareWorkflow(self.workspace_root)
                project_state = workflow.run(
                    video_path=self.video_path,
                    source_language=self.source_language,
                    target_language=self.target_language,
                    mode=self.mode,
                    audio_handling_mode=self.audio_handling_mode,
                    translator_ai=self.translator_ai,
                    optimize_subtitles=self.optimize_subtitles,
                    translator_style=self.translator_style,
                    whisper_model_name=self.whisper_model_name,
                    transcription_engine=self.transcription_engine,
                    speaker_diarization=self.speaker_diarization,
                    speaker_diarization_num_speakers=self.speaker_diarization_num_speakers,
                    skip_translation=self.skip_translation,
                    repair_asr_with_ocr=self.repair_asr_with_ocr,
                    prefetch_voice_name=self.prefetch_voice_name,
                    prefetch_voice_speed=self.prefetch_voice_speed,
                    step_callback=self.step_started.emit,
                    timeline_clips=self.timeline_clips,
                )
                state_path = os.path.join(project_state.project_root, "project.json")
                self.result_ready.emit(state_path, "")
        except Exception as exc:
            self.result_ready.emit("", str(exc))


class VoiceOverWorker(QThread):
    finished = Signal(str, str, object, str)
    progress = Signal(object)

    def __init__(self, workspace_root, segments, output_dir, background_path, audio_handling_mode, voice_name, voice_speed, timing_sync_mode, original_volume, dub_volume, project_state_path="", project_temp_dir="", ai_rewrite_dubbing=False, dubbing_style_instruction="", source_language="auto"):
        super().__init__()
        self.workspace_root = workspace_root
        self.segments = segments
        self.output_dir = output_dir
        self.background_path = background_path
        self.audio_handling_mode = audio_handling_mode
        self.voice_name = voice_name
        self.voice_speed = voice_speed
        self.timing_sync_mode = timing_sync_mode
        self.original_volume = original_volume
        self.dub_volume = dub_volume
        self.project_state_path = project_state_path
        self.project_temp_dir = project_temp_dir
        self.ai_rewrite_dubbing = ai_rewrite_dubbing
        self.dubbing_style_instruction = dubbing_style_instruction
        self.source_language = source_language

    def run(self):
        try:
            from runtime_profile import is_remote_profile
            if is_remote_profile():
                from remote_api import remote_api_post
                response = remote_api_post(
                    "/v1/voice",
                    {
                        "workspace_root": self.workspace_root,
                        "segments": self.segments,
                        "output_dir": self.output_dir,
                        "background_path": self.background_path,
                        "audio_handling_mode": self.audio_handling_mode,
                        "voice_name": self.voice_name,
                        "voice_speed": self.voice_speed,
                        "timing_sync_mode": self.timing_sync_mode,
                        "original_volume": self.original_volume,
                        "dub_volume": self.dub_volume,
                        "project_state_path": self.project_state_path,
                        "project_temp_dir": self.project_temp_dir,
                        "ai_rewrite_dubbing": self.ai_rewrite_dubbing,
                        "dubbing_style_instruction": self.dubbing_style_instruction,
                        "source_language": self.source_language,
                    },
                    timeout=3600,
                )
                result = response.get("result", {})
                self.finished.emit(
                    result.get("voice_track", ""),
                    result.get("mixed_path", ""),
                    result.get("segments", []),
                    "",
                )
            else:
                from workflows.voice_workflow import VoiceWorkflow
                workflow = VoiceWorkflow(self.workspace_root)
                result = workflow.run(
                    segments=self.segments,
                    output_dir=self.output_dir,
                    background_path=self.background_path,
                    audio_handling_mode=self.audio_handling_mode,
                    voice_name=self.voice_name,
                    voice_speed=float(self.voice_speed),
                    timing_sync_mode=self.timing_sync_mode,
                    original_volume=int(self.original_volume),
                    dub_volume=int(self.dub_volume),
                    project_state_path=self.project_state_path,
                    project_temp_dir=self.project_temp_dir,
                    ai_rewrite_dubbing=self.ai_rewrite_dubbing,
                    dubbing_style_instruction=self.dubbing_style_instruction,
                    source_language=self.source_language,
                    on_progress=self.progress.emit,
                    cancellation_check=self.isInterruptionRequested,
                )
                self.finished.emit(
                    result.get("voice_track", ""),
                    result.get("mixed_path", ""),
                    result.get("segments", []),
                    "",
                )
        except InterruptedError:
            print("[VoiceOverWorker] Cancelled by user.")
            self.finished.emit("", "", [], "Operation cancelled by user")
        except Exception as exc:
            print(f"[VoiceOverWorker ERROR] {str(exc)}")
            self.finished.emit("", "", [], str(exc))


class AutoRecapWorker(QThread):
    """Dedicated five-stage Auto Edit Recap worker.

    It intentionally does not invoke subtitle transcription, translation, or
    TTS generation. Existing subtitles are only used as optional context for
    effect planning, so the recap workflow remains separate from Generate.
    """

    stage_started = Signal(str, str)
    finished = Signal(object, str, str)

    def __init__(self, video_path, output_path, config, segments=None, timeline_clips=None):
        super().__init__()
        self.video_path = str(video_path or "")
        self.output_path = str(output_path or "")
        self.config = config
        self.segments = [dict(item) for item in (segments or []) if isinstance(item, dict)]
        self.timeline_clips = [dict(item) for item in (timeline_clips or []) if isinstance(item, dict)]

    def run(self):
        try:
            from app.services.auto_recap_engine import AutoRecapEngine

            engine = AutoRecapEngine(self.config)
            self.stage_started.emit("analyzing", "Analyzing video and detecting effect boundaries...")
            scenes = []
            if self.timeline_clips:
                for clip in self.timeline_clips:
                    source = str(clip.get("source", "") or "")
                    if not source or not os.path.exists(source):
                        continue
                    source_start = float(clip.get("source_start", 0.0) or 0.0)
                    source_end = source_start + float(clip.get("source_duration", 0.0) or 0.0)
                    timeline_start = float(clip.get("timeline_start", 0.0) or 0.0)
                    speed = max(0.01, float(clip.get("speed", 1.0) or 1.0))
                    for scene in engine.detect_scenes_ffmpeg(source, threshold=0.25):
                        start = max(source_start, float(scene.get("start", 0.0) or 0.0))
                        end = min(source_end, float(scene.get("end", 0.0) or 0.0))
                        if end > start:
                            item = dict(scene)
                            item["start"] = timeline_start + (start - source_start) / speed
                            item["end"] = timeline_start + (end - source_start) / speed
                            scenes.append(item)
            else:
                scenes = engine.detect_scenes_ffmpeg(self.video_path, threshold=0.25)
            if not scenes:
                raise RuntimeError("No usable effect boundaries were found in the source video.")

            self.stage_started.emit("building", "Building a full-timeline effect plan (keeping every scene)...")
            scenes = engine.apply_subtitles_to_scenes(scenes, self.segments)
            decisions = engine.generate_edl([], scenes=scenes)
            if not decisions:
                raise RuntimeError("Could not build an Auto Edit Recap effect plan.")

            self.stage_started.emit("smart_edits", "Scheduling zoom, pan, crop, speed and anti-repetition effects...")
            self.stage_started.emit("audio", "Preserving source audio and applying recap audio settings...")
            self.stage_started.emit("rendering", "Rendering recap in one FFmpeg pass...")
            timeline_required = bool(
                len(self.timeline_clips) > 1
                or (self.timeline_clips and float(self.timeline_clips[0].get("source_start", 0.0) or 0.0) > 0.01)
            )
            rendered = (
                engine.render_timeline_recap_1pass(self.timeline_clips, self.output_path, decisions)
                if timeline_required else engine.render_recap_video_1pass(self.video_path, self.output_path, decisions)
            )
            if not rendered:
                raise RuntimeError(engine.last_render_error or "FFmpeg could not render the recap video.")
            self.finished.emit(decisions, self.output_path, "")
        except Exception as exc:
            self.finished.emit([], "", str(exc))


class AutoRecapRenderWorker(QThread):
    """Render an existing recap EDL without blocking the Qt event loop."""

    finished = Signal(str, str)

    def __init__(self, video_path, output_path, config, decisions, timeline_clips=None):
        super().__init__()
        self.video_path = str(video_path or "")
        self.output_path = str(output_path or "")
        self.config = config
        self.decisions = list(decisions or [])
        self.timeline_clips = [
            dict(item) for item in (timeline_clips or []) if isinstance(item, dict)
        ]

    def run(self):
        try:
            from app.services.auto_recap_engine import AutoRecapEngine

            engine = AutoRecapEngine(self.config)
            timeline_required = bool(
                len(self.timeline_clips) > 1
                or (
                    self.timeline_clips
                    and float(self.timeline_clips[0].get("source_start", 0.0) or 0.0) > 0.01
                )
            )
            rendered = (
                engine.render_timeline_recap_1pass(
                    self.timeline_clips, self.output_path, self.decisions
                )
                if timeline_required
                else engine.render_recap_video_1pass(
                    self.video_path, self.output_path, self.decisions
                )
            )
            if not rendered:
                raise RuntimeError(
                    engine.last_render_error or "FFmpeg could not render the recap video."
                )
            self.finished.emit(self.output_path, "")
        except Exception as exc:
            self.finished.emit("", str(exc))


class FinalExportWorker(QThread):
    finished = Signal(str, str)
    progress = Signal(int, str)

    def __init__(self, workspace_root, video_path, output_path, mode, srt_path="", ass_path="", audio_path="", subtitle_style=None, output_quality="source", output_fps="source", output_ratio="source", output_scale_mode="fit", output_fill_focus_x=0.5, output_fill_focus_y=0.5, video_filter_state=None, original_audio_gain_db=0.0, project_state_path="", project_temp_dir="", timeline_clips=None, export_preset="balanced", video_bitrate_kbps=2000):
        super().__init__()
        self.workspace_root = workspace_root
        self.video_path = video_path
        self.output_path = output_path
        self.mode = mode
        self.srt_path = srt_path
        self.ass_path = ass_path
        self.audio_path = audio_path
        self.subtitle_style = subtitle_style or {}
        self.output_quality = output_quality
        self.output_fps = output_fps
        self.output_ratio = output_ratio
        self.output_scale_mode = output_scale_mode
        self.output_fill_focus_x = output_fill_focus_x
        self.output_fill_focus_y = output_fill_focus_y
        self.video_filter_state = video_filter_state or {}
        self.original_audio_gain_db = float(original_audio_gain_db or 0.0)
        self.project_state_path = project_state_path
        self.project_temp_dir = project_temp_dir
        self.timeline_clips = [dict(clip) for clip in (timeline_clips or [])]
        self.export_preset = str(export_preset or "balanced")
        self.video_bitrate_kbps = int(video_bitrate_kbps or 2000)

    def run(self):
        try:
            from runtime_profile import is_remote_profile
            self.progress.emit(0, "Sending export request to backend...")
            if is_remote_profile():
                from remote_api import remote_api_post
                response = remote_api_post(
                    "/v1/export",
                    {
                        "workspace_root": self.workspace_root,
                        "video_path": self.video_path,
                        "output_path": self.output_path,
                        "mode": self.mode,
                        "srt_path": self.srt_path,
                        "ass_path": self.ass_path,
                        "audio_path": self.audio_path,
                        "subtitle_style": self.subtitle_style,
                        "output_quality": self.output_quality,
                        "output_fps": self.output_fps,
                        "output_ratio": self.output_ratio,
                        "output_scale_mode": self.output_scale_mode,
                        "output_fill_focus_x": self.output_fill_focus_x,
                        "output_fill_focus_y": self.output_fill_focus_y,
                        "video_filter_state": self.video_filter_state,
                        "original_audio_gain_db": self.original_audio_gain_db,
                        "project_state_path": self.project_state_path,
                        "project_temp_dir": self.project_temp_dir,
                        "timeline_clips": self.timeline_clips,
                        "export_preset": self.export_preset,
                        "video_bitrate_kbps": self.video_bitrate_kbps,
                    },
                    timeout=3600,
                )
                self.progress.emit(100, "Export complete.")
                self.finished.emit(str(response.get("output_path", "")), "")
            else:
                from workflows.export_workflow import ExportWorkflow
                workflow = ExportWorkflow(self.workspace_root)
                output_path = workflow.run(
                    video_path=self.video_path,
                    output_path=self.output_path,
                    mode=self.mode,
                    srt_path=self.srt_path,
                    ass_path=self.ass_path,
                    audio_path=self.audio_path,
                    subtitle_style=self.subtitle_style,
                    output_quality=self.output_quality,
                    output_fps=self.output_fps,
                    output_ratio=self.output_ratio,
                    output_scale_mode=self.output_scale_mode,
                    output_fill_focus_x=self.output_fill_focus_x,
                    output_fill_focus_y=self.output_fill_focus_y,
                    video_filter_state=self.video_filter_state,
                    original_audio_gain_db=self.original_audio_gain_db,
                    project_state_path=self.project_state_path,
                    project_temp_dir=self.project_temp_dir,
                    on_progress=self.progress.emit,
                    cancellation_check=self.isInterruptionRequested,
                    timeline_clips=self.timeline_clips,
                    export_preset=self.export_preset,
                    video_bitrate_kbps=self.video_bitrate_kbps,
                )
                self.finished.emit(output_path, "")
        except InterruptedError:
            print("[FinalExportWorker] Cancelled by user.")
            self.finished.emit("", "Operation cancelled by user")
        except Exception as exc:
            self.finished.emit("", str(exc))


class SegmentAudioPreviewWorker(QThread):
    finished = Signal(int, str, str)

    def __init__(self, workspace_root, index, text, voice_name, voice_speed, temp_dir="", cache_temp_dir=""):
        super().__init__()
        self.workspace_root = workspace_root
        self.index = index
        self.text = text
        self.voice_name = voice_name
        self.voice_speed = voice_speed
        self.temp_dir = temp_dir
        self.cache_temp_dir = cache_temp_dir

    def run(self):
        try:
            engine = EngineRuntime()
            preview_temp_dir = self.temp_dir or os.path.join(self.workspace_root, "temp", "segment_audio_preview")
            os.makedirs(preview_temp_dir, exist_ok=True)
            cache_temp_dir = self.cache_temp_dir or preview_temp_dir
            os.makedirs(cache_temp_dir, exist_ok=True)

            requested_speed = clamp_requested_speed(float(self.voice_speed))
            v_provider = voice_provider(self.voice_name)
            provider_speed = provider_native_speed(
                provider=v_provider,
                requested_speed=requested_speed,
            )
            residual_speed = (requested_speed / provider_speed) if provider_speed > 0.0 else requested_speed

            cache_key = segment_cache_key(text=self.text, voice_name=self.voice_name,
                                          provider_speed=provider_speed)
            base_wav_path = os.path.join(cache_temp_dir, f"tts_{cache_key}.wav")
            import uuid
            staging_path = os.path.join(cache_temp_dir, f"tts_{uuid.uuid4().hex}.partial.wav")
            engine.synthesize_segment(
                text=self.text,
                wav_path=staging_path,
                voice=self.voice_name,
                speed=provider_speed,
                tmp_dir=cache_temp_dir,
            )
            from services.voice_timing_service import wav_duration
            if wav_duration(staging_path) <= 0:
                raise ValueError("Generated voice is empty.")
            os.replace(staging_path, base_wav_path)

            manifest = load_manifest(cache_temp_dir)
            manifest_segments = dict(manifest.get("segments", {}) or {})
            manifest_by_cache_key = dict(manifest.get("by_cache_key", {}) or {})
            cache_key = segment_cache_key(
                text=self.text,
                voice_name=self.voice_name,
                provider_speed=provider_speed,
            )
            manifest_entry = {
                "cache_key": cache_key,
                "wav_path": base_wav_path,
                "text": self.text,
                "voice_name": self.voice_name,
                "provider_speed": provider_speed,
            }
            manifest_segments[str(self.index)] = manifest_entry
            manifest_by_cache_key[cache_key] = dict(manifest_entry)
            manifest["segments"] = manifest_segments
            manifest["by_cache_key"] = manifest_by_cache_key
            save_manifest(cache_temp_dir, manifest)

            wav_path = os.path.join(preview_temp_dir, f"segment_{self.index}_{os.getpid()}.wav")
            if abs(residual_speed - 1.0) >= 0.02:
                output = engine.change_wav_speed(
                    input_wav_path=base_wav_path,
                    output_wav_path=wav_path,
                    speed_ratio=residual_speed,
                )
            else:
                output = base_wav_path
            self.finished.emit(self.index, output, "")
        except Exception as exc:
            details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
            self.finished.emit(self.index, "", details or str(exc))


class VoiceSamplePreviewWorker(QThread):
    finished = Signal(str, str)
    progress = Signal(str)

    def __init__(self, workspace_root, text, voice_name, voice_speed, temp_dir=""):
        super().__init__()
        self.workspace_root = workspace_root
        self.text = text
        self.voice_name = voice_name
        self.voice_speed = voice_speed
        self.temp_dir = temp_dir

    def run(self):
        try:
            temp_dir = self.temp_dir or os.path.join(self.workspace_root, "temp", "voice_sample_preview")
            os.makedirs(temp_dir, exist_ok=True)
            cache_seed = f"voice-v3|{self.voice_name}|{self.voice_speed}|{self.text}".encode("utf-8", errors="replace")
            cache_key = hashlib.sha1(cache_seed).hexdigest()[:16]
            wav_path = os.path.join(temp_dir, f"voice_sample_{cache_key}.wav")
            base_wav_path = os.path.join(temp_dir, f"voice_sample_{cache_key}_base.wav")
            if abs(float(self.voice_speed) - 1.0) >= 0.02:
                if self._is_preview_audio_usable(wav_path):
                    self.finished.emit(self._normalize_preview_wav(wav_path, temp_dir=temp_dir), "")
                    return
                self._remove_if_exists(wav_path)
            elif os.path.exists(base_wav_path):
                if self._is_preview_audio_usable(base_wav_path):
                    self.finished.emit(self._normalize_preview_wav(base_wav_path, temp_dir=temp_dir), "")
                    return
                self._remove_if_exists(base_wav_path)
            engine = EngineRuntime()
            staging_base_wav_path = os.path.join(temp_dir, f"voice_sample_{cache_key}_base_work.wav")
            self._remove_if_exists(staging_base_wav_path)
            engine.synthesize_segment(
                text=self.text,
                wav_path=staging_base_wav_path,
                voice=self.voice_name,
                speed=1.0,
                tmp_dir=temp_dir,
                on_progress=self.progress.emit,
            )
            if not self._is_preview_audio_usable(staging_base_wav_path):
                raise RuntimeError("Generated voice preview audio is empty or invalid.")
            os.replace(staging_base_wav_path, base_wav_path)
            speed_value = float(self.voice_speed)
            if abs(speed_value - 1.0) >= 0.02:
                self._remove_if_exists(wav_path)
                output = engine.change_wav_speed(
                    input_wav_path=base_wav_path,
                    output_wav_path=wav_path,
                    speed_ratio=speed_value,
                )
            else:
                output = base_wav_path
            if not self._is_preview_audio_usable(output):
                raise RuntimeError("Voice preview audio could not be prepared for playback.")
            output = self._normalize_preview_wav(output, temp_dir=temp_dir)
            if not self._is_preview_audio_usable(output):
                raise RuntimeError("Normalized voice preview audio is empty or invalid.")
            self.finished.emit(output, "")
        except Exception as exc:
            details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
            self.finished.emit("", details or str(exc))

    def _normalize_preview_wav(self, wav_path: str, *, temp_dir: str) -> str:
        candidate = str(wav_path or "").strip()
        if not candidate or not os.path.exists(candidate):
            return candidate
        try:
            normalized_path = os.path.join(temp_dir, f"{Path(candidate).stem}_normalized.wav")
            ffmpeg_path = Path(bin_path("ffmpeg", "ffmpeg.exe"))
            if ffmpeg_path.exists():
                cmd = [
                    str(ffmpeg_path),
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    candidate,
                    "-vn",
                    "-c:a",
                    "pcm_s16le",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    normalized_path,
                ]
                proc = subprocess.run(
                    cmd, capture_output=True, text=True,
                    **subprocess_hidden_kwargs(),
                )
                if proc.returncode == 0 and self._is_preview_audio_usable(normalized_path):
                    return normalized_path
        except Exception:
            pass
        return candidate

    def _is_preview_audio_usable(self, audio_path: str) -> bool:
        candidate = str(audio_path or "").strip()
        if not candidate or not os.path.exists(candidate):
            return False
        if os.path.getsize(candidate) <= 44:
            return False
        ffprobe_path = Path(bin_path("ffmpeg", "ffprobe.exe"))
        if not ffprobe_path.exists():
            return True
        try:
            proc = subprocess.run(
                [str(ffprobe_path), "-v", "error", "-show_streams", candidate],
                capture_output=True,
                text=True,
                **subprocess_hidden_kwargs(),
            )
            return proc.returncode == 0 and bool((proc.stdout or "").strip())
        except Exception:
            return False

    def _remove_if_exists(self, path: str) -> None:
        candidate = str(path or "").strip()
        if not candidate:
            return
        try:
            if os.path.exists(candidate):
                os.remove(candidate)
        except Exception:
            pass


class VoiceExportWorker(QThread):
    """Encodes or copies pure TTS voice audio to MP3 or WAV in the background."""

    finished = Signal(bool, str, str)  # (success, output_path, error_message)
    progress = Signal(int, str)

    def __init__(self, input_wav: str, output_path: str, bitrate: str = "256k"):
        super().__init__()
        self.input_wav = str(input_wav or "").strip()
        self.output_path = str(output_path or "").strip()
        self.bitrate = str(bitrate or "256k").strip()

    def _copy_voice_report(self):
        source = self.input_wav + ".json"
        if os.path.isfile(source) and os.path.abspath(source) != os.path.abspath(self.output_path + ".json"):
            shutil.copy2(source, self.output_path + ".json")

    def run(self):
        partial_path = ""
        try:
            self.progress.emit(10, "Preparing audio export...")
            if not self.input_wav or not os.path.exists(self.input_wav):
                self.finished.emit(False, "", f"Source voice file not found: {self.input_wav}")
                return

            out_dir = os.path.dirname(os.path.abspath(self.output_path))
            if out_dir and not os.path.exists(out_dir):
                os.makedirs(out_dir, exist_ok=True)

            if self.output_path.lower().endswith(".wav"):
                self.progress.emit(50, "Copying WAV audio...")
                if os.path.abspath(self.input_wav) != os.path.abspath(self.output_path):
                    partial_path = os.path.join(
                        out_dir, f".{os.path.basename(self.output_path)}.{uuid.uuid4().hex}.partial.wav"
                    )
                    shutil.copy2(self.input_wav, partial_path)
                    os.replace(partial_path, self.output_path)
                self._copy_voice_report()
                self.progress.emit(100, "WAV audio exported successfully.")
                self.finished.emit(True, self.output_path, "")
                return

            ffmpeg = bin_path("ffmpeg", "ffmpeg.exe")
            if not os.path.exists(ffmpeg):
                self.finished.emit(False, "", f"FFmpeg not found at {ffmpeg}")
                return

            self.progress.emit(30, "Encoding MP3 audio...")
            partial_path = os.path.join(
                out_dir, f".{os.path.basename(self.output_path)}.{uuid.uuid4().hex}.partial.mp3"
            )
            cmd = [
                ffmpeg,
                "-y",
                "-i",
                self.input_wav,
                "-vn",
                "-c:a",
                "libmp3lame",
                "-b:a",
                self.bitrate,
                "-ar",
                "44100",
                partial_path,
            ]
            kwargs = subprocess_hidden_kwargs()
            proc = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
            if proc.returncode == 0 and os.path.exists(partial_path) and os.path.getsize(partial_path) > 0:
                os.replace(partial_path, self.output_path)
                self._copy_voice_report()
                self.progress.emit(100, "MP3 audio exported successfully.")
                self.finished.emit(True, self.output_path, "")
            else:
                err = (proc.stderr or proc.stdout or "FFmpeg MP3 export failed.").strip()
                self.finished.emit(False, "", err)
        except Exception as exc:
            self.finished.emit(False, "", str(exc))
        finally:
            if partial_path and os.path.exists(partial_path):
                try:
                    os.remove(partial_path)
                except OSError:
                    pass

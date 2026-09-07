import importlib.util
import os
import re
import time
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed

from services import EngineRuntime, ProjectService
from translation import render_prompt

# Force-load from app/utils/ (ui/utils/ may shadow it)
_vpu_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "utils", "voice_preview_utils.py")
_vpu_spec = importlib.util.spec_from_file_location("viustudio_voice_preview_utils", _vpu_path)
_vpu = importlib.util.module_from_spec(_vpu_spec)
_vpu_spec.loader.exec_module(_vpu)
clamp_requested_speed = _vpu.clamp_requested_speed
load_manifest = _vpu.load_manifest
manifest_path = _vpu.manifest_path
provider_native_speed = _vpu.provider_native_speed
save_manifest = _vpu.save_manifest
segment_cache_key = _vpu.segment_cache_key
voice_provider = _vpu.voice_provider


def predict_speed_ratios(segments):
    if not segments:
        return segments
    try:
        from tts_processor import normalize_text_for_tts as _norm
    except Exception:
        _norm = lambda t, **kw: t
    for seg in (segments or []):
        is_dict = isinstance(seg, dict)
        pre_speed = seg.get("pre_speed_ratio") if is_dict else getattr(seg, "pre_speed_ratio", None)
        if pre_speed is not None:
            continue
        if is_dict:
            raw_text = " ".join(str(seg.get("dubbing_vi") or seg.get("text") or seg.get("final_text") or "").replace("\n", " ").split()).strip()
            start_val = float(seg.get("start", 0.0) or 0.0)
            end_val = float(seg.get("end", 0.0) or 0.0)
        else:
            raw_text = " ".join(str(getattr(seg, "tts_text", "") or getattr(seg, "final_text", "") or getattr(seg, "original_text", "") or getattr(seg, "text", "") or "").replace("\n", " ").split()).strip()
            start_val = float(getattr(seg, "start", 0.0) or 0.0)
            end_val = float(getattr(seg, "end", 0.0) or 0.0)
        if not raw_text:
            if is_dict:
                seg["pre_speed_ratio"] = 1.0
            else:
                setattr(seg, "pre_speed_ratio", 1.0)
            continue
        text = _norm(raw_text, provider="piper") or raw_text
        duration_sec = max(0.1, end_val - start_val)
        words = len([t for t in re.split(r"\s+", text) if t])
        speech_cost = 0
        value = text
        if re.search(r"\d", value):
            speech_cost += 2
        if re.search(r"\b(19|20)\d{2}\b", value):
            speech_cost += 2
        if re.search(r"[A-Za-z]+\d+|\d+[A-Za-z]+", value):
            speech_cost += 2
        if re.search(r"[A-Z]", value) or re.search(r"[A-Za-z]{4,}", value) or re.search(r"[@#%&+/=_-]", value):
            speech_cost += 2
        if len(re.findall(r"[,;:]", value)) >= 2:
            speech_cost += 1
        token_list = [t for t in re.split(r"\s+", value) if t]
        long_tokens = [t for t in token_list if len(re.sub(r"[^\w]", "", t, flags=re.UNICODE)) >= 7]
        if len(long_tokens) >= 2:
            speech_cost += 1
        wps = 4.0 if speech_cost >= 3 else 4.5
        max_words = max(1, int(duration_sec * wps))
        ratio = round(words / max(1, max_words), 3) if max_words > 0 else 1.0
        if is_dict:
            seg["pre_speed_ratio"] = ratio
        else:
            setattr(seg, "pre_speed_ratio", ratio)
    return segments


class VoiceWorkflow:
    MAX_TTS_WORKERS = 6
    # Piper synthesis uses the Python piper library in-process, so threads can
    # share the loaded model without GIL contention on the ONNX inference side.
    # 6 workers for a 12-core machine; override with VIUSTUDIO_PIPER_TTS_WORKERS env.
    PIPER_TTS_WORKERS = 6
    AI_REWRITE_RATIO = 1.05
    SMART_RETRY_RATIO = 1.15
    HARD_RETRY_RATIO = 1.30
    HARD_OUTLIER_RATIO = 1.20
    RETRY_MIN_ACCEPT_RATIO = 0.88
    RESCUE_MIN_ACCEPT_RATIO = 0.88
    MAX_SAFE_SEGMENT_SPEED = 1.12
    MAX_STUBBORN_SEGMENT_SPEED = 1.10
    MAX_ENGLISH_DENSE_RUN_SPEED = 1.35
    DENSE_RUN_MAX_GAP_SECONDS = 0.50
    TARGET_RATIO_FLOOR = 0.84
    TARGET_RATIO_CEIL = 1.08
    VOICE_COLLISION_GUARD_SECONDS = 0.04

    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.project_service = ProjectService(workspace_root)
        self.engine_runtime = EngineRuntime()
    def _load_state(self, project_state_path: str = ""):
        return self.project_service.load_project(project_state_path) if project_state_path else None

    def _measure_audio_loudness_db(self, audio_path: str) -> float:
        """Measure mean loudness in dBFS using pydub."""
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(audio_path)
            return float(audio.dBFS)
        except Exception as exc:
            print(f"[Voice Workflow] Loudness measurement failed for {audio_path}: {exc}")
            return 0.0

    def _compute_background_gain_compensation(self, original_audio_path: str, background_path: str) -> float:
        """Compute gain needed to make separated background match original audio loudness."""
        if not original_audio_path or not os.path.exists(original_audio_path):
            return 0.0
        if not background_path or not os.path.exists(background_path):
            return 0.0
        try:
            orig_loudness = self._measure_audio_loudness_db(original_audio_path)
            bg_loudness = self._measure_audio_loudness_db(background_path)
            if orig_loudness == float("-inf") or bg_loudness == float("-inf"):
                return 0.0
            compensation = orig_loudness - bg_loudness
            # Clamp to reasonable range (-12 to +12 dB)
            compensation = max(-12.0, min(12.0, compensation))
            print(
                f"[Voice Workflow] Auto-gain: original={orig_loudness:.2f}dBFS, "
                f"background={bg_loudness:.2f}dBFS, compensation={compensation:+.2f}dB"
            )
            return compensation
        except Exception as exc:
            print(f"[Voice Workflow] Auto-gain compensation failed: {exc}")
            return 0.0

    def _percent_to_db(self, percent: int) -> float:
        """Convert volume percentage (0-200) to dB gain."""
        if percent <= 0:
            return -60.0
        import math
        return 20.0 * math.log10(percent / 100.0)

    def _mark_started(self, state, *, with_background: bool):
        if not state:
            return
        self.project_service.update_step(state, "generate_tts", "running", save=False)
        if with_background:
            self.project_service.update_step(state, "mix_audio", "running", save=False)
        self.project_service.save_project(state)

    def _mark_completed(self, state, *, voice_track: str, mixed_path: str, background_path: str, segments=None):
        if not state:
            return
        self.project_service.update_artifact(state, "voice_vi", voice_track, save=False)
        self.project_service.update_step(state, "generate_tts", "done", save=False)
        if segments:
            self.project_service.save_json_artifact(
                state,
                "voice_segments",
                os.path.join("audio", "voice_segments.json"),
                list(segments or []),
            )
        if mixed_path:
            self.project_service.update_artifact(state, "mixed_vi", mixed_path, save=False)
            self.project_service.update_step(state, "mix_audio", "done", save=False)
        elif background_path:
            self.project_service.update_step(state, "mix_audio", "skipped", save=False)
        self.project_service.save_project(state)

    def _load_manifest(self, tmp_dir: str) -> dict:
        return load_manifest(tmp_dir)

    def _save_manifest(self, tmp_dir: str, manifest: dict) -> None:
        save_manifest(tmp_dir, manifest)

    def _update_manifest_entries(self, *, tmp_dir: str, segments, wavs, voice_name: str, provider_speed: float) -> None:
        manifest = load_manifest(tmp_dir)
        manifest_segments = dict(manifest.get("segments", {}) or {})
        manifest_by_cache_key = dict(manifest.get("by_cache_key", {}) or {})
        for idx, (seg, wav_path) in enumerate(zip(list(segments or []), list(wavs or []))):
            text = self._segment_tts_text(seg)
            if not text or not wav_path or not os.path.exists(wav_path):
                continue
            segment_voice_name = str((seg or {}).get("voice_name") or voice_name).strip() or voice_name
            cache_key = segment_cache_key(
                text=text,
                voice_name=segment_voice_name,
                provider_speed=provider_speed,
            )
            entry = {
                "cache_key": cache_key,
                "wav_path": str(wav_path),
                "text": text,
                "voice_name": segment_voice_name,
                "provider_speed": float(provider_speed),
            }
            manifest_segments[str(idx)] = entry
            manifest_by_cache_key[cache_key] = dict(entry)
        manifest["segments"] = manifest_segments
        manifest["by_cache_key"] = manifest_by_cache_key
        save_manifest(tmp_dir, manifest)

    def _segment_cache_key(self, *, text: str, voice_name: str, provider_speed: float) -> str:
        return segment_cache_key(text=text, voice_name=voice_name, provider_speed=provider_speed)

    def _voice_provider(self, voice_name: str) -> str:
        return voice_provider(voice_name)

    def _segment_tts_text(self, seg: dict) -> str:
        current = dict(seg or {})
        subtitle_text = str(current.get("text") or "").strip()
        if bool(current.get("voice_edited")):
            edited_text = str(current.get("tts_text") or current.get("dubbing_vi") or "").strip()
            if edited_text:
                return edited_text
        return subtitle_text

    def _provider_native_speed(self, *, provider: str, requested_speed: float) -> float:
        return provider_native_speed(provider=provider, requested_speed=requested_speed)

    def _clamp_requested_speed(self, requested_speed: float) -> float:
        return clamp_requested_speed(requested_speed)

    def _count_words(self, text: str) -> int:
        return len([token for token in re.split(r"\s+", str(text or "").strip()) if token])

    def _normalized_tts_text(self, text: str, *, voice_provider: str = "") -> str:
        from tts_processor import normalize_text_for_tts
        return " ".join(
            str(normalize_text_for_tts(text, provider=voice_provider or "piper") or "").replace("\n", " ").split()
        ).strip()

    def _count_spoken_words(self, text: str, *, voice_provider: str = "") -> int:
        normalized = self._normalized_tts_text(text, voice_provider=voice_provider)
        return self._count_words(normalized)

    def _spoken_budget_vi(self, *, duration_sec: float, speech_cost: int) -> int:
        base_budget = self._max_words_vi(duration_sec, speech_cost)
        if speech_cost >= 5:
            return max(1, base_budget - 1)
        return base_budget

    def _estimate_speech_cost(self, text: str) -> int:
        value = str(text or "").strip()
        if not value:
            return 0
        score = 0
        if re.search(r"\d", value):
            score += 2
        if re.search(r"\b(19|20)\d{2}\b", value):
            score += 2
        if re.search(r"[A-Za-z]+\d+|\d+[A-Za-z]+", value):
            score += 2
        if re.search(r"[A-Z]", value) or re.search(r"[A-Za-z]{4,}", value) or re.search(r"[@#%&+/=_-]", value):
            score += 2
        if len(re.findall(r"[,;:]", value)) >= 2:
            score += 1
        words = [token for token in re.split(r"\s+", value) if token]
        long_words = [token for token in words if len(re.sub(r"[^\w]", "", token, flags=re.UNICODE)) >= 7]
        if len(long_words) >= 2:
            score += 1
        multi_syllable = [
            token for token in words
            if len([part for part in re.split(r"[-_./]", token) if part]) >= 2
        ]
        if len(multi_syllable) >= max(2, len(words) // 2):
            score += 1
        if re.search(r"\b(api|iphone|pro|max|ultra|beta|gpu|cpu|ai|2tb|512gb|256gb)\b", value, flags=re.IGNORECASE):
            score += 1
        return score

    def _max_words_vi(self, duration_sec: float, speech_cost: int) -> int:
        duration = max(0.0, float(duration_sec))
        words_per_sec = 4.0 if speech_cost >= 3 else 4.5
        return max(1, int(duration * words_per_sec))

    def _target_words_for_ratio(
        self,
        *,
        current_words: int,
        current_spoken_words: int,
        max_words_vi: int,
        ratio: float,
        action: str,
        attempt: int,
    ) -> int:
        ratio_value = max(1.0, float(ratio or 1.0))
        desired_from_ratio = int(current_spoken_words / ratio_value) if current_spoken_words > 0 else current_words
        if action == "compress_light":
            margin = 0 if attempt <= 1 else 1
        elif action == "compress_aggressive":
            margin = 1 + max(0, attempt - 1)
        else:
            margin = max(1, min(2, current_words - 1))
        target_words = min(max_words_vi, desired_from_ratio - margin, current_words - 1)
        return max(1, target_words)

    def _target_words_for_spoken_budget(
        self,
        *,
        text: str,
        duration_sec: float,
        speech_cost: int,
        max_words_vi: int,
        voice_provider: str = "",
    ) -> int:
        spoken_budget = self._spoken_budget_vi(duration_sec=duration_sec, speech_cost=speech_cost)
        raw_words = max(1, self._count_words(text))
        spoken_words = max(1, self._count_spoken_words(text, voice_provider=voice_provider))
        if spoken_words <= spoken_budget:
            return max_words_vi
        shrink_ratio = spoken_budget / spoken_words
        adjusted = int(raw_words * shrink_ratio)
        return max(1, min(max_words_vi, adjusted))

    def _trim_text_for_tts(self, text: str, *, duration_sec: float, max_words_vi: int) -> str:
        value = " ".join(str(text or "").replace("\n", " ").split()).strip()
        if not value:
            return ""

        tokens = value.split()
        if duration_sec < 0.8:
            return " ".join(tokens[: min(2, len(tokens))]).strip()

        if len(tokens) <= max_words_vi:
            return value

        filler_words = {
            "thì", "là", "mà", "đó", "ấy", "nha", "nhé", "à", "ờ", "ừ",
            "rất", "khá", "thực", "sự", "kiểu", "như", "vậy", "luôn",
        }
        compact_tokens = []
        for token in tokens:
            cleaned = re.sub(r"[^\wÀ-ỹ]", "", token, flags=re.UNICODE).lower()
            if cleaned in filler_words:
                continue
            compact_tokens.append(token)

        if len(compact_tokens) < max_words_vi:
            compact_tokens = tokens

        return " ".join(compact_tokens[:max_words_vi]).strip(" ,.;:!?")

    def _keyword_only_text(self, text: str) -> str:
        value = " ".join(str(text or "").replace("\n", " ").split()).strip()
        if not value:
            return ""
        tokens = value.split()
        protected = []
        for token in tokens:
            cleaned = re.sub(r"[^\wÀ-ỹ]", "", token, flags=re.UNICODE)
            if not cleaned:
                continue
            if re.search(r"\d", cleaned) or re.search(r"[A-Z]", cleaned) or len(cleaned) >= 5:
                protected.append(token)
        shortlist = protected[:2] if protected else tokens[:2]
        return " ".join(shortlist).strip(" ,.;:!?")

    def _compress_text_to_budget(self, text: str, *, duration_sec: float, max_words_vi: int, mode: str = "light") -> str:
        value = " ".join(str(text or "").replace("\n", " ").split()).strip()
        if not value:
            return ""
        if mode == "keyword_only":
            return self._keyword_only_text(value)

        compact = self._trim_text_for_tts(value, duration_sec=duration_sec, max_words_vi=max_words_vi)
        if mode != "aggressive":
            return compact

        tokens = compact.split()
        if len(tokens) <= 2:
            return compact
        keep = max(1, min(max_words_vi, len(tokens) - max(1, len(tokens) // 4)))
        protected = []
        for token in tokens:
            cleaned = re.sub(r"[^\wÀ-ỹ]", "", token, flags=re.UNICODE)
            if re.search(r"\d", cleaned) or re.search(r"[A-Z]", cleaned):
                protected.append(token)
        compressed = tokens[:keep]
        for token in protected:
            if token not in compressed and len(compressed) < max_words_vi:
                compressed.append(token)
        return " ".join(compressed[:max_words_vi]).strip(" ,.;:!?")

    def _validate_initial_dubbing_text(
        self,
        *,
        source_text: str,
        subtitle_text: str,
        dubbing_text: str,
        duration_sec: float,
        max_words_vi: int,
        speech_cost: int,
        voice_provider: str = "",
    ) -> tuple[str, str]:
        value = " ".join(str(dubbing_text or "").replace("\n", " ").split()).strip()
        if not value:
            fallback = " ".join(str(subtitle_text or source_text or "").replace("\n", " ").split()).strip()
            value = fallback
        if duration_sec < 0.8:
            return self._keyword_only_text(source_text or subtitle_text), "keyword_only"
        spoken_budget = self._spoken_budget_vi(duration_sec=duration_sec, speech_cost=speech_cost)
        spoken_over_budget = self._count_spoken_words(value, voice_provider=voice_provider) > spoken_budget
        if self._count_words(value) > max_words_vi or spoken_over_budget:
            compact = self._compress_text_to_budget(
                value,
                duration_sec=duration_sec,
                max_words_vi=min(max_words_vi, spoken_budget),
                mode="light",
            )
            if compact:
                return compact, "compress_light"
        return value, "accept"

    def _retry_cap_for_segment(self, *, duration_sec: float, speech_cost: int) -> int:
        return 3 if (duration_sec < 1.8 or speech_cost >= 4) else 2

    def _choose_retry_action(self, *, duration_sec: float, speech_cost: int, ratio: float, attempt: int, retry_cap: int) -> str:
        if duration_sec < 0.8:
            return "keyword_only"
        if ratio <= 1.05:
            return "accept"
        if duration_sec < 1.2 and ratio > 1.05:
            return "compress_aggressive" if attempt > 1 else "compress_light"
        if duration_sec < 1.8 and ratio > 1.10:
            return "compress_aggressive" if attempt > 1 else "compress_light"
        if speech_cost >= 4 and ratio > 1.08:
            return "compress_aggressive" if attempt > 1 else "compress_light"
        if ratio <= 1.15:
            return "compress_light"
        if ratio <= 1.30:
            return "compress_aggressive" if attempt > 1 else "compress_light"
        if attempt >= retry_cap:
            return "keyword_only"
        return "compress_aggressive"

    def _should_use_speedup_before_rewrite(self, *, duration_sec: float, speech_cost: int, ratio: float) -> bool:
        ratio_value = float(ratio or 0.0)
        if ratio_value <= 1.05:
            return False
        if duration_sec < 1.8 or speech_cost >= 4:
            return False
        return ratio_value <= 1.15

    def _should_allow_post_rewrite_speedup(self, *, ratio: float) -> bool:
        return 1.05 < float(ratio or 0.0) <= 1.15

    def _is_target_ratio_band(self, ratio: float) -> bool:
        ratio_value = float(ratio or 0.0)
        return self.TARGET_RATIO_FLOOR <= ratio_value <= self.TARGET_RATIO_CEIL

    def _segment_speed_ratio_for_outlier(
        self,
        *,
        duration_sec: float,
        speech_cost: int,
        ratio: float,
    ) -> float:
        ratio_value = float(ratio or 0.0)
        if ratio_value <= 1.15:
            return 1.0
        if duration_sec < 0.8:
            return 1.0
        if ratio_value <= 1.20 and speech_cost >= 4:
            return min(self.MAX_SAFE_SEGMENT_SPEED, max(1.03, ratio_value / 1.06))
        if ratio_value <= 1.28:
            base = ratio_value / 1.10
            return min(self.MAX_SAFE_SEGMENT_SPEED, max(1.05, base))
        return self.MAX_SAFE_SEGMENT_SPEED

    def _segment_speed_ratio_for_medium_overrun(self, *, ratio: float) -> float:
        ratio_value = float(ratio or 0.0)
        if ratio_value <= 1.08 or ratio_value > 1.16:
            return 1.0
        if ratio_value <= 1.11:
            return 1.03
        if ratio_value <= 1.14:
            return 1.045
        return 1.06

    def _segment_speed_ratio_for_stubborn_segment(
        self,
        *,
        duration_sec: float,
        speech_cost: int,
        ratio: float,
        attempt_count: int,
        segment_index: int,
    ) -> float:
        ratio_value = float(ratio or 0.0)
        if ratio_value <= 1.12:
            return 1.0
        if duration_sec < 0.8:
            return 1.0
        if attempt_count < 2 and speech_cost < 4 and segment_index != 0:
            return 1.0
        if ratio_value <= 1.18:
            return min(self.MAX_STUBBORN_SEGMENT_SPEED, 1.04 if segment_index != 0 else 1.06)
        if ratio_value <= 1.24:
            return min(self.MAX_STUBBORN_SEGMENT_SPEED, 1.07 if speech_cost >= 4 or segment_index == 0 else 1.05)
        return self.MAX_STUBBORN_SEGMENT_SPEED

    def _finalize_segment_result(
        self,
        *,
        seg: dict,
        wav_path: str,
        target_duration: float,
        attempt_count: int,
        action_taken: str,
    ) -> None:
        metrics = dict(seg.get("_tts_metrics") or {})
        tts_duration = self._probe_wav_duration_seconds(wav_path)
        ratio = (tts_duration / target_duration) if target_duration > 0 else 0.0
        metrics["tts_duration"] = round(tts_duration, 3)
        metrics["ratio"] = round(ratio, 3)
        metrics["attempt_count"] = int(max(1, attempt_count))
        metrics["action_taken"] = action_taken
        seg["_tts_metrics"] = metrics
        seg["subtitle_vi"] = (seg.get("subtitle_vi") or seg.get("text") or "").strip()
        seg["dubbing_vi"] = self._segment_tts_text(seg)
        seg["tts_duration"] = metrics["tts_duration"]
        seg["ratio"] = metrics["ratio"]
        seg["attempt_count"] = metrics["attempt_count"]
        seg["action_taken"] = metrics["action_taken"]

    def _rewrite_segment_with_ai(
        self,
        *,
        source_text: str,
        draft_text: str,
        duration_sec: float,
        speech_cost: int,
        max_words_vi: int,
        measured_ratio: float,
        action: str,
        attempt: int,
        target_words: int,
        draft_words: int,
        draft_spoken_words: int,
        source_language: str = "auto",
        style_instruction: str = "",
    ) -> str:
        source_line = (
            f"[mode=dubbing_rewrite][action={action}]"
            f"[duration={duration_sec:.2f}]"
            f"[max_words_vi={max_words_vi}]"
            f"[speech_cost={speech_cost}]"
            f"[measured_ratio={measured_ratio:.3f}]"
            f"[attempt={attempt}]"
            f"[draft_words={draft_words}]"
            f"[draft_spoken_words={draft_spoken_words}]"
            f"[target_words={target_words}] "
            f"{source_text}"
        )
        cleaned_style = " ".join(str(style_instruction or "").split()).strip()
        style_clause = f" Extra tone/style instruction: {cleaned_style}" if cleaned_style else ""
        prompt = render_prompt(
            "dubbing_timing.instruction.md",
            action=action,
            style_clause=style_clause,
        )
        rewritten_segments = self.engine_runtime.rewrite_translation_segments(
            [{"start": 0.0, "end": duration_sec, "text": source_line, "source_text": source_line}],
            [{"start": 0.0, "end": duration_sec, "text": draft_text}],
            src_lang=str(source_language or "auto"),
            style_instruction=prompt,
        )
        if not rewritten_segments:
            return draft_text
        rewritten_text = " ".join(str(rewritten_segments[0].get("text") or "").replace("\n", " ").split()).strip()
        return rewritten_text or draft_text

    def _plan_initial_dubbing_text(
        self,
        *,
        source_text: str,
        subtitle_text: str,
        duration_sec: float,
        speech_cost: int,
        max_words_vi: int,
        enabled: bool,
        source_language: str = "auto",
        style_instruction: str = "",
    ) -> str:
        if duration_sec < 0.8:
            return self._keyword_only_text(source_text or subtitle_text)

        base_text = " ".join(str(subtitle_text or source_text or "").replace("\n", " ").split()).strip()
        if not enabled:
            return base_text

        source_line = (
            f"[mode=dubbing_rewrite][action=translate_for_dubbing]"
            f"[duration={duration_sec:.2f}]"
            f"[max_words_vi={max_words_vi}]"
            f"[speech_cost={speech_cost}] "
            f"{source_text}"
        )
        cleaned_style = " ".join(str(style_instruction or "").split()).strip()
        style_clause = f" Extra tone/style instruction: {cleaned_style}" if cleaned_style else ""
        prompt = render_prompt(
            "dubbing_initial.instruction.md",
            style_clause=style_clause,
        )
        try:
            rewritten_segments = self.engine_runtime.rewrite_translation_segments(
                [{"start": 0.0, "end": duration_sec, "text": source_line, "source_text": source_line}],
                [{"start": 0.0, "end": duration_sec, "text": base_text}],
                src_lang=str(source_language or "auto"),
                style_instruction=prompt,
            )
            if not rewritten_segments:
                return base_text
            rewritten_text = " ".join(str(rewritten_segments[0].get("text") or "").replace("\n", " ").split()).strip()
            return rewritten_text or base_text
        except Exception:
            return base_text

    def _render_segment_candidate(
        self,
        *,
        text: str,
        idx: int,
        attempt: int,
        tmp_dir: str,
        voice_name: str,
        provider_speed: float,
        target_duration: float,
        on_progress: callable = None,
    ) -> tuple[str, float]:
        base_path = os.path.join(tmp_dir, f"seg_{idx:04d}_attempt_{attempt:02d}.wav")
        self.engine_runtime.synthesize_segment(
            text=text,
            wav_path=base_path,
            voice=voice_name,
            speed=provider_speed,
            tmp_dir=tmp_dir,
            on_progress=on_progress,
        )
        actual_duration = self._probe_wav_duration_seconds(base_path)
        ratio = (actual_duration / target_duration) if target_duration > 0 else 0.0
        return base_path, ratio

    def _make_retry_tts_text(self, current_text: str, *, source_text: str, duration_sec: float, ratio: float, max_words_vi: int) -> str:
        current_value = " ".join(str(current_text or "").replace("\n", " ").split()).strip()
        source_value = " ".join(str(source_text or "").replace("\n", " ").split()).strip()
        if not source_value:
            return current_value

        if duration_sec < 0.8:
            return " ".join(source_value.split()[:1]).strip(" ,.;:!?")

        current_words = self._count_words(current_value)
        if ratio <= 1.22:
            drop_words = 1
        elif ratio <= 1.35:
            drop_words = 1
        elif ratio <= 1.50:
            drop_words = 2
        else:
            drop_words = 3
        tighter_budget = max(1, min(max_words_vi, current_words - drop_words))
        retry_text = self._trim_text_for_tts(
            source_value,
            duration_sec=duration_sec,
            max_words_vi=tighter_budget,
        )
        if retry_text and retry_text != current_value:
            return retry_text

        current_tokens = current_value.split()
        if len(current_tokens) <= 1:
            return current_value
        drop_count = 1 if ratio <= 1.50 else 2
        return " ".join(current_tokens[: max(1, len(current_tokens) - drop_count)]).strip(" ,.;:!?")

    def _rebalance_too_short_candidate(
        self,
        current_text: str,
        *,
        source_text: str,
        duration_sec: float,
        current_words: int,
        candidate_words: int,
        max_words_vi: int,
    ) -> str:
        if current_words <= 2:
            return current_text
        softened_budget = max(
            candidate_words + 1,
            min(max_words_vi, current_words - 1),
        )
        softened = self._compress_text_to_budget(
            current_text or source_text,
            duration_sec=duration_sec,
            max_words_vi=softened_budget,
            mode="light",
        )
        softened = " ".join(str(softened or "").replace("\n", " ").split()).strip()
        if softened and softened != current_text:
            return softened
        fallback_budget = max(1, min(max_words_vi, current_words - 1))
        fallback = self._trim_text_for_tts(
            source_text or current_text,
            duration_sec=duration_sec,
            max_words_vi=fallback_budget,
        )
        fallback = " ".join(str(fallback or "").replace("\n", " ").split()).strip()
        return fallback or current_text

    def _hard_outlier_candidate_text(
        self,
        *,
        current_text: str,
        source_text: str,
        duration_sec: float,
        max_words_vi: int,
        ratio: float,
    ) -> str:
        current_words = self._count_words(current_text)
        emergency_budget = max(
            1,
            min(
                max_words_vi,
                current_words - 1,
                int(max(1.0, current_words / max(1.05, float(ratio or 1.0)))) - 1,
            ),
        )
        aggressive = self._compress_text_to_budget(
            source_text or current_text,
            duration_sec=duration_sec,
            max_words_vi=emergency_budget,
            mode="aggressive",
        )
        aggressive = " ".join(str(aggressive or "").replace("\n", " ").split()).strip()
        if aggressive and aggressive != current_text:
            return aggressive
        if current_words > 2:
            compact = " ".join(current_text.split()[: max(1, current_words - 2)]).strip(" ,.;:!?")
            if compact and compact != current_text:
                return compact
        return self._keyword_only_text(source_text or current_text)

    def _prepare_segments_for_tts(
        self,
        segments,
        *,
        voice_provider: str = "",
        ai_rewrite_dubbing: bool = False,
        source_language: str = "auto",
        style_instruction: str = "",
        log: bool = True,
    ):
        from services import AsrVocalizationFilterService

        source_segments = list(segments or [])
        source_segments, suppressed_count = AsrVocalizationFilterService.filter_tts_segments(
            source_segments
        )
        if log and suppressed_count:
            print(
                "[Voice Workflow] Suppressed "
                f"{suppressed_count} stale filler-only cue(s) before TTS."
            )
        prepared = []
        for seg in source_segments:
            current = dict(seg or {})
            subtitle_text = (current.get("text") or "").strip()
            voice_edited = bool(current.get("voice_edited"))
            spoken_text = self._segment_tts_text(current)
            duration_sec = max(0.0, float(current.get("end", 0.0)) - float(current.get("start", 0.0)))
            speech_cost = self._estimate_speech_cost(subtitle_text)
            max_words_vi = self._max_words_vi(duration_sec, speech_cost)
            original_words = self._count_words(subtitle_text)
            spoken_words = self._count_spoken_words(spoken_text, voice_provider=voice_provider)
            action_taken = "manual_voice" if voice_edited else "accept"
            current["tts_text"] = spoken_text if voice_edited and spoken_text != subtitle_text else ""
            current["dubbing_vi"] = spoken_text
            current["subtitle_vi"] = subtitle_text
            current["voice_edited"] = voice_edited
            final_spoken_words = spoken_words
            current["_tts_metrics"] = {
                "duration_sec": round(duration_sec, 3),
                "speech_cost": speech_cost,
                "max_words_vi": max_words_vi,
                "original_words": original_words,
                "spoken_words": spoken_words,
                "tts_words": self._count_words(spoken_text),
                "tts_spoken_words": final_spoken_words,
                "retry_cap": self._retry_cap_for_segment(duration_sec=duration_sec, speech_cost=speech_cost),
                "action_taken": action_taken,
                "trimmed": bool(voice_edited and spoken_text != subtitle_text),
                "subtitle_vi": subtitle_text,
                "dubbing_vi": spoken_text,
                "voice_edited": voice_edited,
            }
            prepared.append(current)
        if log:
            print(f"[Voice Workflow] Prepared TTS text: adjusted=0/{len(prepared)}")
        return prepared

    def _probe_wav_duration_seconds(self, wav_path: str) -> float:
        if not wav_path or not os.path.exists(wav_path):
            return 0.0
        with wave.open(wav_path, "rb") as wav_file:
            frame_rate = wav_file.getframerate() or 16000
            frame_count = wav_file.getnframes()
        return max(0.0, float(frame_count) / float(frame_rate))

    def _write_silence_wav(self, wav_path: str, duration_seconds: float) -> str:
        duration = max(0.2, float(duration_seconds or 0.0))
        sample_rate = 16000
        frame_count = max(1, int(round(duration * sample_rate)))
        os.makedirs(os.path.dirname(wav_path) or ".", exist_ok=True)
        with wave.open(wav_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(b"\x00\x00" * frame_count)
        return wav_path

    def _log_segment_fit_metrics(self, *, segments, wavs):
        clipped = 0
        total = 0
        min_ratio = None
        max_ratio = None
        for idx, (seg, wav_path) in enumerate(zip(list(segments or []), list(wavs or []))):
            target_duration = max(0.0, float(seg.get("end", 0.0)) - float(seg.get("start", 0.0)))
            actual_duration = self._probe_wav_duration_seconds(wav_path)
            ratio = (actual_duration / target_duration) if target_duration > 0 else 0.0
            total += 1
            min_ratio = ratio if min_ratio is None else min(min_ratio, ratio)
            max_ratio = ratio if max_ratio is None else max(max_ratio, ratio)
            if ratio > 1.05:
                clipped += 1
            self._finalize_segment_result(
                seg=seg,
                wav_path=wav_path,
                target_duration=target_duration,
                attempt_count=int((seg.get("attempt_count") or (seg.get("_tts_metrics") or {}).get("attempt_count") or 1)),
                action_taken=str((seg.get("action_taken") or (seg.get("_tts_metrics") or {}).get("action_taken") or "accept")),
            )
        print(
            f"[Voice Fit] Summary: segments={total}, over_target={clipped}/{total}, "
            f"min_ratio={(min_ratio or 0.0):.3f}, max_ratio={(max_ratio or 0.0):.3f}"
        )

    def _measure_segment_ratios(self, *, segments, wavs):
        ratios = []
        for seg, wav_path in zip(list(segments or []), list(wavs or [])):
            target_duration = max(0.0, float(seg.get("end", 0.0)) - float(seg.get("start", 0.0)))
            actual_duration = self._probe_wav_duration_seconds(wav_path) if wav_path and os.path.exists(wav_path) else 0.0
            ratios.append((actual_duration / target_duration) if target_duration > 0 else 0.0)
        return ratios

    def _save_pre_speed_ratios(self, *, segments, wavs):
        for seg, wav_path in zip(list(segments or []), list(wavs or [])):
            target_duration = max(0.0, float(seg.get("end", 0.0)) - float(seg.get("start", 0.0)))
            actual_duration = self._probe_wav_duration_seconds(wav_path) if wav_path and os.path.exists(wav_path) else 0.0
            pre_ratio = (actual_duration / target_duration) if target_duration > 0 else 1.0
            seg["pre_speed_ratio"] = round(pre_ratio, 3)

    def _accept_retry_candidate(self, *, old_ratio: float, new_ratio: float) -> bool:
        if new_ratio <= 0.0:
            return False
        if new_ratio < self.RETRY_MIN_ACCEPT_RATIO:
            return False
        if self._is_target_ratio_band(new_ratio):
            return True
        if old_ratio > 1.0 and new_ratio < 1.0 and new_ratio < 0.92:
            return False
        return abs(new_ratio - 1.0) < abs(old_ratio - 1.0)

    def _apply_segment_speed(self, *, wavs, tmp_dir: str, voice_speed: float, segments: list | None = None):
        """Apply global or per-segment voice speed to each wav."""
        adjusted_wavs = []
        for idx, wav_path in enumerate(wavs):
            if not wav_path or not os.path.exists(wav_path):
                adjusted_wavs.append(wav_path)
                continue
            seg_speed = float(voice_speed)
            if segments and idx < len(segments):
                try:
                    raw = segments[idx].get("voice_speed")
                    if raw is not None:
                        seg_speed = float(raw)
                except (TypeError, ValueError):
                    pass
            if abs(seg_speed - 1.0) < 0.02:
                adjusted_wavs.append(wav_path)
                continue
            adjusted_path = os.path.join(tmp_dir, f"seg_{idx:04d}_speed_{int(round(seg_speed * 100)):03d}.wav")
            adjusted_wavs.append(
                self.engine_runtime.change_wav_speed(
                    input_wav_path=wav_path,
                    output_wav_path=adjusted_path,
                    speed_ratio=seg_speed,
                )
            )
        return adjusted_wavs

    def _apply_safe_timing_polish(
        self,
        *,
        segments,
        wavs,
        tmp_dir: str,
        voice_speed: float,
        sync_mode: str,
    ):
        polished_wavs = list(wavs or [])
        # Apply the requested global/per-segment speed before measuring and
        # fitting to subtitle windows. Doing this after Smart Fit made a 1.2x
        # selection shorten an already-synchronized clip and reintroduced the
        # exact "voice ended, subtitle still visible" drift.
        if abs(float(voice_speed) - 1.0) >= 0.02 or any(
            seg.get("voice_speed") for seg in (segments or [])
        ):
            polished_wavs = self._apply_segment_speed(
                wavs=polished_wavs,
                tmp_dir=tmp_dir,
                voice_speed=voice_speed,
                segments=segments,
            )
        for idx, (seg, wav_path) in enumerate(zip(list(segments or []), polished_wavs)):
            if not wav_path or not os.path.exists(wav_path):
                continue
            target_duration = max(0.0, float(seg.get("end", 0.0)) - float(seg.get("start", 0.0)))
            actual_duration = self._probe_wav_duration_seconds(wav_path)
            ratio = (actual_duration / target_duration) if target_duration > 0 else 0.0

            # SMART: trim trailing silence first so the duration
            # estimate used by speed-adjustment heuristics is based
            # on actual speech, not dead air.
            if (sync_mode or "off").strip().lower() == "smart":
                trimmed_path = os.path.join(tmp_dir, f"seg_{idx:04d}_silencetrim.wav")
                trimmed = self.engine_runtime.trim_trailing_silence(
                    input_wav_path=polished_wavs[idx],
                    output_wav_path=trimmed_path,
                )
                if trimmed != polished_wavs[idx]:
                    polished_wavs[idx] = trimmed
                    actual_duration = self._probe_wav_duration_seconds(trimmed)
                    ratio = (actual_duration / target_duration) if target_duration > 0 else 0.0
                    seg["_trimmed_silence"] = True
            speech_cost = int(((seg.get("_tts_metrics") or {}).get("speech_cost")) or 0)
            duration_sec = float(((seg.get("_tts_metrics") or {}).get("duration_sec")) or target_duration)
            attempt_count = int((seg.get("attempt_count") or (seg.get("_tts_metrics") or {}).get("attempt_count") or 1))

            if self._should_use_speedup_before_rewrite(
                duration_sec=duration_sec,
                speech_cost=speech_cost,
                ratio=ratio,
            ):
                speed_ratio = min(1.15, max(1.0, ratio))
                if abs(speed_ratio - 1.0) >= 0.02:
                    adjusted_path = os.path.join(tmp_dir, f"seg_{idx:04d}_polish_speed.wav")
                    wav_path = self.engine_runtime.change_wav_speed(
                        input_wav_path=wav_path,
                        output_wav_path=adjusted_path,
                        speed_ratio=speed_ratio,
                    )
                    polished_wavs[idx] = wav_path
                    seg["action_taken"] = "speed_light"
                    metrics = dict(seg.get("_tts_metrics") or {})
                    metrics["action_taken"] = "speed_light"
                    seg["_tts_metrics"] = metrics

            actual_duration = self._probe_wav_duration_seconds(polished_wavs[idx])
            ratio = (actual_duration / target_duration) if target_duration > 0 else 0.0
            stubborn_speed = self._segment_speed_ratio_for_stubborn_segment(
                duration_sec=duration_sec,
                speech_cost=speech_cost,
                ratio=ratio,
                attempt_count=attempt_count,
                segment_index=idx,
            )
            if stubborn_speed > 1.0:
                adjusted_path = os.path.join(tmp_dir, f"seg_{idx:04d}_stubborn_speed.wav")
                polished_wavs[idx] = self.engine_runtime.change_wav_speed(
                    input_wav_path=polished_wavs[idx],
                    output_wav_path=adjusted_path,
                    speed_ratio=stubborn_speed,
                )
                seg["action_taken"] = "speed_stubborn"
                metrics = dict(seg.get("_tts_metrics") or {})
                metrics["action_taken"] = "speed_stubborn"
                metrics["stubborn_speed_ratio"] = round(stubborn_speed, 3)
                seg["_tts_metrics"] = metrics

            actual_duration = self._probe_wav_duration_seconds(polished_wavs[idx])
            ratio = (actual_duration / target_duration) if target_duration > 0 else 0.0
            rescue_speed = self._segment_speed_ratio_for_outlier(
                duration_sec=duration_sec,
                speech_cost=speech_cost,
                ratio=ratio,
            )
            if rescue_speed > 1.0 and ratio > 1.15:
                adjusted_path = os.path.join(tmp_dir, f"seg_{idx:04d}_rescue_speed.wav")
                polished_wavs[idx] = self.engine_runtime.change_wav_speed(
                    input_wav_path=polished_wavs[idx],
                    output_wav_path=adjusted_path,
                    speed_ratio=rescue_speed,
                )
                seg["action_taken"] = "speed_rescue"
                metrics = dict(seg.get("_tts_metrics") or {})
                metrics["action_taken"] = "speed_rescue"
                metrics["rescue_speed_ratio"] = round(rescue_speed, 3)
                seg["_tts_metrics"] = metrics

            actual_duration = self._probe_wav_duration_seconds(polished_wavs[idx])
            ratio = (actual_duration / target_duration) if target_duration > 0 else 0.0
            medium_speed = self._segment_speed_ratio_for_medium_overrun(ratio=ratio)
            if medium_speed > 1.0:
                adjusted_path = os.path.join(tmp_dir, f"seg_{idx:04d}_medium_speed.wav")
                polished_wavs[idx] = self.engine_runtime.change_wav_speed(
                    input_wav_path=polished_wavs[idx],
                    output_wav_path=adjusted_path,
                    speed_ratio=medium_speed,
                )
                seg["action_taken"] = "speed_balance"
                metrics = dict(seg.get("_tts_metrics") or {})
                metrics["action_taken"] = "speed_balance"
                metrics["balance_speed_ratio"] = round(medium_speed, 3)
                seg["_tts_metrics"] = metrics

            if (sync_mode or "off").strip().lower() == "smart":
                actual_duration = self._probe_wav_duration_seconds(polished_wavs[idx])
                ratio = (actual_duration / target_duration) if target_duration > 0 else 0.0
                if self._should_allow_post_rewrite_speedup(ratio=ratio):
                    synced_path = os.path.join(tmp_dir, f"seg_{idx:04d}_smartfit.wav")
                    polished_wavs[idx] = self.engine_runtime.fit_wav_to_duration(
                        input_wav_path=polished_wavs[idx],
                        output_wav_path=synced_path,
                        target_duration_seconds=target_duration,
                        mode="smart",
                    )
            if (sync_mode or "off").strip().lower() in ("timeline", "timeline priority"):
                # Timeline Priority: cut audio to fit the segment window,
                # but extend to fill gaps to the next segment to minimize cutting.
                # Calculate extended duration if there's a gap to next segment
                extended_duration = target_duration
                if idx + 1 < len(segments):
                    next_seg = segments[idx + 1]
                    next_start = float(next_seg.get("start", 0.0))
                    seg_end = float(seg.get("end", 0.0))
                    gap = next_start - seg_end
                    if gap > 0.01:  # Only extend if gap is meaningful (>10ms)
                        extended_duration = target_duration + gap
                        print(f"[Timeline Priority] Segment {idx+1}: extending by {gap:.3f}s to fill gap")
                
                synced_path = os.path.join(tmp_dir, f"seg_{idx:04d}_timelinefit.wav")
                polished_wavs[idx] = self.engine_runtime.fit_wav_to_duration(
                    input_wav_path=polished_wavs[idx],
                    output_wav_path=synced_path,
                    target_duration_seconds=extended_duration,
                    mode="timeline",
                )
        if (sync_mode or "off").strip().lower() in ("force", "force fit"):
            for idx, (seg, wav_path) in enumerate(zip(list(segments or []), polished_wavs)):
                if not wav_path or not os.path.exists(wav_path):
                    continue
                target_duration = max(0.0, float(seg.get("end", 0.0)) - float(seg.get("start", 0.0)))
                actual_duration = self._probe_wav_duration_seconds(wav_path)
                ratio = (actual_duration / target_duration) if target_duration > 0 else 0.0
                if ratio > 1.0:
                    synced_path = os.path.join(tmp_dir, f"seg_{idx:04d}_forcefit.wav")
                    polished_wavs[idx] = self.engine_runtime.fit_wav_to_duration(
                        input_wav_path=wav_path,
                        output_wav_path=synced_path,
                        target_duration_seconds=target_duration,
                        mode="force",
                    )
                    seg["action_taken"] = (seg.get("action_taken") or "") + "+force_fit"
                    seg["ratio"] = 1.0
        return polished_wavs

    def _apply_deficit_timing_polish(self, *, segments, wavs, tmp_dir, sync_mode):
        polished_wavs = list(wavs or [])
        segments = list(segments or [])
        overlap_count = 0
        stretch_count = 0
        silence_count = 0
        no_action_count = 0

        for idx, wav_path in enumerate(polished_wavs):
            if not wav_path or not os.path.exists(wav_path):
                continue
            seg = segments[idx]
            target_d = max(0.0, float(seg.get("end", 0.0)) - float(seg.get("start", 0.0)))
            actual_d = self._probe_wav_duration_seconds(wav_path)
            ratio = (actual_d / target_d) if target_d > 0 else 1.0

            if ratio >= 1.0 or ratio <= 0.01:
                continue

            gap_ms = int((target_d - actual_d) * 1000)
            if gap_ms <= 20:
                overlap_count += 1
                continue

            mode_key = (sync_mode or "off").strip().lower()

            if ratio >= 0.77 and mode_key == "smart":
                synced_path = os.path.join(tmp_dir, f"seg_{idx:04d}_deficit_stretch.wav")
                polished_wavs[idx] = self.engine_runtime.fit_wav_to_duration(
                    input_wav_path=wav_path,
                    output_wav_path=synced_path,
                    target_duration_seconds=target_d,
                    mode="smart",
                )
                seg["action_taken"] = "deficit_stretch"
                new_actual = self._probe_wav_duration_seconds(polished_wavs[idx])
                gap_ms = max(0, int((target_d - new_actual) * 1000))
                stretch_count += 1
                if gap_ms <= 20:
                    continue
            elif ratio >= 0.85:
                no_action_count += 1
                continue

            if gap_ms > 0 and ratio < 0.85:
                silence_count += 1
                continue

        print(
            "[Voice Deficit] Summary: "
            f"overlap={overlap_count}, stretch={stretch_count}, "
            f"silence_fade={silence_count}, no_action={no_action_count}"
        )
        return segments, polished_wavs

    def _fit_segment_wavs_to_timeline(self, *, segments, wavs, tmp_dir: str, sync_mode: str):
        mode_key = (sync_mode or "off").strip().lower()
        if mode_key not in {"smart", "timeline"}:
            return wavs

        synced_wavs = []
        for idx, (seg, wav_path) in enumerate(zip(segments, wavs)):
            if not wav_path or not os.path.exists(wav_path):
                synced_wavs.append(wav_path)
                continue
            target_duration = max(0.0, float(seg.get("end", 0.0)) - float(seg.get("start", 0.0)))
            suffix = "timelinefit" if mode_key == "timeline" else "smartfit"
            synced_path = os.path.join(tmp_dir, f"seg_{idx:04d}_{suffix}.wav")
            fitted_path = self.engine_runtime.fit_wav_to_duration(
                input_wav_path=wav_path,
                output_wav_path=synced_path,
                target_duration_seconds=target_duration,
                mode=mode_key,
            )
            synced_wavs.append(fitted_path)
        return synced_wavs

    @staticmethod
    def _is_english_voice(voice_name: str) -> bool:
        value = str(voice_name or "").strip().lower()
        if value.startswith("edge:"):
            value = value.split(":", 1)[1]
        return value.startswith(("en_", "en-")) or "piper-en" in value.replace("\\", "/")

    def _fit_dense_english_voice_runs(
        self,
        *,
        segments,
        wavs,
        tmp_dir: str,
        sync_mode: str,
        voice_name: str,
        requested_speed: float = 1.0,
    ):
        """Keep dense imported English subtitles from accumulating voice drift.

        YouTube subtitle timings are optimized for reading, not synthesized
        narration. English Piper audio can therefore overrun many consecutive
        cues even though each cue is valid. Serializing every overrun preserves
        words but can push narration tens of seconds behind the picture.

        For Smart mode, measure contiguous dialogue runs and apply one bounded
        catch-up ratio to the whole run. A uniform ratio sounds substantially
        more natural than changing speed cue-by-cue, while the 1.35x total cap
        avoids chipmunk speech. Sparse cues and non-English voices are untouched.
        """
        segment_list = list(segments or [])
        fitted_wavs = list(wavs or [])
        if (
            str(sync_mode or "").strip().lower() != "smart"
            or not self._is_english_voice(voice_name)
            or not segment_list
            or not fitted_wavs
        ):
            return fitted_wavs

        safe_requested_speed = max(0.1, float(requested_speed or 1.0))
        adaptive_cap = max(1.0, self.MAX_ENGLISH_DENSE_RUN_SPEED / safe_requested_speed)
        if adaptive_cap < 1.02:
            return fitted_wavs

        runs: list[list[int]] = []
        current_run: list[int] = []
        previous_end: float | None = None
        for index, seg in enumerate(segment_list[: len(fitted_wavs)]):
            wav_path = fitted_wavs[index]
            if not wav_path or not os.path.exists(wav_path):
                if current_run:
                    runs.append(current_run)
                    current_run = []
                previous_end = None
                continue
            try:
                start = float(seg.get("start", 0.0) or 0.0)
                end = float(seg.get("end", start) or start)
            except (AttributeError, TypeError, ValueError):
                continue
            if end <= start:
                continue
            if (
                current_run
                and previous_end is not None
                and start - previous_end > self.DENSE_RUN_MAX_GAP_SECONDS
            ):
                runs.append(current_run)
                current_run = []
            current_run.append(index)
            previous_end = end
        if current_run:
            runs.append(current_run)

        adjusted_runs = 0
        adjusted_cues = 0
        max_ratio = 1.0
        for run_number, indices in enumerate(runs):
            first = segment_list[indices[0]]
            last = segment_list[indices[-1]]
            run_start = float(first.get("start", 0.0) or 0.0)
            run_end = float(last.get("end", run_start) or run_start)
            available = max(
                0.05,
                (run_end - run_start)
                - self.VOICE_COLLISION_GUARD_SECONDS * max(0, len(indices) - 1),
            )
            speech_duration = sum(
                self._probe_wav_duration_seconds(fitted_wavs[index]) for index in indices
            )
            required_ratio = speech_duration / available if available > 0.0 else 1.0
            run_ratio = min(adaptive_cap, max(1.0, required_ratio))
            if run_ratio < 1.03:
                continue

            adjusted_runs += 1
            max_ratio = max(max_ratio, run_ratio)
            for index in indices:
                source_path = fitted_wavs[index]
                adjusted_path = os.path.join(
                    tmp_dir,
                    f"seg_{index:04d}_dense_en_{run_number:04d}.wav",
                )
                fitted_wavs[index] = self.engine_runtime.change_wav_speed(
                    input_wav_path=source_path,
                    output_wav_path=adjusted_path,
                    speed_ratio=run_ratio,
                )
                seg = segment_list[index]
                target_duration = max(
                    0.0,
                    float(seg.get("end", 0.0) or 0.0) - float(seg.get("start", 0.0) or 0.0),
                )
                fitted_duration = self._probe_wav_duration_seconds(fitted_wavs[index])
                seg["tts_duration"] = round(fitted_duration, 3)
                seg["ratio"] = round(
                    fitted_duration / target_duration if target_duration > 0.0 else 0.0,
                    3,
                )
                metrics = dict(seg.get("_tts_metrics") or {})
                metrics["dense_run_speed_ratio"] = round(run_ratio, 3)
                metrics["tts_duration"] = seg["tts_duration"]
                metrics["ratio"] = seg["ratio"]
                action = str(seg.get("action_taken") or metrics.get("action_taken") or "accept")
                if "dense_run_fit" not in action:
                    action = f"{action}+dense_run_fit"
                seg["action_taken"] = action
                metrics["action_taken"] = action
                seg["_tts_metrics"] = metrics
                adjusted_cues += 1

        if adjusted_runs:
            print(
                "[Voice Timing] Dense English fit: "
                f"runs={adjusted_runs}, cues={adjusted_cues}, max_speed={max_ratio:.3f}x"
            )
        return fitted_wavs

    def _enforce_non_overlapping_voice_windows(self, *, segments, wavs, tmp_dir: str):
        """Schedule dense voice cues without overlapping or cutting speech.

        The old collision guard hard-trimmed a long WAV at the next subtitle's
        start time.  That made the following cue punctual by literally losing
        the end of the current sentence.  Earlier timing passes already perform
        the bounded, natural-sounding speed changes; this final pass therefore
        serializes any remaining overrun and records the real audio window.
        ``build_voice_track_from_srt_segments`` consumes ``_audio_start`` as a
        second line of defence for imported/manual subtitles.
        """
        segment_list = list(segments or [])
        guarded_wavs = list(wavs or [])
        queued_count = 0
        previous_audio_end = 0.0
        for index in range(min(len(segment_list), len(guarded_wavs))):
            seg = segment_list[index]
            wav_path = guarded_wavs[index]
            if not wav_path or not os.path.exists(wav_path):
                continue
            try:
                requested_start = float(seg.get("start", 0.0) or 0.0)
            except (AttributeError, TypeError, ValueError):
                continue
            actual = self._probe_wav_duration_seconds(wav_path)
            if actual <= 0.0:
                continue

            scheduled_start = requested_start
            if previous_audio_end > 0.0:
                scheduled_start = max(
                    scheduled_start,
                    previous_audio_end + self.VOICE_COLLISION_GUARD_SECONDS,
                )
            audio_end = scheduled_start + actual
            seg["_audio_start"] = scheduled_start
            seg["_audio_end"] = audio_end
            metrics = dict(seg.get("_tts_metrics") or {})
            metrics["scheduled_audio_start"] = round(scheduled_start, 3)
            metrics["scheduled_audio_end"] = round(audio_end, 3)
            delay = max(0.0, scheduled_start - requested_start)
            if delay > 0.01:
                queued_count += 1
                action = str(seg.get("action_taken") or "accept")
                if "voice_queue" not in action:
                    seg["action_taken"] = f"{action}+voice_queue"
                metrics["voice_queue_delay"] = round(delay, 3)
                metrics["action_taken"] = seg["action_taken"]
            seg["_tts_metrics"] = metrics
            previous_audio_end = audio_end

        if queued_count:
            print(
                "[Voice Timing] Serialized "
                f"{queued_count} dense voice cue(s) without cutting speech."
            )
        return guarded_wavs

    def _extend_segment_ends_to_audio(self, *, segments, wavs, sync_mode: str = "off") -> None:
        """Synchronize subtitle windows with measured TTS duration.

        Subtitle timing remains the source/timeline truth.  Voice placement is
        kept separately in ``_audio_start``/``_audio_end`` so a long TTS clip
        cannot rewrite the SRT and shift every later cue.  The renderer/mixer
        can use the audio metadata without corrupting the visual subtitle lane.
        """
        segment_list = list(segments or [])
        for index, (seg, wav_path) in enumerate(zip(segment_list, wavs or [])):
            if not wav_path or not os.path.exists(wav_path):
                continue
            actual_d = self._probe_wav_duration_seconds(wav_path)
            if actual_d <= 0:
                continue
            try:
                start_s = float(seg.get("start", 0.0))
            except (TypeError, ValueError):
                continue
            audio_start = seg.get("_audio_start", start_s)
            try:
                audio_start = float(audio_start)
            except (TypeError, ValueError):
                audio_start = start_s
            try:
                audio_end = float(seg.get("_audio_end", audio_start + actual_d))
            except (TypeError, ValueError):
                audio_end = audio_start + actual_d
            seg["_audio_start"] = audio_start
            seg["_audio_end"] = audio_end
            if audio_start > start_s + 0.01:
                metrics = dict(seg.get("_tts_metrics") or {})
                metrics["voice_queue_delay"] = round(audio_start - start_s, 3)
                seg["_tts_metrics"] = metrics

    def _synthesize_segment_wavs(
        self,
        *,
        segments,
        tmp_dir: str,
        voice_name: str,
        provider_speed: float = 1.0,
        voice_provider: str = '',
        on_progress: callable = None,
        cancellation_check: callable = None,
        index_offset: int = 0,
        log: bool = True,
    ):
        segments = list(segments or [])
        manifest = self._load_manifest(tmp_dir)
        manifest_segments = dict(manifest.get("segments", {}) or {})
        manifest_by_cache_key = dict(manifest.get("by_cache_key", {}) or {})
        wavs = [""] * len(segments)
        pending_jobs = []
        cache_hits = 0

        for idx, seg in enumerate(segments):
            global_idx = int(index_offset) + idx
            txt = self._segment_tts_text(seg)
            if not txt:
                wavs[idx] = ""
                continue
            segment_voice_name = str(seg.get("voice_name") or voice_name).strip() or voice_name
            seg_wav = os.path.join(tmp_dir, f"seg_{global_idx:04d}_base.wav")
            cache_key = self._segment_cache_key(text=txt, voice_name=segment_voice_name, provider_speed=provider_speed)
            cache_entry = manifest_segments.get(str(global_idx), {})
            cached_wav = str(cache_entry.get("wav_path", "")).strip()
            cached_key = str(cache_entry.get("cache_key", "")).strip()
            if not (cached_key == cache_key and cached_wav and os.path.exists(cached_wav)):
                cache_entry = dict(manifest_by_cache_key.get(cache_key, {}) or {})
                cached_wav = str(cache_entry.get("wav_path", "")).strip()
                cached_key = str(cache_entry.get("cache_key", "")).strip()
            if cached_key == cache_key and cached_wav and os.path.exists(cached_wav):
                wavs[idx] = cached_wav
                manifest_segments[str(global_idx)] = {
                    "cache_key": cache_key,
                    "wav_path": cached_wav,
                    "text": txt,
                    "voice_name": segment_voice_name,
                    "provider_speed": provider_speed,
                }
                manifest_by_cache_key[cache_key] = dict(manifest_segments[str(global_idx)])
                cache_hits += 1
                continue
            pending_jobs.append(
                {
                    "idx": idx,
                    "global_idx": global_idx,
                    "text": txt,
                    "wav_path": seg_wav,
                    "cache_key": cache_key,
                    "voice_name": segment_voice_name,
                }
            )

        if pending_jobs:
            pending_providers = {self._voice_provider(str(job["voice_name"])) for job in pending_jobs}
            if pending_providers == {"piper"}:
                configured_workers = int(os.getenv("VIUSTUDIO_PIPER_TTS_WORKERS", self.PIPER_TTS_WORKERS) or self.PIPER_TTS_WORKERS)
                cpu_count = os.cpu_count() or 4
                if len(pending_jobs) >= 500:
                    long_project_workers = min(configured_workers, max(8, cpu_count - 2))
                elif len(pending_jobs) >= 120:
                    long_project_workers = min(configured_workers, 8)
                elif len(pending_jobs) >= 40:
                    long_project_workers = min(configured_workers, 6)
                else:
                    long_project_workers = min(configured_workers, 4)
                cpu_limit = max(1, cpu_count)
                worker_count = max(1, min(long_project_workers, len(pending_jobs), cpu_limit))
                # Pre-load the Piper model in the main thread so all workers share
                # the cached model object without racing on first-load I/O.
                try:
                    first_voice = pending_jobs[0]["voice_name"]
                    from tts_processor import preload_tts_voice
                    if on_progress:
                        on_progress(f"Loading Piper voice model ({first_voice})...")
                    preload_tts_voice(first_voice, on_progress=None)
                except Exception:
                    pass
            elif pending_providers == {"edge"}:
                worker_count = 1
            else:
                worker_count = max(1, min(self.MAX_TTS_WORKERS, len(pending_jobs)))
            if log:
                print(
                    "[Voice Workflow] TTS synth jobs: "
                    f"pending={len(pending_jobs)}, cache_hits={cache_hits}, workers={worker_count}, native_speed={provider_speed:.2f}"
                )
            if on_progress:
                total_count = max(1, len(segments))
                initial_percent = int(cache_hits * 75 / total_count)
                msg = (
                    f"TTS {cache_hits}/{total_count} ({initial_percent}%) • "
                    f"Generating {len(pending_jobs)} cues with {worker_count} worker(s)"
                )
                try:
                    from app.core.models.progress import ProgressEvent
                    on_progress(ProgressEvent(
                        workflow="tts",
                        stage="voiceover",
                        substage="cue_tts",
                        current=float(cache_hits),
                        total=float(total_count),
                        percent=initial_percent,
                        message=msg,
                    ))
                except Exception:
                    on_progress(msg)
            if not pending_jobs:
                manifest["segments"] = manifest_segments
                manifest["by_cache_key"] = manifest_by_cache_key
                self._save_manifest(tmp_dir, manifest)
                return wavs
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                future_map = {
                    executor.submit(
                        self.engine_runtime.synthesize_segment,
                        text=job["text"],
                        wav_path=job["wav_path"],
                        voice=job["voice_name"],
                        speed=provider_speed,
                        tmp_dir=tmp_dir,
                        on_progress=on_progress,
                    ): job
                    for job in pending_jobs
                }
                completed_count = 0
                for future in as_completed(future_map):
                    if cancellation_check and cancellation_check():
                        for f in future_map:
                            f.cancel()
                        manifest["segments"] = manifest_segments
                        manifest["by_cache_key"] = manifest_by_cache_key
                        self._save_manifest(tmp_dir, manifest)
                        raise InterruptedError("TTS synthesis cancelled by user")
                    job = future_map[future]
                    idx = int(job["idx"])
                    txt = str(job["text"])
                    seg_wav = str(job["wav_path"])
                    try:
                        future.result()
                    except Exception as exc:
                        preview = " ".join(txt.split())
                        if len(preview) > 120:
                            preview = preview[:117] + "..."
                        if on_progress:
                            on_progress(f"[TTS Warning] Segment {idx + 1} failed, using silence placeholder.")
                        target_duration = max(
                            0.2,
                            float(segments[idx].get("end", 0.0)) - float(segments[idx].get("start", 0.0)),
                        )
                        self._write_silence_wav(seg_wav, target_duration)
                        print(
                            f"[Voice Workflow] TTS failed at subtitle segment {idx + 1}: "
                            f"\"{preview}\". Using silence placeholder. Error: {exc}"
                        )
                    manifest_segments[str(job["global_idx"])] = {
                        "cache_key": str(job["cache_key"]),
                        "wav_path": seg_wav,
                        "text": txt,
                        "voice_name": job["voice_name"],
                        "provider_speed": provider_speed,
                    }
                    manifest_by_cache_key[str(job["cache_key"])] = dict(manifest_segments[str(job["global_idx"])])
                    wavs[idx] = seg_wav
                    completed_count += 1
                    if on_progress:
                        done_count = min(len(segments), cache_hits + completed_count)
                        percent = int(done_count * 75 / max(1, len(segments)))
                        msg = (
                            f"TTS {done_count}/{len(segments)} ({percent}%) • "
                            f"Finished cue {int(job['global_idx']) + 1}"
                        )
                        try:
                            from app.core.models.progress import ProgressEvent
                            on_progress(ProgressEvent(
                                workflow="tts",
                                stage="voiceover",
                                substage="cue_tts",
                                current=float(done_count),
                                total=float(len(segments)),
                                percent=percent,
                                message=msg,
                            ))
                        except Exception:
                            on_progress(msg)
        elif log:
            print(f"[Voice Workflow] TTS synth jobs: pending=0, cache_hits={cache_hits}, workers=0, native_speed={provider_speed:.2f}")

        manifest["segments"] = manifest_segments
        manifest["by_cache_key"] = manifest_by_cache_key
        self._save_manifest(tmp_dir, manifest)
        return wavs

    def prime_tts_cache(
        self,
        *,
        segments,
        tmp_dir: str,
        voice_name: str,
        voice_speed: float = 1.0,
        index_offset: int = 0,
        on_progress: callable = None,
        cancellation_check: callable = None,
        quiet: bool = False,
    ) -> list[str]:
        os.makedirs(tmp_dir, exist_ok=True)
        safe_voice_speed = self._clamp_requested_speed(float(voice_speed))
        voice_provider = self._voice_provider(voice_name)
        prepared_segments = self._prepare_segments_for_tts(
            segments,
            voice_provider=voice_provider,
            ai_rewrite_dubbing=False,
            source_language="auto",
            style_instruction="",
            log=not quiet,
        )
        if not quiet:
            print(
                "[Voice Workflow] Priming TTS cache: "
                f"segments={len(prepared_segments)}, voice={voice_name}, provider={voice_provider}, "
                f"index_offset={int(index_offset)}"
            )
        provider_speed = self._provider_native_speed(
            provider=voice_provider,
            requested_speed=safe_voice_speed,
        )
        return self._synthesize_segment_wavs(
            segments=prepared_segments,
            tmp_dir=tmp_dir,
            voice_name=voice_name,
            provider_speed=provider_speed,
            voice_provider=voice_provider,
            on_progress=on_progress,
            cancellation_check=cancellation_check,
            index_offset=index_offset,
            log=not quiet,
        )

    def run(
        self,
        *,
        segments,
        output_dir: str,
        background_path: str = "",
        audio_handling_mode: str = "fast",
        voice_name: str = "ngochuyen",
        voice_speed: float = 1.0,
        timing_sync_mode: str = "off",
        original_volume: int = 50,
        dub_volume: int = 100,
        project_state_path: str = "",
        project_temp_dir: str = "",
        ai_rewrite_dubbing: bool = False,
        dubbing_style_instruction: str = "",
        source_language: str = "auto",
        on_progress: callable = None,
        cancellation_check: callable = None,
    ):
        if cancellation_check and cancellation_check():
            raise InterruptedError("Voice workflow cancelled by user")
        workflow_started = time.perf_counter()
        state = self._load_state(project_state_path)
        self._mark_started(state, with_background=bool(background_path))
        try:
            import tts_processor
            tts_processor._VIETNAMESE_NORMALIZER = None
            tts_processor._VIETNAMESE_NORMALIZER_DATA_DIR = ""
        except Exception:
            pass
        audio_mode_key = str(audio_handling_mode or "fast").strip().lower()
        print(f"[Voice Workflow] Audio handling mode: {audio_mode_key}")
        os.makedirs(output_dir, exist_ok=True)
        tmp_dir = str(project_temp_dir or "").strip() or os.path.join(output_dir, "_tts_tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        safe_voice_speed = self._clamp_requested_speed(float(voice_speed))
        voice_provider = self._voice_provider(voice_name)
        segments = self._prepare_segments_for_tts(
            segments,
            voice_provider=voice_provider,
            ai_rewrite_dubbing=bool(ai_rewrite_dubbing),
            source_language=source_language,
            style_instruction=dubbing_style_instruction,
        )
        provider_speed = self._provider_native_speed(
            provider=voice_provider,
            requested_speed=safe_voice_speed,
        )
        residual_speed = (
            safe_voice_speed / provider_speed
            if provider_speed > 0.0
            else safe_voice_speed
        )

        synth_started = time.perf_counter()
        wavs = self._synthesize_segment_wavs(
            segments=segments,
            tmp_dir=tmp_dir,
            voice_name=voice_name,
            provider_speed=provider_speed,
            voice_provider=voice_provider,
            on_progress=on_progress,
            cancellation_check=cancellation_check,
        )
        if cancellation_check and cancellation_check():
            raise InterruptedError("Voice workflow cancelled by user")

        if on_progress:
            try:
                from app.core.models.progress import ProgressEvent
                on_progress(ProgressEvent(
                    workflow="tts",
                    stage="voiceover",
                    substage="timing_align",
                    current=78.0,
                    total=100.0,
                    percent=78,
                    message="Aligning voice duration with subtitles (Smart Fit)...",
                ))
            except Exception:
                on_progress("Aligning voice duration with subtitles (Smart Fit)...")

        self._update_manifest_entries(
            tmp_dir=tmp_dir,
            segments=segments,
            wavs=wavs,
            voice_name=voice_name,
            provider_speed=provider_speed,
        )
        self._save_pre_speed_ratios(segments=segments, wavs=wavs)
        wavs = self._apply_safe_timing_polish(
            segments=segments,
            wavs=wavs,
            tmp_dir=tmp_dir,
            voice_speed=residual_speed,
            sync_mode=timing_sync_mode,
        )
        self._log_segment_fit_metrics(segments=segments, wavs=wavs)

        if cancellation_check and cancellation_check():
            raise InterruptedError("Voice workflow cancelled by user")

        if on_progress:
            try:
                from app.core.models.progress import ProgressEvent
                on_progress(ProgressEvent(
                    workflow="tts",
                    stage="voiceover",
                    substage="window_enforce",
                    current=85.0,
                    total=100.0,
                    percent=85,
                    message="Resolving voice boundary collisions...",
                ))
            except Exception:
                on_progress("Resolving voice boundary collisions...")

        segments, wavs = self._apply_deficit_timing_polish(
            segments=segments,
            wavs=wavs,
            tmp_dir=tmp_dir,
            sync_mode=timing_sync_mode,
        )
        wavs = self._fit_dense_english_voice_runs(
            segments=segments,
            wavs=wavs,
            tmp_dir=tmp_dir,
            sync_mode=timing_sync_mode,
            voice_name=voice_name,
            requested_speed=safe_voice_speed,
        )
        wavs = self._enforce_non_overlapping_voice_windows(
            segments=segments,
            wavs=wavs,
            tmp_dir=tmp_dir,
        )
        self._extend_segment_ends_to_audio(
            segments=segments,
            wavs=wavs,
            sync_mode=timing_sync_mode,
        )

        synth_elapsed = time.perf_counter() - synth_started
        print(
            "[Voice Workflow] Speed plan: "
            f"requested={safe_voice_speed:.2f}, native={provider_speed:.2f}, residual={residual_speed:.2f}"
        )

        if cancellation_check and cancellation_check():
            raise InterruptedError("Voice workflow cancelled by user")

        if on_progress:
            try:
                from app.core.models.progress import ProgressEvent
                on_progress(ProgressEvent(
                    workflow="tts",
                    stage="voiceover",
                    substage="track_assembly",
                    current=92.0,
                    total=100.0,
                    percent=92,
                    message="Assembling final voice track (voice_vi.wav)...",
                ))
            except Exception:
                on_progress("Assembling final voice track (voice_vi.wav)...")

        voice_track = os.path.join(tmp_dir, "voice_vi.wav")
        build_started = time.perf_counter()
        self.engine_runtime.build_voice_track(
            segments=segments,
            tts_wav_paths=wavs,
            output_wav_path=voice_track,
            gain_db=0.0,
        )
        build_elapsed = time.perf_counter() - build_started

        if cancellation_check and cancellation_check():
            raise InterruptedError("Voice workflow cancelled by user")

        # Skip mixed audio creation - will be generated at export time with current volumes
        mixed = ""
        mix_elapsed = 0.0
        print(f"[Voice Workflow] Voice track created at {voice_track}. Mixed audio will be generated at export time.")

        self._mark_completed(
            state,
            voice_track=voice_track,
            mixed_path=mixed,
            background_path=background_path,
            segments=segments,
        )
        workflow_elapsed = time.perf_counter() - workflow_started
        print(
            "[Timing] Voice workflow: "
            f"synthesize={synth_elapsed:.2f}s, "
            f"build_track={build_elapsed:.2f}s, "
            f"mix={mix_elapsed:.2f}s, "
            f"total={workflow_elapsed:.2f}s"
        )

        if on_progress:
            try:
                from app.core.models.progress import ProgressEvent
                on_progress(ProgressEvent(
                    workflow="tts",
                    stage="voiceover",
                    substage="complete",
                    current=100.0,
                    total=100.0,
                    percent=100,
                    message="Voice generation completed successfully",
                ))
            except Exception:
                on_progress("Voice generation completed successfully")

        return {
            "voice_track": voice_track,
            "mixed_path": mixed,
            "segments": segments,
        }

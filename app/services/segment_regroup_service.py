from __future__ import annotations

import os
import re
import math
import time
import logging
from math import ceil
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class SegmentRegroupService:
    VERSION = "segment-regroup-v4"

    def regroup(self, segments: list[dict], *, max_gap_seconds: float = 0.35, max_duration_seconds: float = 8.0) -> list[dict]:
        # Step 1: Deduplicate & stitch boundary overlapping segments on the whole cues first
        deduped = self.deduplicate_and_clamp_timeline(segments)

        # Step 2: Split oversized segments (> 8.0s) on clean, unified sentences
        regrouped: list[dict] = []
        for segment in deduped or []:
            text = str(segment.get("text", "") or "").strip()
            if not text:
                continue
            regrouped.extend(
                self._split_oversized_segment(
                    segment,
                    max_duration_seconds=max_duration_seconds,
                )
            )

        normalized = []
        for index, segment in enumerate(regrouped, start=1):
            payload = self._clone_segment(segment)
            payload["id"] = index
            payload["text"] = self._normalize_sentence_text(payload.get("text", ""))
            normalized.append(payload)
        return self.expand_short_cues_into_gaps(normalized)

    @classmethod
    def compute_natural_cue_duration(cls, text: str) -> float:
        """Compute the natural minimum duration (seconds) needed for comfortable
        speech articulation and human reading of a subtitle cue.
        """
        raw = str(text or "").strip()
        if not raw:
            return 0.8
        cjk_chars = len(re.findall(r"[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]", raw))
        total_chars = len(re.findall(r"\w", raw))
        if cjk_chars >= 2 and total_chars > 0 and (cjk_chars / total_chars) > 0.4:
            # CJK: roughly 0.22s per character + 0.30s base onset/offset padding
            return max(0.8, cjk_chars * 0.22 + 0.30)
        else:
            # Non-CJK (Vietnamese, English, etc.):
            words = [w for w in re.split(r"\s+", raw) if w]
            word_count = len(words)
            return max(0.8, word_count * 0.28 + 0.20)

    SAFE_GAP = 0.08
    MAX_PER_NUDGE = 0.15
    MAX_CUMULATIVE_DRIFT = 0.20
    MAX_LEADING = 0.20
    TARGET_MAX_SPEED = 1.15
    HARD_MAX_SPEED = 1.20

    @classmethod
    def is_semantic_shortening_safe(cls, original: str, candidate: str) -> bool:
        """Ensure shortened candidate preserves essential semantics:
        - Negation must never be dropped (e.g. 'không', 'chưa', 'đừng', 'chẳng').
        - Digits / numbers must be preserved.
        """
        orig = str(original or "").lower()
        cand = str(candidate or "").lower()
        if not cand:
            return False

        # 1. Negation preservation
        negation_words = {"không", "chưa", "chẳng", "đừng", "chớ", "chả"}
        orig_has_neg = any(re.search(rf"\b{neg}\b", orig) for neg in negation_words)
        cand_has_neg = any(re.search(rf"\b{neg}\b", cand) for neg in negation_words)
        if orig_has_neg and not cand_has_neg:
            return False

        # 2. Number digits preservation
        orig_digits = re.findall(r"\d+", orig)
        cand_digits = re.findall(r"\d+", cand)
        for digit in orig_digits:
            if digit not in cand_digits:
                return False

        # 3. Language consistency (if original is Vietnamese with diacritics, candidate must also be Vietnamese)
        vn_diacritics = r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]"
        if re.search(vn_diacritics, orig) and not re.search(vn_diacritics, cand):
            return False

        return True

    @classmethod
    def generate_shorten_candidates(cls, text: str) -> list[str]:
        """Generate candidate phrases for TTS while STRICTLY PRESERVING FULL MEANING.
        NEVER truncate or drop essential words:
        Level 0: original full text
        Level 1: natural conversational contractions / idiom equivalences (e.g. 'Anh hào phóng thật đấy' -> 'Hào phóng ghê')
        """
        raw = " ".join(str(text or "").replace("\n", " ").split()).strip()
        if not raw:
            return []

        candidates = [raw]

        # Level 1: Conversational / spoken idioms (complete, natural expressions only)
        replacements = [
            (r"\bAnh\s+hào\s+phóng\s+thật\s+đấy\b", "Hào phóng ghê"),
            (r"\bCô\s+hào\s+phóng\s+thật\s+đấy\b", "Hào phóng ghê"),
            (r"\bBạn\s+hào\s+phóng\s+thật\s+đấy\b", "Hào phóng ghê"),
            (r"\bthật\s+đấy\b", "thật"),
            (r"\bquá\s+đi\s+mất\b", "quá"),
            (r"\bvô\s+cùng\b", "rất"),
            (r"\bchắc\s+chắn\s+là\b", "chắc chắn"),
            (r"\bthực\s+sự\s+là\b", ""),
            (r"\bcó\s+thể\s+nói\s+là\b", ""),
            (r"\bkiểu\s+như\s+là\b", ""),
            (r"\bkiểu\s+như\b", ""),
            (r"\bmột\s+cách\b", ""),
            (r"\bvề\s+cơ\s+bản\b", ""),
            (r"\bnói\s+chung\s+là\b", ""),
        ]
        cand1 = raw
        for pat, rep in replacements:
            cand1 = re.sub(pat, rep, cand1, flags=re.IGNORECASE)
        cand1 = " ".join(cand1.split()).strip(" ,.;:!?")
        if cand1 and cand1 != raw and cls.is_semantic_shortening_safe(raw, cand1):
            if not cand1.endswith((".", "!", "?")):
                cand1 += "."
            if cand1 not in candidates:
                candidates.append(cand1)

        return candidates

    @classmethod
    def estimate_tts_duration(cls, text: str) -> float:
        """Estimate natural speech duration of text (in seconds) based on
        empirical syllable articulation time + prosody pause overhead.
        """
        raw = str(text or "").strip()
        if not raw:
            return 0.0
        cjk_chars = len(re.findall(r"[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]", raw))
        total_chars = len(re.findall(r"\w", raw))
        if cjk_chars >= 2 and total_chars > 0 and (cjk_chars / total_chars) > 0.4:
            return max(0.60, cjk_chars * 0.22 + 0.20)
        words = [w for w in re.split(r"\s+", raw) if w]
        if not words:
            return 0.0
        return max(0.55, len(words) * 0.25 + 0.15)

    @classmethod
    def estimate_tts_speed(cls, text: str, available_duration: float) -> float:
        if available_duration <= 0.001:
            return 999.0
        dur = cls.estimate_tts_duration(text)
        return round(dur / available_duration, 3)

    _AI_SHORTEN_CACHE: dict[tuple[str, float, str], str] = {}
    _QUOTA_EXHAUSTED_UNTIL: float = 0.0

    @classmethod
    def shorten_text_for_tts(
        cls,
        text: str,
        available_duration: float,
        *,
        max_words: int | None = None,
        context_prev: str = "",
    ) -> str:
        candidates = cls.generate_shorten_candidates(text)
        if not candidates:
            return text
        # Select the candidate that best fits available_duration * TARGET_MAX_SPEED
        target_dur = max(0.1, available_duration)
        for cand in candidates:
            if cls.estimate_tts_speed(cand, target_dur) <= cls.TARGET_MAX_SPEED:
                return cand
        for cand in candidates:
            if cls.estimate_tts_speed(cand, target_dur) <= cls.HARD_MAX_SPEED:
                return cand
        # When rule-based candidates don't fit <= HARD_MAX_SPEED, attempt AI shortening
        ai_cand = cls.ai_shorten_text_for_tts(text, target_dur, context_prev=context_prev)
        if ai_cand and ai_cand != text:
            return ai_cand
        # When even AI doesn't shorten, return the best complete candidate.
        # NEVER return a truncated sentence fragment!
        return candidates[1] if len(candidates) > 1 else candidates[0]

    @classmethod
    def ai_shorten_text_for_tts(
        cls,
        text: str,
        available_duration: float,
        *,
        context_prev: str = "",
        timeout: int = 4,
    ) -> str:
        """Ask the configured AI (Gemini / OpenAI-compatible) to rephrase *text* so
        it fits within *available_duration* seconds when read aloud, while strictly
        preserving its meaning, context, and emotional tone.

        Provider resolution order (first one that is fully configured wins):
          1. GOOGLE_AI_STUDIO  – Google AI Studio / Gemini (from Translation Engine settings)
          2. DEEPSEEK          – DeepSeek
          3. OPENAI            – OpenAI
          4. CUSTOM_AI         – custom / self-hosted OpenAI-compatible endpoint

        Returns the AI-shortened text on success, or *text* unchanged when:
          - Quota/rate-limit circuit breaker is active.
          - No provider is configured (api_key / model / base_url missing).
          - The API call fails for any reason (network, quota, etc.).
          - The AI response is empty or longer than the original.
        """
        raw = " ".join(str(text or "").split()).strip()
        if not raw:
            return raw

        if time.time() < cls._QUOTA_EXHAUSTED_UNTIL:
            # Circuit breaker is active after hitting quota (HTTP 429)
            return raw

        cache_key = (raw, round(available_duration, 1), str(context_prev or "").strip())
        if cache_key in cls._AI_SHORTEN_CACHE:
            return cls._AI_SHORTEN_CACHE[cache_key]

        # Ensure .env is loaded if os.environ doesn't have the key yet
        if not os.getenv("GOOGLE_AI_STUDIO_API_KEY"):
            try:
                from dotenv import load_dotenv
                workspace_env = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    ".env",
                )
                if os.path.exists(workspace_env):
                    load_dotenv(workspace_env)
            except Exception:
                pass

        # Resolve provider – check env vars in priority order
        providers_to_try = [
            (
                "GOOGLE_AI_STUDIO",
                os.getenv("GOOGLE_AI_STUDIO_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/").strip(),
                (os.getenv("GOOGLE_AI_STUDIO_MODEL") or os.getenv("GOOGLE_AI_STUDIO_POLISH_MODEL") or "gemini-3.6-flash").strip(),
                [
                    os.getenv("GOOGLE_AI_STUDIO_API_KEY", "").strip(),
                    os.getenv("GEMINI_API_KEY", "").strip(),
                    os.getenv("GOOGLE_API_KEY", "").strip(),
                ],
            ),
            (
                "DEEPSEEK",
                os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").strip(),
                os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip(),
                [os.getenv("DEEPSEEK_API_KEY", "").strip()],
            ),
            (
                "OPENAI",
                os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1/").strip(),
                os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip(),
                [os.getenv("OPENAI_API_KEY", "").strip()],
            ),
            (
                "CUSTOM_AI",
                os.getenv("CUSTOM_AI_BASE_URL", "").strip(),
                os.getenv("CUSTOM_AI_MODEL", "").strip(),
                [os.getenv("CUSTOM_AI_API_KEY", "").strip()],
            ),
        ]

        api_key = model_name = base_url = ""
        for name, default_base, default_model, key_candidates in providers_to_try:
            valid_key = next((k for k in key_candidates if k), "")
            if valid_key and default_model and default_base:
                api_key, model_name, base_url = valid_key, default_model, default_base
                break

        if not (api_key and model_name and base_url):
            logger.debug("ai_shorten_text_for_tts: no AI provider configured, skipping")
            return raw

        # Build prompt: strictly preserve meaning, context, and nuance
        target_words = max(1, int(available_duration * cls.HARD_MAX_SPEED / 0.25))
        prompt_lines = [
            "Bạn là chuyên gia biên tập phụ đề và lồng tiếng.",
            f"Nhiệm vụ: Rút gọn câu thoại tiếng Việt sau để người đọc TTS đọc tự nhiên trong khoảng {available_duration:.1f} giây (tối đa khoảng {target_words} từ).",
            "Yêu cầu bắt buộc:",
            "1. Ngôn ngữ câu trả lời: BẮT BUỘC là TIẾNG VIỆT. Tuyệt đối không dịch sang tiếng Anh hay ngôn ngữ khác.",
            "2. Giữ NGUYÊN nghĩa gốc, ngữ cảnh và sắc thái cảm xúc (hài hước, giận dữ, trang trọng, v.v.).",
            "3. Tuyệt đối KHÔNG làm mất ý phủ định (không, chưa, chẳng, đừng...), KHÔNG làm mất các con số / dữ kiện quan trọng.",
            "4. Câu rút gọn phải là câu hoàn chỉnh ngữ pháp, tự nhiên trong khẩu ngữ, TUYỆT ĐỐI KHÔNG được cắt cụt câu hay bỏ lửng.",
            "5. Chỉ trả về DUY NHẤT câu đã rút gọn bằng tiếng Việt, không thêm bất kỳ lời giải thích, ghi chú hay tiền tố nào.",
        ]
        if context_prev and str(context_prev).strip():
            prompt_lines.append(f"Ngữ cảnh câu trước: {str(context_prev).strip()}")
        prompt_lines.append(f"Câu gốc: {raw}")
        prompt = "\n".join(prompt_lines)

        try:
            from openai import OpenAI  # noqa: PLC0415 – lazy import
            client = OpenAI(api_key=api_key, base_url=base_url)
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=256,
                timeout=timeout,
            )
            shortened = str(response.choices[0].message.content or "").strip()
            # Strip any scaffolding / prefixes the model might echo (e.g. Meaning:, Output:, etc.)
            shortened = re.sub(
                r"^(?:(?:[Cc]âu\s+)?(?:[Rr]út\s+gọn|[Nn]gắn\s+gọn)|[Mm]eaning|[Tt]ranslation|[Tt]arget|[Vv]ietnamese|[Tt]iếng\s+[Vv]iệt|[Oo]utput|[Rr]esult)\s*:\s*",
                "",
                shortened,
            ).strip()
            shortened = shortened.strip("\"'""''`")
            shortened = " ".join(shortened.split()).strip()
            if not shortened:
                logger.warning("ai_shorten_text_for_tts: empty response, using original")
                return raw
            # Safety: reject if AI returned something longer (hallucination / added padding)
            if len(shortened.split()) > len(raw.split()):
                logger.warning(
                    "ai_shorten_text_for_tts: AI response longer than original (%d > %d words), discarding",
                    len(shortened.split()), len(raw.split()),
                )
                return raw
            # Safety: must preserve negation & digits
            if not cls.is_semantic_shortening_safe(raw, shortened):
                logger.warning(
                    "ai_shorten_text_for_tts: semantic check failed for %r → %r, using original",
                    raw[:60], shortened[:60],
                )
                return raw
            logger.info(
                "ai_shorten_text_for_tts: successfully shortened %r → %r (%.2fs budget)",
                raw[:60], shortened[:60], available_duration,
            )
            cls._AI_SHORTEN_CACHE[cache_key] = shortened
            return shortened
        except Exception as exc:
            text_err = str(exc or "").lower()
            if any(m in text_err for m in ("quota", "resource_exhausted", "rate limit", "ratelimit", "429")):
                cls._QUOTA_EXHAUSTED_UNTIL = time.time() + 1800  # 30-minute circuit breaker
                logger.warning(
                    "ai_shorten_text_for_tts: AI provider quota exceeded (HTTP 429). "
                    "Temporarily disabled AI shortening for 30 minutes to prevent app freezing."
                )
            else:
                logger.warning("ai_shorten_text_for_tts: API call failed (%s), using original", exc)
            return raw

    @classmethod
    def expand_short_cues_into_gaps(
        cls,
        segments: list[dict],
        *,
        min_cue_duration: float = 0.8,
        safe_gap_seconds: float = 0.08,
        max_timeline_duration: float | None = None,
        video_duration: float | None = None,
        enable_ai: bool = False,
    ) -> list[dict]:
        """Extend artificially short cues into silence gaps with strict synchrony constraints:
        1. Subtitle timeline (sub_start, sub_end, start, end) is strictly IMMUTABLE to preserve video sync.
        2. TTS window (voice_start, voice_end) is expanded into silence without cumulative ripple drift.
        3. Trailing expansion bounded by next_sub_start - safe_gap.
        4. Ripple nudge capped at MAX_PER_NUDGE (0.15s) and MAX_CUMULATIVE_DRIFT (0.20s).
        5. Leading expansion computed via available_leading = voice_start - prev_sub_end - safe_gap.
        6. Multi-level candidate shortening tested against required speed <= 1.15 (natural) or <= 1.20 (acceptable).
        7. If even shortest candidate requires speed > 1.20, marked as timing_conflict = True without truncating.
        """
        if not segments:
            return []

        ordered = sorted(
            [dict(s) for s in segments if isinstance(s, dict)],
            key=lambda s: (float(s.get("sub_start", s.get("start", 0.0)) or 0.0), float(s.get("sub_end", s.get("end", 0.0)) or 0.0)),
        )

        for i, cue in enumerate(ordered):
            orig_start = float(cue.get("sub_start", cue.get("start", 0.0)) or 0.0)
            orig_end = float(cue.get("sub_end", cue.get("end", orig_start)) or orig_start)
            # Invariant 1: Subtitle timeline is IMMUTABLE
            cue["sub_start"] = orig_start
            cue["sub_end"] = orig_end
            cue["start"] = orig_start
            cue["end"] = orig_end

            # TTS window
            voice_start = float(cue.get("voice_start", orig_start))
            voice_end = float(cue.get("voice_end", orig_end))
            voice_dur = max(0.0, voice_end - voice_start)

            # Target speech text
            candidate_texts = [
                cue.get("dubbing_vi", ""),
                cue.get("tts_text", ""),
                cue.get("final_text", ""),
                cue.get("raw_translation", ""),
                cue.get("text", ""),
                cue.get("original_text", ""),
            ]
            valid_texts = [str(t).strip() for t in candidate_texts if str(t).strip()]
            needed_dur = max(cls.estimate_tts_duration(t) for t in valid_texts) if valid_texts else min_cue_duration

            # Next dialogue onset
            if i + 1 < len(ordered):
                next_sub_start = float(ordered[i + 1].get("sub_start", ordered[i + 1].get("start", orig_end)))
            elif video_duration is not None:
                next_sub_start = float(video_duration)
            elif max_timeline_duration is not None:
                next_sub_start = float(max_timeline_duration)
            else:
                next_sub_start = voice_end + 2.0

            # 1. Trailing expansion (priority): expand voice_end into following silence gap before next_sub_start
            max_trailing_end = next_sub_start - safe_gap_seconds
            if voice_dur < needed_dur and max_trailing_end > voice_end:
                voice_end = min(voice_start + needed_dur, max_trailing_end)
                voice_dur = max(0.0, voice_end - voice_start)

            # 2. Ripple-nudge (cautious with anti-cumulative drift):
            if voice_dur < needed_dur and i + 1 < len(ordered):
                next_cue = ordered[i + 1]
                next_sub_s = float(next_cue.get("sub_start", next_cue.get("start", 0.0)))
                next_sub_e = float(next_cue.get("sub_end", next_cue.get("end", next_sub_s)))
                next_v_s = float(next_cue.get("voice_start", next_sub_s))
                next_v_e = float(next_cue.get("voice_end", next_sub_e))
                next_v_dur = next_v_e - next_v_s

                gap_to_next_speech = next_sub_s - orig_end
                if gap_to_next_speech < 0.12:
                    if i + 2 < len(ordered):
                        after_next_sub_s = float(ordered[i + 2].get("sub_start", ordered[i + 2].get("start", next_v_e)))
                    elif video_duration is not None:
                        after_next_sub_s = float(video_duration)
                    elif max_timeline_duration is not None:
                        after_next_sub_s = float(max_timeline_duration)
                    else:
                        after_next_sub_s = next_v_e + 2.0

                    available_after_next = max(0.0, after_next_sub_s - next_v_e - safe_gap_seconds)
                    if available_after_next >= 0.5:
                        current_drift = next_v_s - next_sub_s
                        remaining_drift_budget = max(0.0, cls.MAX_CUMULATIVE_DRIFT - current_drift)
                        deficit = needed_dur - voice_dur
                        nudge = min(deficit, available_after_next, cls.MAX_PER_NUDGE, remaining_drift_budget)
                        if nudge >= 0.03:
                            # Nudge ONLY next cue's voice window (NOT its subtitle timeline!)
                            next_cue["voice_start"] = round(next_v_s + nudge, 3)
                            next_cue["voice_end"] = round(next_cue["voice_start"] + next_v_dur, 3)
                            # Expand current cue's voice_end into the created gap
                            voice_end = min(voice_start + needed_dur, next_cue["voice_start"] - safe_gap_seconds)
                            voice_dur = max(0.0, voice_end - voice_start)

            # 3. Leading expansion (last resort): borrow leading silence before current cue
            if voice_dur < needed_dur:
                prev_sub_e = float(ordered[i - 1].get("sub_end", ordered[i - 1].get("end", 0.0))) if i > 0 else 0.0
                available_leading = max(0.0, voice_start - prev_sub_e - safe_gap_seconds)
                deficit = needed_dur - voice_dur
                if available_leading > 0.03 and deficit > 0.02:
                    borrow = min(deficit, available_leading, cls.MAX_LEADING)
                    voice_start = max(round(voice_start - borrow, 3), 0.0)
                    voice_dur = max(0.0, voice_end - voice_start)

            # 4. Multi-level Candidate Shortening & TTS Speed Evaluation
            cue["voice_start"] = round(voice_start, 3)
            cue["voice_end"] = round(voice_end, 3)
            available_voice_dur = round(voice_end - voice_start, 3)

            primary_text = ""
            for t in [cue.get("dubbing_vi"), cue.get("tts_text"), cue.get("final_text"), cue.get("text")]:
                if str(t or "").strip():
                    primary_text = str(t).strip()
                    break

            candidates = cls.generate_shorten_candidates(primary_text)
            best_cand = candidates[0] if candidates else primary_text
            best_speed = cls.estimate_tts_speed(best_cand, available_voice_dur)
            fit_quality = "natural" if best_speed <= cls.TARGET_MAX_SPEED else ("acceptable" if best_speed <= cls.HARD_MAX_SPEED else "overflow")

            if best_speed > cls.TARGET_MAX_SPEED:
                found_acceptable = False
                for cand in candidates[1:]:
                    cand_speed = cls.estimate_tts_speed(cand, available_voice_dur)
                    if cand_speed <= cls.TARGET_MAX_SPEED:
                        best_cand = cand
                        best_speed = cand_speed
                        fit_quality = "natural"
                        found_acceptable = True
                        break
                    elif cand_speed <= cls.HARD_MAX_SPEED:
                        best_cand = cand
                        best_speed = cand_speed
                        fit_quality = "acceptable"
                        found_acceptable = True
                if not found_acceptable:
                    # In overflow, attempt AI shortening ONLY when enable_ai is True (e.g. in VoiceWorkflow background worker)
                    if enable_ai:
                        prev_text = ""
                        if i > 0:
                            prev_text = str(ordered[i - 1].get("dubbing_vi") or ordered[i - 1].get("text") or "")
                        ai_cand = cls.ai_shorten_text_for_tts(
                            primary_text,
                            available_voice_dur,
                            context_prev=prev_text,
                        )
                        if ai_cand and ai_cand != primary_text:
                            ai_speed = cls.estimate_tts_speed(ai_cand, available_voice_dur)
                            best_cand = ai_cand
                            best_speed = ai_speed
                            if ai_speed <= cls.TARGET_MAX_SPEED:
                                fit_quality = "natural"
                                found_acceptable = True
                            elif ai_speed <= cls.HARD_MAX_SPEED:
                                fit_quality = "acceptable"
                                found_acceptable = True
                            else:
                                fit_quality = "overflow"
                                found_acceptable = True

                    if not found_acceptable and candidates:
                        # Fallback: keep the best complete candidate (never drop sentence words)
                        best_cand = candidates[1] if len(candidates) > 1 else candidates[0]
                        best_speed = cls.estimate_tts_speed(best_cand, available_voice_dur)
                        fit_quality = "overflow"

            cue["dubbing_vi"] = best_cand
            cue["tts_text"] = best_cand
            cue["fit_quality"] = fit_quality
            if fit_quality == "overflow":
                cue["timing_conflict"] = True
                cue["overflow_seconds"] = round(cls.estimate_tts_duration(best_cand) - available_voice_dur * cls.HARD_MAX_SPEED, 3)
            else:
                cue["timing_conflict"] = False

        return ordered



    @classmethod
    def _is_near_prefix(cls, full_norm: str, prefix_norm: str, min_chars: int = 2) -> bool:
        """Check if prefix_norm is a prefix or near-prefix of full_norm (allowing minor ASR variation)."""
        if not full_norm or not prefix_norm or len(prefix_norm) < min_chars:
            return False
        if full_norm.startswith(prefix_norm):
            return True
        # For short phrases (<= 6 chars), require exact prefix only to prevent false positives
        if len(prefix_norm) <= 6:
            return False
        k = len(prefix_norm)
        if len(full_norm) >= k:
            head = full_norm[:k]
            sim = SequenceMatcher(None, head, prefix_norm).ratio()
            if sim >= 0.88:
                return True
        return False

    @classmethod
    def _find_suffix_prefix_overlap(cls, left_text: str, right_text: str) -> tuple[int, str]:
        left = str(left_text or "").strip()
        right = str(right_text or "").strip()
        if not left or not right:
            return 0, ""

        left_norm = re.sub(r"[^\w]", "", left.lower())
        right_norm = re.sub(r"[^\w]", "", right.lower())
        if not left_norm or not right_norm:
            return 0, ""

        max_search = min(len(left_norm), len(right_norm))
        for k in range(max_search, 1, -1):
            suffix = left_norm[-k:]
            prefix = right_norm[:k]
            if suffix == prefix:
                return k, suffix
        return 0, ""

    @classmethod
    def _stitch_text(cls, left: str, right: str, overlap_norm_len: int) -> str:
        matched = 0
        right_cut_idx = len(right)
        for idx, char in enumerate(right):
            if re.match(r"\w", char):
                matched += 1
                if matched == overlap_norm_len:
                    right_cut_idx = idx + 1
                    break
        continuation = right[right_cut_idx:].strip()
        if not continuation:
            return left
        if left and left[-1] in "，, ":
            return f"{left}{continuation}".strip()
        elif re.search(r"[\u3400-\u9fff\uf900-\ufaff]", left):
            return f"{left}{continuation}".strip()
        else:
            return f"{left} {continuation}".strip()

    @classmethod
    def deduplicate_and_clamp_timeline(
        cls,
        segments: list[dict],
        *,
        min_gap_seconds: float = 0.02,
        similarity_threshold: float = 0.85,
    ) -> list[dict]:
        """Remove duplicate, near-duplicate, and prefix/suffix overlapping cues,

        and enforce clean non-overlapping timeline boundaries.
        """
        if not segments:
            return []

        # Validate and order first; deduplication is neighbour-based and must
        # never operate on a cache/import list that happens to be unsorted.
        ordered_raw: list[tuple[float, float, dict]] = []
        for raw in segments:
            if not isinstance(raw, dict):
                continue
            text = str(raw.get("text", "") or "").strip()
            if not text:
                continue
            try:
                start = float(raw.get("start", 0.0) or 0.0)
                end = float(raw.get("end", start) or start)
            except (TypeError, ValueError):
                continue
            if not (math.isfinite(start) and math.isfinite(end)):
                continue
            start = max(0.0, start)
            end = max(start + 0.1, end)
            ordered_raw.append((start, end, raw))

        ordered_raw.sort(key=lambda item: (item[0], item[1]))
        cleaned: list[dict] = []
        for _parsed_start, _parsed_end, raw in ordered_raw:
            # Values were validated above; parse again only to preserve the
            # existing per-item normalization and metadata copying below.
            start = _parsed_start
            end = _parsed_end
            item = dict(raw)
            item["start"] = start
            item["end"] = end
            item["text"] = str(raw.get("text", "") or "").strip()

            if not cleaned:
                cleaned.append(item)
                continue

            prev = cleaned[-1]
            prev_text = prev["text"].strip()
            item_text = item["text"].strip()

            prev_norm = re.sub(r"[^\w]", "", prev_text.lower())
            item_norm = re.sub(r"[^\w]", "", item_text.lower())

            overlap = max(0.0, min(prev["end"], item["end"]) - max(prev["start"], item["start"]))
            time_gap = item["start"] - prev["end"]

            # Check for duplication / prefix-containment if they overlap or are very close (gap < 0.5s)
            if overlap > 0.0 or time_gap < 0.5:
                # Case 1: Exact or near-exact duplicate (>= similarity_threshold)
                sim = SequenceMatcher(None, prev_norm, item_norm).ratio() if prev_norm and item_norm else 0.0
                if sim >= similarity_threshold:
                    if (item["end"] - item["start"]) > (prev["end"] - prev["start"]):
                        cleaned[-1] = item
                    continue

                prev_old_end = float(prev.get("end", 0.0) or 0.0)
                # Case 2: item is an extension/completion of prev (fuzzy prefix)
                if cls._is_near_prefix(item_norm, prev_norm):
                    cleaned[-1] = item
                    continue

                # Case 3: prev is an extension of item (fuzzy prefix)
                if cls._is_near_prefix(prev_norm, item_norm):
                    continue

                # Case 4: Suffix-prefix overlap (end of prev is start of item) -> STITCH, not just clamp!
                if overlap > 0.15 or (0.0 <= item["start"] - prev["end"] <= 0.3):
                    overlap_len, _ = cls._find_suffix_prefix_overlap(prev_text, item_text)
                    if overlap_len >= 2:
                        stitched_text = cls._stitch_text(prev_text, item_text, overlap_len)
                        prev["text"] = stitched_text
                        prev["end"] = max(float(prev["end"]), float(item["end"]))
                        if item.get("words"):
                            prev["words"] = list(prev.get("words") or []) + [
                                w for w in (item.get("words") or [])
                                if float(w.get("start", 0.0)) >= prev_old_end - 0.05
                            ]
                        continue  # Merged into prev, do NOT append item separately

                # Case 5: Absorb a tiny trailing fragment into the preceding cue.
                # A recognizer sometimes emits a sub-second, 1-4 character fragment
                # (``草重层`` after ``操縱層是你打的``, or ``先盛職`` after ``血胜值``)
                # at the exact end of a longer cue. This is a re-read / partial
                # echo of the same utterance or caption, not a second line of
                # dialogue. Genuine adjacent dialogue lines are longer than 0.4s
                # or leave a beat between them, so the window below stays narrow.
                if cls._is_absorbable_tail_fragment(prev, item):
                    prev_old_end = float(prev["end"])
                    prev["end"] = max(prev_old_end, float(item["end"]))
                    if item.get("words"):
                        prev["words"] = list(prev.get("words") or []) + [
                            w for w in (item.get("words") or [])
                            if float(w.get("start", 0.0)) >= prev_old_end - 0.05
                        ]
                    continue  # Fragment absorbed; do NOT append item separately

            # Enforce clean non-overlapping timeline boundaries so subtitles never collide on screen
            if overlap > 0.0:
                if overlap <= 0.15:
                    prev["end"] = max(float(prev["start"]) + 0.1, float(item["start"]) - min_gap_seconds)
                else:
                    midpoint = (float(prev["end"]) + float(item["start"])) * 0.5
                    prev["end"] = max(float(prev["start"]) + 0.1, midpoint - min_gap_seconds * 0.5)
                    item["start"] = min(float(item["end"]) - 0.1, max(float(prev["end"]) + min_gap_seconds, midpoint + min_gap_seconds * 0.5))
                if prev.get("words"):
                    for w in prev["words"]:
                        if float(w.get("end", 0.0)) > float(prev["end"]):
                            w["end"] = round(float(prev["end"]), 3)
                if item.get("words"):
                    for w in item["words"]:
                        if float(w.get("start", 0.0)) < float(item["start"]):
                            w["start"] = round(float(item["start"]), 3)

            cleaned.append(item)

        # ASR workers normally emit sorted output, but OCR imports, cached
        # artifacts, and multi-video timelines do not guarantee that.  All
        # overlap/dedup decisions must be made in timeline order or an
        # out-of-order cue can shift/clamp the wrong neighbour.
        ordered = sorted(cleaned, key=lambda item: (float(item["start"]), float(item["end"])))
        return cls.expand_short_cues_into_gaps(ordered)

    @staticmethod
    def _is_absorbable_tail_fragment(prev: dict, item: dict) -> bool:
        """True when ``item`` is a tiny echo of the tail of ``prev``.

        Sub-second recognizer output that starts exactly where the previous
        cue ends and carries at most 4 characters is a re-read of the same
        utterance or on-screen caption (``先盛職`` after ``血胜值``), not a
        second line of dialogue. Genuine adjacent dialogue lines either last
        longer than 0.4s or leave a beat between cues, so the combined window
        below is intentionally narrow.
        """
        prev_start = float(prev.get("start", 0.0) or 0.0)
        prev_end = float(prev.get("end", prev_start) or prev_start)
        item_start = float(item.get("start", 0.0) or 0.0)
        item_end = float(item.get("end", item_start) or item_start)
        if item_end <= item_start:
            return False
        head_duration = prev_end - prev_start
        tail_duration = item_end - item_start
        gap = item_start - prev_end
        if not (-0.02 <= gap <= 0.05):
            return False
        if head_duration < 0.55 or tail_duration > 0.40:
            return False
        if item_end - prev_start > 1.25:
            return False
        prev_norm = re.sub(r"[^\w]", "", str(prev.get("text", "") or "").lower())
        item_norm = re.sub(r"[^\w]", "", str(item.get("text", "") or "").lower())
        if not prev_norm or len(prev_norm) < 2:
            return False
        if not item_norm or len(item_norm) > 4 or item_norm == prev_norm:
            return False
        return True

    def _split_oversized_segment(
        self,
        segment: dict,
        *,
        max_duration_seconds: float,
    ) -> list[dict]:
        """Keep ASR boundaries unless one cue is too long for dialogue/TTS.

        Whisper word timestamps are authoritative when available. Engines
        without word timing (notably SenseVoice) use sentence boundaries and
        finally a proportional text/time split. The fallback is deliberately
        limited to oversized cues; short acknowledgements are never merged or
        rewritten.
        """
        payload = self._clone_segment(segment)
        start = float(payload.get("start", 0.0))
        end = max(start, float(payload.get("end", start)))
        limit = max(0.5, float(max_duration_seconds or 0.0))
        if end - start <= limit + 0.01:
            return [payload]

        words = self._valid_words(payload.get("words"), start=start, end=end)
        if words:
            pieces = self._split_by_words(payload, words, limit=limit)
            if len(pieces) > 1:
                return pieces
        return self._split_text_proportionally(payload, limit=limit)

    @staticmethod
    def _valid_words(words, *, start: float, end: float) -> list[dict]:
        valid: list[dict] = []
        for word in words or []:
            try:
                word_start = max(start, float(word.get("start", start)))
                word_end = min(end, max(word_start, float(word.get("end", word_start))))
            except (AttributeError, TypeError, ValueError):
                continue
            text = str(word.get("text", word.get("word", "")) or "").strip()
            if text and word_end >= word_start:
                valid.append({"start": word_start, "end": word_end, "text": text})
        return sorted(valid, key=lambda item: (item["start"], item["end"]))

    def _split_by_words(self, payload: dict, words: list[dict], *, limit: float) -> list[dict]:
        groups: list[list[dict]] = []
        current: list[dict] = []
        group_start = float(payload["start"])
        for word in words:
            if current and float(word["end"]) - group_start > limit:
                groups.append(current)
                current = []
                group_start = float(word["start"])
            if not current:
                group_start = float(word["start"])
            current.append(word)
            if re.search(r"[.!?\u3002\uff01\uff1f\uff1b;]\s*$", str(word["text"])):
                groups.append(current)
                current = []
        if current:
            groups.append(current)
        if len(groups) <= 1:
            return []

        pieces: list[dict] = []
        original_start = float(payload["start"])
        original_end = float(payload["end"])
        for index, group in enumerate(groups):
            piece = self._clone_segment(payload)
            piece["start"] = original_start if index == 0 else float(group[0]["start"])
            piece["end"] = original_end if index == len(groups) - 1 else float(group[-1]["end"])
            piece["text"] = self._join_word_text(group)
            piece["words"] = list(group)
            piece["split_from_long_asr"] = True
            pieces.append(piece)
        return pieces

    @staticmethod
    def _join_word_text(words: list[dict]) -> str:
        values = [str(word.get("text", "") or "").strip() for word in words]
        if values and all(re.search(r"[\u3400-\u9fff\uf900-\ufaff]", value) for value in values):
            return "".join(values)
        return " ".join(values).strip()

    def _split_text_proportionally(self, payload: dict, *, limit: float) -> list[dict]:
        text = str(payload.get("text", "") or "").strip()
        start = float(payload["start"])
        end = float(payload["end"])
        part_count = max(2, int(ceil((end - start) / limit)))
        tokens = self._text_tokens(text)
        if len(tokens) < part_count:
            return [payload]

        duration = end - start
        while True:
            groups: list[list[str]] = []
            cursor = 0
            for part_index in range(part_count):
                remaining_parts = part_count - part_index
                remaining_tokens = len(tokens) - cursor
                take = max(1, int(ceil(remaining_tokens / remaining_parts)))
                if part_index < part_count - 1:
                    take = self._prefer_sentence_boundary(tokens, cursor, take)
                    # Leave at least one token for every remaining piece.
                    take = min(take, remaining_tokens - (remaining_parts - 1))
                groups.append(tokens[cursor:cursor + take])
                cursor += take
            if cursor < len(tokens):
                groups[-1].extend(tokens[cursor:])
            total_units = float(sum(max(1, len("".join(group))) for group in groups))
            longest_duration = duration * max(
                max(1, len("".join(group))) for group in groups
            ) / total_units
            if longest_duration <= limit + 0.01 or part_count >= len(tokens):
                break
            part_count += 1

        pieces: list[dict] = []
        consumed_units = 0.0
        for index, group in enumerate(groups):
            units = float(max(1, len("".join(group))))
            piece = self._clone_segment(payload)
            piece["start"] = start + duration * (consumed_units / total_units)
            consumed_units += units
            piece["end"] = end if index == len(groups) - 1 else start + duration * (consumed_units / total_units)
            piece["text"] = self._join_text_tokens(group)
            piece.pop("words", None)
            piece["split_from_long_asr"] = True
            pieces.append(piece)
        return pieces

    @staticmethod
    def _text_tokens(text: str) -> list[str]:
        if re.search(r"[\u3400-\u9fff\uf900-\ufaff]", text) and not re.search(r"\s", text):
            return list(text)
        return re.findall(r"\S+", text)

    @staticmethod
    def _prefer_sentence_boundary(tokens: list[str], start: int, take: int) -> int:
        target = min(len(tokens), start + take)
        lower = max(start + 1, target - max(2, take // 3))
        upper = min(len(tokens) - 1, target + max(2, take // 3))
        for index in range(target, lower - 1, -1):
            if re.search(r"[,.!?;:\u3002\uff0c\uff01\uff1f\uff1b]$", tokens[index - 1]):
                return index - start
        for index in range(target + 1, upper + 1):
            if re.search(r"[,.!?;:\u3002\uff0c\uff01\uff1f\uff1b]$", tokens[index - 1]):
                return index - start
        return take

    @staticmethod
    def _join_text_tokens(tokens: list[str]) -> str:
        if tokens and all(re.search(r"[\u3400-\u9fff\uf900-\ufaff]", token) for token in tokens):
            return "".join(tokens)
        return " ".join(tokens).strip()

    def _clone_segment(self, segment: dict) -> dict:
        payload = {
            "start": float(segment.get("start", 0.0)),
            "end": float(segment.get("end", 0.0)),
            "text": str(segment.get("text", "") or "").strip(),
        }
        if segment.get("words"):
            payload["words"] = list(segment.get("words") or [])
        if segment.get("chunk_id"):
            payload["chunk_id"] = segment.get("chunk_id")
        for key in (
            "speaker", "language", "confidence", "split_from_long_asr",
            "speech_detected", "speech_gate",
        ):
            if key in segment:
                payload[key] = segment[key]
        return payload

    def _normalize_sentence_text(self, text: str) -> str:
        value = re.sub(r"\s+", " ", str(text or "").strip())
        return value

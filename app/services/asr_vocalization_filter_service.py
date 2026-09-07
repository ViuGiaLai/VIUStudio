from __future__ import annotations

import re
import unicodedata


class AsrVocalizationFilterService:
    """Remove isolated, non-semantic ASR vocalizations from generated cues.

    Short breaths, music attacks, and effects frequently pass a speech VAD and
    are decoded by compact ASR models as fillers such as Chinese ``嗯``.  Those
    cues have no useful translation content and are especially disruptive once
    synthesized by TTS.  Only a complete standalone vocalization is removed;
    the same token inside real dialogue remains untouched.
    """

    VERSION = "asr-vocalization-filter-v1"

    _STANDALONE_VOCALIZATIONS = {
        # Chinese / Japanese / Korean recognition output.
        "嗯", "嗯嗯", "呃", "额", "啊", "哦", "噢", "唔", "哼", "唉",
        "欸", "诶", "呵", "哈", "哇", "呀", "哟", "喔", "え", "ええ", "えー", "うん", "ああ",
        "あの", "음", "어", "아", "응",
        # Common Latin-script ASR equivalents. Keep meaningful acknowledgements
        # such as yes/no/okay: they can be complete dialogue turns.
        "um", "umm", "uh", "uhh", "erm", "hmm", "hm", "mm", "mhm",
        "ừm", "ờm", "hừm",
    }

    @classmethod
    def _normalized(cls, value: object) -> str:
        text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
        return re.sub(r"[^\w\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]+", "", text)

    @classmethod
    def is_standalone_vocalization(cls, value: object) -> bool:
        return cls._normalized(value) in cls._STANDALONE_VOCALIZATIONS

    @staticmethod
    def _is_non_speech_annotation(value: object) -> bool:
        text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
        match = re.fullmatch(r"[\[（(<【]\s*([^\]）)>】]+?)\s*[\]）)>】][.!?。！？]*", text)
        if not match:
            return False
        label = re.sub(r"[^\w\u3400-\u9fff]+", "", match.group(1))
        return label in {
            "music", "applause", "laughter", "laughing", "noise", "silence",
            "音乐", "音樂", "掌声", "掌聲", "笑声", "笑聲", "噪音",
        }

    @classmethod
    def _dominant_cjk_output(cls, segments: list[dict], source_language: str) -> bool:
        code = str(source_language or "auto").strip().lower().split("-")[0]
        if code in {"zh", "cmn", "yue", "ja", "ko"}:
            return True
        cjk_chars = 0
        latin_chars = 0
        for segment in segments or []:
            text = str((segment or {}).get("text", "") or "")
            cjk_chars += len(re.findall(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]", text))
            latin_chars += len(re.findall(r"[a-z]", text, flags=re.IGNORECASE))
        return cjk_chars >= 20 and cjk_chars >= latin_chars * 2

    @classmethod
    def _is_implausible_short_decode(cls, segment: dict) -> bool:
        """Detect decoder text that cannot fit inside its VAD interval."""
        try:
            start = float(segment.get("start", 0.0) or 0.0)
            end = float(segment.get("end", start) or start)
        except (TypeError, ValueError):
            return False
        duration = max(0.0, end - start)
        compact = cls._normalized(segment.get("text", ""))
        if not compact:
            return False
        # Repeated one-character stutters are a common compact-model fallback
        # on clicks/breaths. A real repeated response can still be preserved by
        # stable OCR below.
        if len(compact) == 2 and compact[0] == compact[1] and duration <= 0.20:
            return True
        # Two or more glyphs inside <=110ms is outside a credible subtitle
        # speaking rate and indicates that decode padding supplied the text
        # while VAD found essentially no utterance.
        return len(compact) >= 2 and duration <= 0.11

    @staticmethod
    def _has_authoritative_text_evidence(segment: dict) -> bool:
        source = str(segment.get("text_source", "") or "").strip().lower()
        if source.startswith("ocr_"):
            return True
        ocr_text = str(segment.get("ocr_text", "") or "").strip()
        try:
            consensus = int(segment.get("ocr_consensus_frames", 0) or 0)
        except (TypeError, ValueError):
            consensus = 0
        return bool(ocr_text and consensus >= 2)

    @classmethod
    def filter_generated_segments(
        cls,
        segments: list[dict],
        *,
        source_language: str = "auto",
    ) -> tuple[list[dict], int]:
        """Return generated ASR cues without unsupported filler-only output.

        Stable source-video OCR is allowed to preserve a real, visible
        interjection. Imported or manually edited subtitles never pass through
        this method, so user-authored content is not silently changed.
        """
        kept, removed, _rejected = cls.filter_generated_segments_with_report(
            segments,
            source_language=source_language,
        )
        return kept, removed

    @classmethod
    def filter_generated_segments_with_report(
        cls,
        segments: list[dict],
        *,
        source_language: str = "auto",
    ) -> tuple[list[dict], int, list[dict]]:
        """Filter generated cues and return an auditable rejection report."""
        kept: list[dict] = []
        rejected: list[dict] = []
        dominant_cjk = cls._dominant_cjk_output(segments, source_language)
        for raw in segments or []:
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            text = item.get("text", "")
            cross_script_fragment = bool(
                dominant_cjk
                and re.fullmatch(r"\s*[a-z]\s*[.!?]?\s*", str(text or ""), re.IGNORECASE)
            )
            reason = ""
            if (
                (
                    cls.is_standalone_vocalization(text)
                    or cls._is_non_speech_annotation(text)
                    or cross_script_fragment
                    or cls._is_implausible_short_decode(item)
                )
                and not cls._has_authoritative_text_evidence(item)
            ):
                if cls.is_standalone_vocalization(text):
                    reason = "standalone_vocalization"
                elif cls._is_non_speech_annotation(text):
                    reason = "non_speech_annotation"
                elif cross_script_fragment:
                    reason = "cross_script_fragment"
                else:
                    reason = "implausible_short_decode"
                rejected.append({
                    "start": item.get("start", 0.0),
                    "end": item.get("end", 0.0),
                    "text": str(text or ""),
                    "reason": reason,
                })
                continue
            kept.append(item)
        return kept, len(rejected), rejected

    @classmethod
    def filter_tts_segments(cls, segments: list[dict]) -> tuple[list[dict], int]:
        """Defensively silence stale generated filler cues before synthesis."""
        kept: list[dict] = []
        removed = 0
        for raw in segments or []:
            item = dict(raw or {})
            source_text = item.get("original_text") or item.get("source_text") or ""
            manually_authored = bool(item.get("voice_edited") or item.get("manual_text"))
            if (
                not manually_authored
                and (
                    cls.is_standalone_vocalization(source_text)
                    or cls._is_non_speech_annotation(source_text)
                )
                and not cls._has_authoritative_text_evidence(item)
            ):
                removed += 1
                continue
            kept.append(item)
        return kept, removed

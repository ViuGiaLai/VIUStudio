from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


_SCRIPT_PATTERNS = {
    "han": re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"),
    "japanese": re.compile(r"[\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff]"),
    "korean": re.compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af\u3400-\u4dbf\u4e00-\u9fff]"),
    "latin": re.compile(r"[A-Za-z\u00c0-\u024f]"),
    "cyrillic": re.compile(r"[\u0400-\u052f]"),
    "arabic": re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]"),
    "thai": re.compile(r"[\u0e00-\u0e7f]"),
}
_LANGUAGE_FAMILIES = {
    "zh": "han", "cmn": "han", "yue": "han",
    "ja": "japanese", "ko": "korean",
    "en": "latin", "vi": "latin", "id": "latin", "es": "latin",
    "fr": "latin", "de": "latin", "pt": "latin",
    "ru": "cyrillic", "ar": "arabic", "th": "thai",
}
_SUSPICIOUS_LENGTH = {
    "han": 4, "japanese": 4, "korean": 4, "latin": 4,
    "cyrillic": 4, "arabic": 4, "thai": 4,
}
# Latin substrings are especially collision-prone (``he`` inside ``the``),
# so require complete tokens there. Other supported scripts commonly attach
# particles/prefixes without spaces and need compact matching.
_WORD_BASED_FAMILIES = {"latin"}
_NON_DIALOGUE_OCR_PATTERNS = (
    # Common burned-in cards/labels that can contain a short ASR token but are
    # not the subtitle of the current spoken line.
    re.compile(r"(?:下集|精彩|剧集)?预告|未完待续|第[一二三四五六七八九十百千万0-9]+集"),
    re.compile(r"次回予告|つづく|続く", re.IGNORECASE),
    re.compile(r"다음\s*화\s*예고|미리\s*보기"),
    re.compile(r"\b(?:next\s+episode|preview|trailer|to\s+be\s+continued)\b", re.IGNORECASE),
    re.compile(r"\b(?:tập\s+tiếp\s+theo|xem\s+trước|còn\s+tiếp)\b", re.IGNORECASE),
)


class AsrOcrReconciliationService:
    """Verify recognition-risk ASR cues against burned-in source subtitles.

    VAD remains authoritative for the presence and outer timing of speech.
    Spatially filtered OCR becomes authoritative for text only after temporal
    consensus; a sequence of stable OCR states may split a merged ASR cue.
    Script checks and title-card rejection keep unrelated visible text out of
    the spoken transcript.
    """

    VERSION = "multilingual-fast-adaptive-dialogue-segmentation-v16"
    MAX_TIME_SLOP_SECONDS = 0.45
    MAX_OCR_LENGTH = 80
    MERGE_RISK_DURATION_SECONDS = 2.5
    AUTHORITATIVE_SHORT_LENGTH = {
        "han": 4, "japanese": 4, "korean": 5, "latin": 8,
        "cyrillic": 8, "arabic": 8, "thai": 8,
    }

    @staticmethod
    def _has_speech_evidence(segment: dict) -> bool:
        """Honor an explicit VAD result while remaining compatible with Whisper."""
        return "speech_detected" not in segment or segment.get("speech_detected") is True

    @staticmethod
    def _is_non_dialogue_ocr_text(value: object) -> bool:
        text = unicodedata.normalize("NFKC", str(value or "")).strip()
        return any(pattern.search(text) for pattern in _NON_DIALOGUE_OCR_PATTERNS)

    @staticmethod
    def _language_family(source_language: str) -> str:
        code = str(source_language or "auto").strip().lower().split("-")[0]
        return _LANGUAGE_FAMILIES.get(code, "")

    @staticmethod
    def _detect_family(value: object) -> str:
        text = str(value or "")
        counts = {
            family: len(pattern.findall(text))
            for family, pattern in _SCRIPT_PATTERNS.items()
        }
        return max(counts, key=counts.get) if counts and max(counts.values()) > 0 else ""

    @staticmethod
    def _normalized(value: object, family: str) -> str:
        text = unicodedata.normalize("NFKC", str(value or "")).casefold()
        tokens = []
        current = []
        for char in text:
            if char.isalpha() or char.isdigit():
                current.append(char)
            elif current:
                tokens.append("".join(current))
                current = []
        if current:
            tokens.append("".join(current))
        separator = " " if family in _WORD_BASED_FAMILIES else ""
        return separator.join(tokens)

    @classmethod
    def _is_family_text(cls, value: object, family: str) -> bool:
        if family not in _SCRIPT_PATTERNS:
            return False
        text = str(value or "")
        letters = sum(1 for char in text if char.isalpha())
        script_chars = len(_SCRIPT_PATTERNS[family].findall(text))
        return letters > 0 and script_chars / letters >= 0.7

    @classmethod
    def _is_suspicious(cls, value: object, family: str) -> bool:
        if family not in _SUSPICIOUS_LENGTH or not cls._is_family_text(value, family):
            return False
        normalized = cls._normalized(value, family)
        compact = normalized.replace(" ", "")
        if not compact or len(compact) > _SUSPICIOUS_LENGTH[family]:
            return False
        if family in _WORD_BASED_FAMILIES and len(normalized.split()) != 1:
            return False
        return True

    @classmethod
    def _needs_ocr_verification(cls, segment: dict, family: str) -> bool:
        """Select cues where SenseVoice commonly loses, adds, or merges text."""
        text = segment.get("text", "")
        if family not in cls.AUTHORITATIVE_SHORT_LENGTH or not cls._is_family_text(text, family):
            return False
        compact = cls._normalized(text, family).replace(" ", "")
        if not compact:
            return False
        try:
            start = float(segment.get("start", 0.0) or 0.0)
            end = max(start, float(segment.get("end", start) or start))
        except (TypeError, ValueError):
            start = end = 0.0
        duration = end - start
        char_count = len(compact)
        # Low speech density: speaking for 1.5+s with <= 6 characters (likely truncated ASR)
        low_density = duration >= 1.5 and char_count <= 6
        # Multi-sentence / merge risk: long duration AND contains an actual
        # clause-ending punctuation mark (or whitespace for CJK scripts where spaces indicate clause pauses).
        if family in {"han", "japanese", "korean"}:
            has_clause_break = bool(re.search(r"[,，。!?！？;；\s]", text.strip()))
        else:
            has_clause_break = bool(re.search(r"[,，。!?！？;；]", text.strip()))
        merge_risk = duration >= cls.MERGE_RISK_DURATION_SECONDS and (has_clause_break or low_density)
        # Low confidence score if provided by ASR engine
        low_confidence = False
        if segment.get("confidence") is not None:
            try:
                low_confidence = float(segment["confidence"]) < 0.75
            except (TypeError, ValueError):
                pass
        # When a video has burned-in source subtitles, a stable two-frame OCR
        # result is stronger evidence than ASR for names and compact dialogue.
        # Verify every normally sized spoken cue, not only very short ASR text;
        # the hardsub precheck still prevents this work on ordinary videos.
        hardsub_verifiable = (
            0.20 <= duration <= 12.0
            and char_count <= cls.MAX_OCR_LENGTH
        )
        return bool(
            hardsub_verifiable
            or
            char_count <= cls.AUTHORITATIVE_SHORT_LENGTH[family]
            or merge_risk
            or low_density
            or low_confidence
            or segment.get("split_from_long_asr") is True
        )

    @classmethod
    def should_scan(cls, asr_segments: list[dict], source_language: str) -> bool:
        # NOTE: this deliberately does NOT hard-gate on `_LANGUAGE_FAMILIES`
        # membership. `_LANGUAGE_FAMILIES` is only a whitelist of language
        # *codes* we can shortcut without inspecting the text; it is not an
        # exhaustive list of supported scripts. Every other entry point in
        # this class (`suspicious_time_ranges`, `suspicious_cue_requests`,
        # `reconcile`) already falls back to `_detect_family()` per segment
        # when the language code isn't in the whitelist, so a video tagged
        # with an unlisted-but-supported code (e.g. "it", "nl", "tr") still
        # gets reconciled correctly by those methods. Previously this method
        # short-circuited to False for any such language, silently disabling
        # OCR reconciliation before it ever got a chance to run, even though
        # the rest of the pipeline was fully capable of handling it. Keeping
        # `should_scan` consistent with the other methods avoids that gap.
        explicit_family = cls._language_family(source_language)
        return any(
            cls._has_speech_evidence(segment) and cls._needs_ocr_verification(
                segment,
                explicit_family or cls._detect_family(segment.get("text", "")),
            )
            for segment in asr_segments or []
        )

    @classmethod
    def suspicious_time_ranges(
        cls,
        asr_segments: list[dict],
        *,
        source_language: str = "auto",
        padding_seconds: float = 0.75,
    ) -> list[tuple[float, float]]:
        explicit_family = cls._language_family(source_language)
        pending = []
        for segment in asr_segments or []:
            if not cls._has_speech_evidence(segment):
                continue
            family = explicit_family or cls._detect_family(segment.get("text", ""))
            if not cls._needs_ocr_verification(segment, family):
                continue
            start = max(0.0, float(segment.get("start", 0.0) or 0.0) - padding_seconds)
            end = max(start, float(segment.get("end", start) or start) + padding_seconds)
            pending.append((start, end))
        ranges = []
        for start, end in sorted(pending):
            if ranges and start - ranges[-1][1] <= cls.MAX_TIME_SLOP_SECONDS:
                ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
            else:
                ranges.append((start, end))
        # Do not truncate long projects. A fixed 512-cue cap silently left the
        # second half of long videos without OCR verification, making quality
        # depend on where a line appeared in the timeline.
        return ranges

    @classmethod
    def suspicious_cue_ranges(
        cls,
        asr_segments: list[dict],
        *,
        source_language: str = "auto",
        padding_seconds: float = 0.15,
    ) -> list[tuple[float, float]]:
        """Return one tight OCR window per suspect cue without merging cues."""
        return [
            (request["start"], request["end"])
            for request in cls.suspicious_cue_requests(
                asr_segments,
                source_language=source_language,
                padding_seconds=padding_seconds,
            )
        ]

    @classmethod
    def suspicious_cue_requests(
        cls,
        asr_segments: list[dict],
        *,
        source_language: str = "auto",
        padding_seconds: float = 0.15,
    ) -> list[dict]:
        """Return tight OCR windows together with their expected ASR text."""
        explicit_family = cls._language_family(source_language)
        requests = []
        for segment in asr_segments or []:
            if not cls._has_speech_evidence(segment):
                continue
            family = explicit_family or cls._detect_family(segment.get("text", ""))
            if not cls._needs_ocr_verification(segment, family):
                continue
            cue_start = float(segment.get("start", 0.0) or 0.0)
            cue_end = max(cue_start, float(segment.get("end", cue_start) or cue_start))
            # A two-second VAD cue can already contain two burned-in subtitle
            # states. Sequence sampling catches that transition instead of
            # assigning the midpoint text to the whole speech interval.
            scan_mode = "sequence" if cue_end - cue_start >= 1.35 else "authoritative"
            effective_padding = 0.0 if scan_mode == "sequence" else max(float(padding_seconds), 0.15)
            start = max(0.0, cue_start - effective_padding)
            end = max(start, cue_end + effective_padding)
            requests.append({
                "start": start,
                "end": end,
                "text": str(segment.get("text", "") or "").strip(),
                "scan_mode": scan_mode,
            })
        return requests

    @staticmethod
    def _interval_match(asr: dict, ocr: dict) -> tuple[float, float]:
        asr_start = float(asr.get("start", 0.0) or 0.0)
        asr_end = max(asr_start, float(asr.get("end", asr_start) or asr_start))
        ocr_start = float(ocr.get("start", 0.0) or 0.0)
        ocr_end = max(ocr_start, float(ocr.get("end", ocr_start) or ocr_start))
        overlap = max(0.0, min(asr_end, ocr_end) - max(asr_start, ocr_start))
        midpoint_distance = abs((asr_start + asr_end) * 0.5 - (ocr_start + ocr_end) * 0.5)
        return overlap, midpoint_distance

    @staticmethod
    def _contains_complete_cue(asr_text: str, ocr_text: str, family: str) -> bool:
        if family in _WORD_BASED_FAMILIES:
            asr_words = asr_text.split()
            ocr_words = ocr_text.split()
            width = len(asr_words)
            return bool(width) and any(
                ocr_words[index:index + width] == asr_words
                for index in range(len(ocr_words) - width + 1)
            )
        return bool(asr_text) and asr_text in ocr_text

    @classmethod
    def _is_safe_text_match(cls, asr_text: str, ocr_text: str, family: str) -> bool:
        if cls._contains_complete_cue(asr_text, ocr_text, family):
            # An OCR line that fully contains the ASR text -- including the
            # exact-match case where both strings are identical -- is a
            # safe candidate. Using a strict `>` here previously excluded
            # exact matches (the single most trustworthy case) from the
            # candidate pool: when multiple OCR lines exist in the same
            # window, discarding the exact match could let a noisier,
            # loosely-matching candidate win the `best` selection below and
            # overwrite an already-correct ASR cue.
            return len(ocr_text) >= len(asr_text)
        if family in _WORD_BASED_FAMILIES:
            return False
        # Permit close, similar-length corrections or multi-part sequence subtitles for CJK/compact-script cues.
        asr_len = len(asr_text.replace(" ", ""))
        ocr_len = len(ocr_text.replace(" ", ""))
        if 2 <= asr_len <= 40 and 2 <= ocr_len <= 40:
            len_ratio = ocr_len / max(1, asr_len)
            if 0.25 <= len_ratio <= 2.5:
                similarity = SequenceMatcher(None, asr_text, ocr_text).ratio()
                if (0.5 <= len_ratio <= 1.5 and similarity >= 0.20) or similarity >= 0.35:
                    return True
                common = sum(1 for ch in ocr_text if ch in asr_text)
                if common >= 2 and (similarity >= 0.15 or 0.5 <= len_ratio <= 1.5):
                    return True
        return False

    @classmethod
    def _normalize_reconciled_timeline(cls, segments: list[dict]) -> tuple[list[dict], int]:
        """Remove OCR flicker duplicates and return one non-overlapping lane."""
        ordered = sorted(
            (dict(segment) for segment in segments or []),
            key=lambda item: (
                float(item.get("start", 0.0) or 0.0),
                float(item.get("end", 0.0) or 0.0),
            ),
        )
        normalized: list[dict] = []
        changes = 0
        for item in ordered:
            try:
                item_start = max(0.0, float(item.get("start", 0.0) or 0.0))
                item_end = max(item_start, float(item.get("end", item_start) or item_start))
            except (TypeError, ValueError):
                continue
            item["start"], item["end"] = item_start, item_end
            item_family = cls._detect_family(item.get("text", ""))
            item_key = cls._normalized(item.get("text", ""), item_family)

            if normalized:
                previous = normalized[-1]
                previous_family = cls._detect_family(previous.get("text", ""))
                previous_key = cls._normalized(previous.get("text", ""), previous_family)
                gap = item_start - float(previous.get("end", item_start) or item_start)
                substantial_text = len(item_key.replace(" ", "")) >= 4
                text_similarity = (
                    SequenceMatcher(None, previous_key, item_key).ratio()
                    if previous_key and item_key
                    else 0.0
                )
                both_ocr_states = (
                    str(previous.get("text_source", "")).startswith("ocr_")
                    and str(item.get("text_source", "")).startswith("ocr_")
                )
                # A static burned-in caption stays on screen for seconds while
                # the sequence scan re-reads it every ~0.6s, and each read can
                # garble one or two glyphs differently (``妙小不理`` vs
                # ``莎小不延``). When a brief VAD pause (< 0.6s) separates two
                # OCR-only cues of the same caption, the gap rules above miss
                # the merge because the noisy re-reads share only ~70-85% of
                # their characters. Requiring a substantial cue on both sides
                # keeps short, genuinely distinct captions separate.
                ocr_read_repeat = (
                    both_ocr_states
                    and gap <= 0.6
                    and text_similarity >= 0.70
                    and len(item_key.replace(" ", "")) >= 6
                    and len(previous_key.replace(" ", "")) >= 6
                )
                flicker_duplicate = (
                    item_key == previous_key
                    or (both_ocr_states and gap <= 0.08 and text_similarity >= 0.55)
                    or ocr_read_repeat
                    or (gap <= 1.75 and text_similarity >= 0.86)
                )

                # Burned-in subtitles can briefly disappear during a cut or
                # glow transition, causing the same stable sentence to be
                # emitted twice. One spoken ASR cue must remain one cue.
                if (
                    substantial_text
                    and item_key
                    and flicker_duplicate
                ):
                    previous["start"] = min(float(previous["start"]), item_start)
                    previous["end"] = max(float(previous["end"]), item_end)
                    previous["text_source"] = "ocr_reconciled_deduplicated"
                    previous["ocr_duplicate_merged"] = int(previous.get("ocr_duplicate_merged", 0) or 0) + 1
                    previous["words"] = []
                    previous.pop("_audio_end", None)
                    if "tts_group_start" in previous:
                        previous["tts_group_start"] = previous["start"]
                    if "tts_group_end" in previous:
                        previous["tts_group_end"] = previous["end"]
                    changes += 1
                    continue

                # A very short OCR fragment that is already contained in the
                # following complete cue is a transition sample, not another
                # line of dialogue (for example ``二人不成`` immediately before
                # the full sentence ending in those same characters).
                item_end - item_start
                previous_duration = float(previous["end"]) - float(previous["start"])
                if (
                    previous_duration < 0.22
                    and previous_key
                    and previous_key in item_key
                ):
                    item["start"] = min(float(previous["start"]), item_start)
                    normalized.pop()
                    changes += 1

            if normalized and float(normalized[-1]["end"]) > float(item["start"]):
                previous = normalized[-1]
                boundary = (
                    float(previous["end"]) + float(item["start"])
                ) * 0.5
                boundary = max(float(previous["start"]) + 0.02, boundary)
                boundary = min(float(item["end"]) - 0.02, boundary)
                previous["end"] = boundary
                item["start"] = boundary
                previous.pop("_audio_end", None)
                item.pop("_audio_end", None)
                if "tts_group_end" in previous:
                    previous["tts_group_end"] = boundary
                if "tts_group_start" in item:
                    item["tts_group_start"] = boundary
                changes += 1
            normalized.append(item)
        return normalized, changes

    @classmethod
    def reconcile(
        cls,
        asr_segments: list[dict],
        ocr_segments: list[dict],
        *,
        source_language: str = "auto",
    ) -> tuple[list[dict], int]:
        repaired: list[dict] = []
        replacement_count = 0
        explicit_family = cls._language_family(source_language)

        for source in asr_segments or []:
            item = dict(source)
            asr_text = str(item.get("text", "") or "").strip()
            family = explicit_family or cls._detect_family(asr_text)
            asr_normalized = cls._normalized(asr_text, family)
            if (
                not cls._has_speech_evidence(item)
                or not cls._needs_ocr_verification(item, family)
            ):
                repaired.append(item)
                continue

            candidates = []
            for ocr in ocr_segments or []:
                ocr_text = str(ocr.get("text", "") or "").strip()
                if cls._is_non_dialogue_ocr_text(ocr_text):
                    continue
                if not cls._is_family_text(ocr_text, family):
                    continue
                ocr_normalized = cls._normalized(ocr_text, family)
                if not ocr_normalized or len(ocr_normalized.replace(" ", "")) > cls.MAX_OCR_LENGTH:
                    continue
                # Full/legacy OCR artifacts predate the consensus metadata and
                # are already temporally consolidated. Fast verification emits
                # the field explicitly; one frame there is never sufficient.
                stable_source_subtitle = (
                    "ocr_consensus_frames" not in ocr
                    or int(ocr.get("ocr_consensus_frames", 0) or 0) >= 2
                )
                if not stable_source_subtitle:
                    continue
                safe_legacy_match = (
                    cls._is_safe_text_match(asr_normalized, ocr_normalized, family)
                    or (
                        int(ocr.get("ocr_consensus_frames", 0) or 0) >= 2
                        and cls._is_suspicious(asr_text, family)
                    )
                )
                if not safe_legacy_match:
                    continue
                overlap, midpoint_distance = cls._interval_match(item, ocr)
                if overlap <= 0.0 and midpoint_distance > cls.MAX_TIME_SLOP_SECONDS:
                    continue
                candidates.append((overlap > 0.0, overlap, -midpoint_distance, -len(ocr_normalized), ocr))

            if candidates:
                ordered = sorted(
                    (candidate[-1] for candidate in candidates),
                    key=lambda value: (
                        float(value.get("start", 0.0) or 0.0),
                        float(value.get("end", 0.0) or 0.0),
                    ),
                )
                sequence_related = []
                for candidate in ordered:
                    if candidate.get("ocr_scan_mode") != "sequence":
                        continue
                    candidate_normalized = cls._normalized(
                        candidate.get("text", ""), family
                    )
                    matcher = SequenceMatcher(None, asr_normalized, candidate_normalized)
                    longest = matcher.find_longest_match(
                        0, len(asr_normalized), 0, len(candidate_normalized)
                    ).size
                    if (
                        candidate_normalized in asr_normalized
                        or asr_normalized in candidate_normalized
                        or (longest >= 2 and matcher.ratio() >= 0.22)
                    ):
                        sequence_related.append(candidate)
                # During subtitle fade-in a fast recognizer can briefly see a
                # stable but incomplete/background string. If other states in
                # the same sequence clearly align with ASR, discard only the
                # unrelated transition states before cue splitting.
                if sequence_related:
                    related_ids = {id(candidate) for candidate in sequence_related}
                    ordered = [
                        candidate for candidate in ordered
                        if candidate.get("ocr_scan_mode") != "sequence"
                        or id(candidate) in related_ids
                    ]
                distinct = []
                for candidate in ordered:
                    candidate_text = str(candidate.get("text", "") or "").strip()
                    candidate_key = cls._normalized(candidate_text, family)
                    if distinct and distinct[-1][0] == candidate_key:
                        distinct[-1] = (candidate_key, candidate)
                    else:
                        distinct.append((candidate_key, candidate))

                # A sequence scan can prove that one long ASR region contains
                # two different burned-in subtitle states. Split at the
                # midpoint between their confirmed sample windows.
                sequence_candidates = [
                    candidate for _key, candidate in distinct
                    if candidate.get("ocr_scan_mode") == "sequence"
                ]
                if len(sequence_candidates) > 1:
                    centers = [
                        (
                            float(candidate.get("start", 0.0) or 0.0)
                            + float(candidate.get("end", 0.0) or 0.0)
                        ) * 0.5
                        for candidate in sequence_candidates
                    ]
                    asr_start = float(item.get("start", 0.0) or 0.0)
                    asr_end = max(asr_start, float(item.get("end", asr_start) or asr_start))
                    first_ocr_start = float(sequence_candidates[0].get("start", asr_start) or asr_start)
                    last_ocr_end = float(sequence_candidates[-1].get("end", asr_end) or asr_end)
                    boundaries = [max(asr_start, min(asr_end, first_ocr_start))]
                    boundaries.extend(
                        max(
                            boundaries[-1],
                            min(
                                asr_end,
                                (
                                    float(sequence_candidates[i - 1].get("end", centers[i - 1]) or centers[i - 1])
                                    + float(sequence_candidates[i].get("start", centers[i]) or centers[i])
                                ) * 0.5,
                            ),
                        )
                        for i in range(1, len(centers))
                    )
                    boundaries.append(max(boundaries[-1], min(asr_end, last_ocr_end)))
                    for index, candidate in enumerate(sequence_candidates):
                        if boundaries[index + 1] <= boundaries[index] + 0.02:
                            continue
                        piece = dict(item)
                        ocr_text = str(candidate.get("text", "") or "").strip()
                        piece["start"] = boundaries[index]
                        piece["end"] = boundaries[index + 1]
                        piece["asr_text_original"] = asr_text
                        piece["ocr_text"] = ocr_text
                        piece["text_source"] = "ocr_reconciled_split"
                        piece["text"] = ocr_text
                        piece["words"] = []
                        repaired.append(piece)
                    replacement_count += 1
                    continue

                # Exact text agreement must outrank raw temporal overlap. A
                # nearby transition/title fragment can occupy more of the VAD
                # window than the real subtitle (for example ``金面金`` beside
                # ``韩念川是吧``); choosing by overlap first corrupts correct
                # ASR and prevents the useful OCR timing alignment.
                exact_candidates = [
                    candidate for candidate in candidates
                    if cls._normalized(candidate[-1].get("text", ""), family) == asr_normalized
                ]
                if exact_candidates:
                    best = max(exact_candidates, key=lambda candidate: candidate[:4])[-1]
                else:
                    best = max(
                        candidates,
                        key=lambda candidate: (
                            SequenceMatcher(
                                None,
                                asr_normalized,
                                cls._normalized(candidate[-1].get("text", ""), family),
                            ).ratio(),
                            *candidate[:4],
                        ),
                    )[-1]
                ocr_text = str(best.get("text", "") or "").strip()
                ocr_normalized = cls._normalized(ocr_text, family)

                # An exact, stable burned-in subtitle is also authoritative
                # timing evidence. ASR/VAD commonly opens a cue on music or a
                # breath before the character speaks; keeping those outer VAD
                # bounds made the translated cue appear seconds before the
                # hard subtitle. Align only exact text matches, so a fuzzy OCR
                # correction cannot unexpectedly move dialogue.
                timing_aligned = False
                matcher = SequenceMatcher(None, asr_normalized, ocr_normalized)
                text_similarity = matcher.ratio()
                is_substring = (
                    (ocr_normalized in asr_normalized or asr_normalized in ocr_normalized)
                    if ocr_normalized and asr_normalized else False
                )
                timing_is_authoritative = (
                    ocr_normalized == asr_normalized
                    or (
                        best.get("ocr_scan_mode") == "sequence"
                        and (text_similarity >= 0.50 or is_substring)
                    )
                )
                if timing_is_authoritative:
                    try:
                        old_start = float(item.get("start", 0.0) or 0.0)
                        old_end = max(old_start, float(item.get("end", old_start) or old_start))
                        ocr_start = max(0.0, float(best.get("start", old_start) or old_start))
                        ocr_end = max(ocr_start, float(best.get("end", old_end) or old_end))
                    except (TypeError, ValueError):
                        ocr_start = ocr_end = old_start = old_end = 0.0
                    if (
                        ocr_end - ocr_start >= 0.20
                        and ocr_start < old_end + cls.MAX_TIME_SLOP_SECONDS
                        and ocr_end > old_start - cls.MAX_TIME_SLOP_SECONDS
                        and (
                            abs(ocr_start - old_start) >= 0.08
                            or abs(ocr_end - old_end) >= 0.08
                        )
                    ):
                        item.setdefault("asr_start_original", old_start)
                        item.setdefault("asr_end_original", old_end)
                        item["start"] = ocr_start
                        item["end"] = ocr_end
                        if "tts_group_start" in item:
                            item["tts_group_start"] = ocr_start
                        if "tts_group_end" in item:
                            item["tts_group_end"] = ocr_end
                        item.pop("_audio_end", None)
                        item.pop("_original_end", None)
                        item["ocr_text"] = ocr_text
                        item["text_source"] = "ocr_timing_aligned"
                        item["words"] = []
                        replacement_count += 1
                        timing_aligned = True

                if ocr_normalized == asr_normalized:
                    # Persist exact two-frame agreement even when OCR timing is
                    # already close enough that no alignment was necessary.
                    # Downstream hallucination filtering needs this evidence to
                    # preserve a genuine visible one-character interjection.
                    item["ocr_text"] = ocr_text
                    item["ocr_consensus_frames"] = max(
                        2, int(best.get("ocr_consensus_frames", 0) or 0)
                    )
                    item.setdefault("text_source", "ocr_verified")

                if ocr_normalized != asr_normalized:
                    is_safe_replacement = (
                        text_similarity >= 0.25
                        or is_substring
                        or (
                            int(best.get("ocr_consensus_frames", 0) or 0) >= 2
                            and cls._is_suspicious(asr_text, family)
                        )
                    )
                    if is_safe_replacement:
                        item["asr_text_original"] = asr_text
                        item["ocr_text"] = ocr_text
                        item["text_source"] = "ocr_reconciled"
                        item["text"] = ocr_text
                        if not timing_aligned:
                            replacement_count += 1
            repaired.append(item)

        repaired, timeline_changes = cls._normalize_reconciled_timeline(repaired)
        return repaired, replacement_count + timeline_changes

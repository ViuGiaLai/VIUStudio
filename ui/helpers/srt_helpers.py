import re
from difflib import SequenceMatcher


_TIMESTAMP_PATTERN = r"\d{2}:\d{2}:\d{2},\d{3}"
_TIME_RANGE_RE = re.compile(rf"^\s*({_TIMESTAMP_PATTERN})\s*-->\s*({_TIMESTAMP_PATTERN})\s*$")


def parse_srt_to_segments(srt_text):
    is_valid, segments, _error = validate_srt_text(srt_text)
    if not is_valid:
        return []
    return segments


def normalize_subtitle_timing(segments, gap_seconds: float = 0.04):
    """Return one sorted subtitle lane without duplicate/overlapping cues."""
    ordered = []
    for source in list(segments or []):
        item = dict(source)
        try:
            item["start"] = max(0.0, float(item.get("start", 0.0)))
            item["end"] = max(item["start"], float(item.get("end", item["start"])))
        except (TypeError, ValueError):
            continue
        ordered.append(item)
    ordered.sort(key=lambda item: (item["start"], item["end"]))

    def canonical_text(item):
        return "".join(re.findall(r"\w", str(item.get("text", "")).casefold(), flags=re.UNICODE))

    deduplicated = []
    for item in ordered:
        item_text = canonical_text(item)
        duplicate = False
        for previous in reversed(deduplicated):
            overlap = min(previous["end"], item["end"]) - max(previous["start"], item["start"])
            if overlap <= 0:
                if previous["end"] <= item["start"]:
                    break
                continue
            previous_text = canonical_text(previous)
            if not item_text or not previous_text:
                continue
            shorter_duration = max(
                0.001,
                min(previous["end"] - previous["start"], item["end"] - item["start"]),
            )
            temporal_match = overlap / shorter_duration >= 0.35
            text_match = (
                item_text == previous_text
                or SequenceMatcher(None, previous_text, item_text).ratio() >= 0.92
            )
            if temporal_match and text_match:
                duplicate = True
                break
        if not duplicate:
            deduplicated.append(item)

    normalized = []
    safe_gap = max(0.0, float(gap_seconds))
    for item in deduplicated:
        if normalized and normalized[-1]["end"] > item["start"]:
            previous = normalized[-1]
            previous["end"] = max(previous["start"], item["start"] - safe_gap)
            # Timing-derived metadata belongs to the old boundary. Keeping it
            # would make the timeline stack the cleaned cue by its stale TTS
            # audio end and could leave word highlighting beyond the cue.
            previous.pop("_audio_end", None)
            previous.pop("_original_end", None)
            if "tts_group_end" in previous:
                previous["tts_group_end"] = previous["end"]
            if isinstance(previous.get("words"), list):
                trimmed_words = []
                for raw_word in previous["words"]:
                    word = dict(raw_word) if isinstance(raw_word, dict) else raw_word
                    if not isinstance(word, dict):
                        continue
                    try:
                        word_start = float(word.get("start", previous["start"]))
                        word_end = float(word.get("end", word_start))
                    except (TypeError, ValueError):
                        continue
                    if word_start >= previous["end"]:
                        continue
                    word["end"] = min(word_end, previous["end"])
                    trimmed_words.append(word)
                previous["words"] = trimmed_words
            if previous["end"] <= previous["start"]:
                normalized.pop()
        normalized.append(item)
    return expand_short_cues_into_gaps(normalized, safe_gap_seconds=safe_gap)


try:
    from app.services.segment_regroup_service import SegmentRegroupService
except ImportError:
    from services.segment_regroup_service import SegmentRegroupService

SAFE_GAP = SegmentRegroupService.SAFE_GAP
MAX_PER_NUDGE = SegmentRegroupService.MAX_PER_NUDGE
MAX_CUMULATIVE_DRIFT = SegmentRegroupService.MAX_CUMULATIVE_DRIFT
MAX_LEADING = SegmentRegroupService.MAX_LEADING
TARGET_MAX_SPEED = SegmentRegroupService.TARGET_MAX_SPEED
HARD_MAX_SPEED = SegmentRegroupService.HARD_MAX_SPEED
is_semantic_shortening_safe = SegmentRegroupService.is_semantic_shortening_safe
generate_shorten_candidates = SegmentRegroupService.generate_shorten_candidates
estimate_tts_duration = SegmentRegroupService.estimate_tts_duration
estimate_tts_speed = SegmentRegroupService.estimate_tts_speed


def compute_natural_cue_duration(text: str) -> float:
    """Compute the natural minimum duration (seconds) needed for comfortable
    speech articulation and human reading of a subtitle cue.
    """
    return SegmentRegroupService.compute_natural_cue_duration(text)


def shorten_text_for_tts(
    text: str,
    available_duration: float,
    *,
    max_words: int | None = None,
) -> str:
    """Shorten translation text when time slot is strictly constrained and cannot expand,
    allowing TTS to articulate naturally without being forced into high speedups (> 1.18x).
    """
    return SegmentRegroupService.shorten_text_for_tts(text, available_duration, max_words=max_words)


def expand_short_cues_into_gaps(
    segments,
    *,
    min_cue_duration: float = 0.8,
    safe_gap_seconds: float = 0.08,
    max_timeline_duration: float | None = None,
    video_duration: float | None = None,
):
    """Extend artificially short cues into silence gaps with strict synchrony constraints:
    1. Subtitle timeline (sub_start, sub_end, start, end) is strictly IMMUTABLE to preserve video sync.
    2. TTS window (voice_start, voice_end) is expanded into silence without cumulative ripple drift.
    3. Trailing expansion bounded by next_sub_start - safe_gap.
    4. Ripple nudge capped at MAX_PER_NUDGE (0.15s) and MAX_CUMULATIVE_DRIFT (0.20s).
    5. Leading expansion computed via available_leading = voice_start - prev_sub_end - safe_gap.
    6. Multi-level candidate shortening tested against required speed <= 1.15 (natural) or <= 1.20 (acceptable).
    7. If even shortest candidate requires speed > 1.20, marked as timing_conflict = True without truncating.
    """
    return SegmentRegroupService.expand_short_cues_into_gaps(
        segments,
        min_cue_duration=min_cue_duration,
        safe_gap_seconds=safe_gap_seconds,
        max_timeline_duration=max_timeline_duration,
        video_duration=video_duration,
    )



def align_segments_to_video_start(segments: list, first_video_start: float, offset_if_relative: bool = True) -> list:
    """Ensure subtitle segments start strictly from the first video clip on the timeline,
    skipping any intro clips/images. If the first cue starts before first_video_start
    and offset_if_relative is True, all cues are offset so that the first cue aligns to first_video_start.
    Any cue lying entirely inside the intro is dropped, and overlapping onset is clamped.
    """
    if not segments or first_video_start <= 0.05:
        return segments

    first_sub_start = float(segments[0].get("start", 0.0) or 0.0)
    # If the imported or existing subtitles were authored relative to 0:00 (i.e. start before video)
    if offset_if_relative and first_sub_start < first_video_start - 0.05:
        offset = round(first_video_start, 3)
        aligned = []
        for s in segments:
            item = dict(s)
            st = round(float(item.get("start", 0.0) or 0.0) + offset, 3)
            et = round(float(item.get("end", st + 0.1) or (st + 0.1)) + offset, 3)
            item["start"] = max(first_video_start, st)
            item["end"] = max(item["start"] + 0.05, et)
            aligned.append(item)
        segments = aligned

    # Filter out any cues that end at or before the video start,
    # and clamp any remaining cue to start >= first_video_start
    filtered = []
    for s in segments:
        item = dict(s)
        st = float(item.get("start", 0.0) or 0.0)
        et = float(item.get("end", st + 0.05) or (st + 0.05))
        if et <= first_video_start:
            continue
        if st < first_video_start:
            item["start"] = first_video_start
        item["end"] = max(item["start"] + 0.05, et)
        filtered.append(item)
    return filtered


def validate_srt_text(srt_text, expected_len=None):
    segments = []
    normalized_text = _normalize_srt_text(srt_text)
    if not normalized_text:
        return False, segments, "SRT content is empty."

    blocks = [block.strip() for block in re.split(r"\n\s*\n", normalized_text) if block.strip()]
    if not blocks:
        return False, segments, "SRT content is empty."

    for block_index, block in enumerate(blocks, start=1):
        lines = [line.rstrip() for line in block.split("\n")]
        if len(lines) < 3:
            return False, [], f"Subtitle block {block_index} is incomplete."
        if not lines[0].strip().isdigit():
            return False, [], f"Subtitle block {block_index} is missing a numeric index."

        time_match = _TIME_RANGE_RE.match(lines[1])
        if not time_match:
            return False, [], f"Subtitle block {block_index} has an invalid time range."

        try:
            start = _timestamp_to_seconds(time_match.group(1))
            end = _timestamp_to_seconds(time_match.group(2))
        except ValueError as exc:
            return False, [], f"Subtitle block {block_index} has an invalid timestamp: {exc}"

        if end < start:
            return False, [], f"Subtitle block {block_index} ends before it starts."

        text = "\n".join(lines[2:]).strip()
        if not text:
            return False, [], f"Subtitle block {block_index} is missing subtitle text."

        expected_index = str(block_index)
        if lines[0].strip() != expected_index:
            return False, [], f"Subtitle block {block_index} should use index {expected_index}."

        segments.append({"start": start, "end": end, "text": text})

    if expected_len is not None and len(segments) != int(expected_len):
        return False, [], f"SRT segment count mismatch. Expected {int(expected_len)}, got {len(segments)}."

    return True, segments, ""


def extract_subtitle_text_entries(srt_text):
    entries = []
    normalized_text = _normalize_srt_text(srt_text)
    if not normalized_text:
        return entries
    blocks = [block.strip() for block in re.split(r"\n\s*\n", normalized_text) if block.strip()]
    for block in blocks:
        lines = [line.rstrip() for line in block.splitlines()]
        if not lines:
            continue
        if len(lines) >= 3 and " --> " in lines[1]:
            text = "\n".join(lines[2:]).strip()
        elif len(lines) >= 2 and lines[0].strip().isdigit():
            text = "\n".join(lines[1:]).strip()
        else:
            text = "\n".join(lines).strip()
        entries.append(text)
    return entries


def format_timestamp(seconds):
    total_ms = int(seconds * 1000)
    ms = total_ms % 1000
    total_seconds = total_ms // 1000
    sec = total_seconds % 60
    total_minutes = total_seconds // 60
    mins = total_minutes % 60
    hrs = total_minutes // 60
    return f"{hrs:02d}:{mins:02d}:{sec:02d},{ms:03d}"


def format_segments_to_srt(segments, max_gap_ms: float = 100.0):
    lines = []
    max_gap_s = max_gap_ms / 1000.0
    for idx, seg in enumerate(segments):
        start = format_timestamp(seg["start"])
        end_s = float(seg.get("end", 0.0) or 0.0)
        if idx + 1 < len(segments):
            next_start = float(segments[idx + 1].get("start", 0.0))
            gap = next_start - end_s
            if 0 < gap <= max_gap_s:
                end_s = next_start
        end = format_timestamp(end_s)
        lines.append(f"{idx + 1}")
        lines.append(f"{start} --> {end}")
        seg_text = str(
            seg.get("final_text")
            or seg.get("text")
            or seg.get("subtitle_text")
            or seg.get("raw_translation")
            or seg.get("original_text")
            or ""
        ).strip()
        lines.append(f"{seg_text}\n")
    return "\n".join(lines)


def _timestamp_to_seconds(value):
    raw_value = str(value or "").strip()
    if not re.fullmatch(_TIMESTAMP_PATTERN, raw_value):
        raise ValueError(raw_value or "<empty>")
    value = raw_value.replace(",", ".")
    parts = value.split(":")
    if len(parts) != 3:
        raise ValueError(raw_value)
    hrs, mins, secs = parts
    return int(hrs) * 3600 + int(mins) * 60 + float(secs)


def _normalize_srt_text(srt_text):
    return str(srt_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def parse_timestamp(value) -> float | None:
    """Parse a timestamp string in various formats into seconds as a float.

    Supports:
      - 'HH:MM:SS,mmm' or 'HH:MM:SS.mmm'
      - 'MM:SS,mmm' or 'MM:SS.mmm'
      - 'SS.mmm' or 'SS,mmm' or 'SS'
      - float/int numbers directly
    Returns None if parsing fails.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return max(0.0, float(value))
    raw = str(value).strip().replace(",", ".")
    if not raw:
        return None
    parts = raw.split(":")
    try:
        if len(parts) == 3:
            h, m, s = parts
            return max(0.0, int(h) * 3600 + int(m) * 60 + float(s))
        elif len(parts) == 2:
            m, s = parts
            return max(0.0, int(m) * 60 + float(s))
        elif len(parts) == 1:
            return max(0.0, float(parts[0]))
    except (ValueError, TypeError):
        return None
    return None

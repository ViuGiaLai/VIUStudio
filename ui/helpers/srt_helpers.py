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
    return normalized


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

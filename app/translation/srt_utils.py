import re


def parse_srt(srt_text: str) -> list[dict]:
    segments = []
    if not srt_text or not srt_text.strip():
        return segments

    blocks = [b.strip() for b in srt_text.strip().split("\n\n") if b.strip()]
    for block in blocks:
        lines = [line.rstrip() for line in block.splitlines()]
        if len(lines) < 3:
            continue
        time_line = lines[1]
        if " --> " not in time_line:
            continue
        start_raw, end_raw = time_line.split(" --> ", 1)
        try:
            start = _to_seconds(start_raw)
            end = _to_seconds(end_raw)
        except (TypeError, ValueError):
            # Ignore malformed blocks instead of manufacturing a 00:00 cue.
            # A synthetic zero-timestamp subtitle shifts every downstream
            # translation/TTS decision and is much harder to diagnose.
            continue
        text = "\n".join(lines[2:]).strip()
        if not text or start < 0.0 or end <= start:
            continue
        segments.append({"start": start, "end": end, "text": text})
    return segments


def to_srt(segments: list[dict], max_gap_ms: float = 100.0) -> str:
    lines = []
    max_gap_s = max_gap_ms / 1000.0
    for idx, seg in enumerate(segments, 1):
        lines.append(str(idx))
        end_time = seg['end']
        
        # Close small gaps to next segment
        if idx < len(segments):
            next_seg = segments[idx]
            gap = next_seg['start'] - end_time
            if 0 < gap <= max_gap_s:
                end_time = next_seg['start']
        
        lines.append(f"{format_timestamp(seg['start'])} --> {format_timestamp(end_time)}")
        lines.append((seg.get("text") or seg.get("final_text") or seg.get("refined_translation") or seg.get("raw_translation") or seg.get("original_text") or "").strip())
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def clone_with_texts(segments: list[dict], texts: list[str], provider: str, polished: bool = False) -> list[dict]:
    cloned = []
    for seg, text in zip(segments, texts):
        cloned.append(
            {
                "start": seg["start"],
                "end": seg["end"],
                "text": (text or "").strip(),
                "source_text": seg.get("source_text") or seg.get("original_text") or seg.get("text", ""),
                "provider": provider,
                "polished": polished,
            }
        )
    return cloned


def format_timestamp(seconds: float) -> str:
    total_ms = int(round(float(seconds) * 1000))
    ms = total_ms % 1000
    total_seconds = total_ms // 1000
    sec = total_seconds % 60
    total_minutes = total_seconds // 60
    mins = total_minutes % 60
    hrs = total_minutes // 60
    return f"{hrs:02d}:{mins:02d}:{sec:02d},{ms:03d}"


def _to_seconds(raw: str) -> float:
    raw = raw.strip().replace(",", ".")
    parts = raw.split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid SRT timestamp: {raw!r}")
    hrs, mins, secs = parts
    hours = int(hrs)
    minutes = int(mins)
    seconds = float(secs)
    if hours < 0 or minutes < 0 or seconds < 0 or minutes >= 60 or seconds >= 60:
        raise ValueError(f"Invalid SRT timestamp: {raw!r}")
    return hours * 3600 + minutes * 60 + seconds


def split_text_batches(texts: list[str], batch_size: int) -> list[list[str]]:
    return [texts[i:i + batch_size] for i in range(0, len(texts), batch_size)]


def validate_texts(texts: list[str], expected_len: int) -> bool:
    if len(texts) != expected_len:
        return False
    if not all(isinstance(text, str) for text in texts):
        return False
    return expected_len == 0 or any(text.strip() for text in texts)


def parse_numbered_line_items(raw: str) -> list[tuple[int, str]]:
    """Parse numbered model output while retaining the original cue IDs."""
    # Strip Gemma chain-of-thought tags
    cleaned = re.sub(r"<thought>.*?</thought>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"</?think>", "", cleaned, flags=re.IGNORECASE)
    # Strip everything before first numbered line (thinking prefix)
    first_num = re.search(r"^\s*\d+\.", cleaned, re.MULTILINE)
    if first_num:
        cleaned = cleaned[first_num.start():]
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")

    items = []
    pattern = re.compile(r"^\s*(\d+)\.\s*(.*?)(?=^\s*\d+\.\s*|\Z)", re.MULTILINE | re.DOTALL)
    for match in pattern.finditer(cleaned):
        body = str(match.group(2) or "").strip()
        if not body:
            continue
        body_lines = []
        for raw_line in body.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            cleaned_line = re.sub(
                r"^(?:Assistant|Translation|Trợ lý|Dịch|Bản dịch|Tiếng Việt)\s*:\s*",
                "",
                stripped,
                flags=re.IGNORECASE,
            ).strip()
            if not cleaned_line:
                continue
            if cleaned_line.startswith(("Note:", "Here", "Sure", "OK", "Let", "I'll", "The")):
                continue
            body_lines.append(cleaned_line)
        normalized = " ".join(body_lines).strip()
        while True:
            nested = re.match(r"^\s*\d+\.\s*(.+?)\s*$", normalized)
            if not nested:
                break
            candidate = nested.group(1).strip()
            if not candidate or candidate == normalized:
                break
            normalized = candidate
        if normalized:
            items.append((int(match.group(1)), normalized))

    if items:
        return items

    fallback_items = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        cleaned_line = re.sub(
            r"^(?:Assistant|Translation|Trợ lý|Dịch|Bản dịch|Tiếng Việt)\s*:\s*",
            "",
            stripped,
            flags=re.IGNORECASE,
        ).strip()
        if not cleaned_line:
            continue
        if cleaned_line.startswith(("Note:", "Here", "Sure", "OK", "Let", "I'll", "The")):
            continue
        match = re.match(r"^\s*\d+\.\s*(.+?)\s*$", stripped)
        if match:
            candidate = match.group(1).strip()
            candidate = re.sub(
                r"^(?:Assistant|Translation|Trợ lý|Dịch|Bản dịch|Tiếng Việt)\s*:\s*",
                "",
                candidate,
                flags=re.IGNORECASE,
            ).strip()
            while True:
                nested = re.match(r"^\s*\d+\.\s*(.+?)\s*$", candidate)
                if not nested:
                    break
                inner = nested.group(1).strip()
                if not inner or inner == candidate:
                    break
                candidate = inner
            fallback_items.append((int(match.group(1)), candidate))
    return fallback_items


def parse_numbered_lines(raw: str) -> list[str]:
    """Backward-compatible text-only parser for numbered model output."""
    return [text for _number, text in parse_numbered_line_items(raw)]


def align_segments_to_video_start(segments: list[dict], first_video_start: float, offset_if_relative: bool = True) -> list[dict]:
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

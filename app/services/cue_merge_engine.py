"""Deterministic SRT cue grouping for continuous movie-recap narration.

The output of this module is *not* narration.  It is a traceable group of
source cues which the review writer later rewrites as one natural paragraph.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CueGroup:
    source_scene_id: str
    source_cue_ids: list[int]
    source_start: float
    source_end: float
    source_subtitles: list[str]
    raw_concat_text: str
    merge_trace: list[dict[str, Any]] = field(default_factory=list)
    closed_reason: str = "END_OF_INPUT"
    continued_from: str = ""


class CueMergeEngine:
    """Implements the merge rules from Movie Review Editor spec 6b."""

    GAP_THRESHOLD = 2.0
    MAX_SOURCE_DURATION = 25.0
    MAX_CHARS = 420

    _CONTINUATION_PREFIXES = (
        "và ", "nhưng ", "thế nhưng ", "dù vậy ", "sau đó ", "ngay lúc ",
        "đúng lúc ", "lúc này ", "vì vậy ", "bởi vậy ", "cuối cùng ",
    )
    _HIGH_IMPORTANCE = ("!", "bất ngờ", "hóa ra", "hoá ra", "bí mật", "chết", "giết")

    @classmethod
    def semantic_relation(cls, previous: dict[str, Any], current: dict[str, Any], gap: float) -> str:
        text = str(current.get("text", "")).strip().casefold()
        if gap > cls.GAP_THRESHOLD:
            return "NEW_BEAT"
        if text.startswith(cls._CONTINUATION_PREFIXES):
            return "CONTINUATION"
        if len(text) < 80 or any(word in text for word in ("anh", "cô", "hắn", "nó", "họ")):
            return "NEW_DETAIL"
        return "CONTINUATION"

    @classmethod
    def merge(cls, cues: list[dict[str, Any]], visual_boundaries: list[float] | None = None,
              semantic_relations: dict[tuple[int, int], str] | None = None) -> list[CueGroup]:
        rows = sorted(cues, key=lambda item: (float(item["start"]), float(item["end"]), int(item["id"])))
        if not rows:
            return []
        boundaries = sorted(float(value) for value in (visual_boundaries or []))
        groups: list[CueGroup] = []
        buffer: list[dict[str, Any]] = []
        trace: list[dict[str, Any]] = []
        continued_from = ""

        def close(reason: str) -> None:
            nonlocal buffer, trace, continued_from
            if not buffer:
                return
            groups.append(CueGroup(
                source_scene_id=str(buffer[0].get("source_scene_id") or
                                    f"SCENE-{1 + sum(1 for cut in boundaries if cut <= float(buffer[0]['start'])):04d}"),
                source_cue_ids=[int(item["id"]) for item in buffer],
                source_start=float(buffer[0]["start"]),
                source_end=float(buffer[-1]["end"]),
                source_subtitles=[str(item["text"]) for item in buffer],
                raw_concat_text=" ".join(str(item["text"]).strip() for item in buffer),
                merge_trace=list(trace), closed_reason=reason, continued_from=continued_from,
            ))
            continued_from = ""
            buffer, trace = [], []

        for cue in rows:
            if not buffer:
                buffer = [cue]
                continue
            previous = buffer[-1]
            gap = max(0.0, float(cue["start"]) - float(previous["end"]))
            crosses_scene = (
                str(previous.get("source_scene_id", "")) != str(cue.get("source_scene_id", ""))
                or any(float(previous["end"]) <= cut <= float(cue["start"]) + 0.15 for cut in boundaries)
            )
            relation = "SCENE_CHANGE" if crosses_scene else str(
                (semantic_relations or {}).get((int(previous["id"]), int(cue["id"])))
                or cls.semantic_relation(previous, cue, gap)
            ).upper()
            duration_ok = float(cue["end"]) - float(buffer[0]["start"]) <= cls.MAX_SOURCE_DURATION
            chars_ok = sum(len(str(item["text"])) for item in buffer) + len(str(cue["text"])) <= cls.MAX_CHARS
            budget_ok = duration_ok and chars_ok
            high_beat = relation == "NEW_BEAT" and (
                float(previous.get("importance", 0.0) or 0.0) >= 0.7
                or any(marker in str(previous["text"]).casefold() for marker in cls._HIGH_IMPORTANCE)
            )
            can_merge = (
                not crosses_scene and gap <= cls.GAP_THRESHOLD and budget_ok
                and relation in {"CONTINUATION", "NEW_DETAIL"} and not high_beat
            )
            if can_merge:
                trace.append({"from_cue": int(previous["id"]), "to_cue": int(cue["id"]),
                              "reason": relation, "gap_ms": int(round(gap * 1000))})
                buffer.append(cue)
                continue
            reason = "SCENE_CHANGE" if crosses_scene else ("LENGTH_BUDGET" if not budget_ok else relation)
            previous_group_id = f"N{len(groups) + 1:04d}"
            close(reason)
            continued_from = previous_group_id if reason == "LENGTH_BUDGET" else ""
            buffer = [cue]
        close("END_OF_INPUT")
        return groups

"""Quantitative C1-C6 narration continuity checks from spec v2.1."""
from __future__ import annotations

import os
import re
from difflib import SequenceMatcher
from typing import Any


def _tokens(text: str) -> str:
    return " ".join(re.findall(r"\w+", str(text or "").casefold(), flags=re.UNICODE))


class ContinuityQAService:
    def analyze(self, project: Any) -> dict[str, Any]:
        scenes = list(getattr(project, "scenes", []) or [])
        avg = sum(len(scene.source_cue_ids) for scene in scenes) / max(1, len(scenes))
        flagged: list[dict[str, Any]] = []
        for scene in scenes:
            similarity = SequenceMatcher(None, _tokens(scene.review_text), _tokens(scene.raw_concat_text)).ratio()
            if scene.review_text and scene.raw_concat_text and similarity >= 0.55:
                flagged.append({"segment_id": scene.scene_id, "issue": "C2_high_similarity",
                                "score": round(similarity, 3)})
            if scene.tts_rendered and (not scene.tts_audio_path or not os.path.isfile(scene.tts_audio_path)):
                flagged.append({"segment_id": scene.scene_id, "issue": "C3_missing_single_tts"})
            elif scene.tts_rendered and any(
                row.get("alignment") != "estimated_within_paragraph" for row in scene.narration_timings
            ):
                flagged.append({"segment_id": scene.scene_id, "issue": "C3_joined_or_legacy_tts"})
            pauses = [row for row in scene.narration_plan
                      if (int(row.get("pause_before_ms", 0) or 0) or int(row.get("pause_after_ms", 0) or 0))
                      and len(row.get("source_cue_ids", [])) == 1]
            if len(scene.source_cue_ids) > 1 and len(pauses) / len(scene.source_cue_ids) > 0.7:
                flagged.append({"segment_id": scene.scene_id, "issue": "C4_cue_shaped_pauses"})
            cut_count = sum(1 for row in scene.edit_plan if str(row.get("action", "")).upper() == "CUT")
            if len(scene.source_cue_ids) > 1 and cut_count >= len(scene.source_cue_ids) - 1:
                flagged.append({"segment_id": scene.scene_id, "issue": "C5_cue_shaped_edits"})
            if (len(scene.source_cue_ids) == 1 and scene.duration < 2.0
                    and float(scene.story_beat.get("importance", 0.0) or 0.0) < 0.7
                    and scene.closed_reason not in {"SCENE_CHANGE", "HIGH_IMPORTANCE"}):
                flagged.append({"segment_id": scene.scene_id, "issue": "C6_orphan_segment"})
        status = ("not_ready" if not scenes else
                  "blocked" if (len(scenes) > 1 and avg < 1.3) else
                  "needs_review" if (flagged or (len(scenes) > 1 and avg < 2.0)) else "ready")
        return {"avg_cues_per_segment": round(avg, 2), "flagged_segments": flagged,
                "overall_status": status}

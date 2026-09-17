"""Compile source footage onto a narration-first output clock.

Source SRT timestamps select relevant pictures; they never insert silence into
the output.  Decisions are emitted in narrative order and the output cursor is
advanced only by kept footage.
"""
from __future__ import annotations

from typing import Any

from app.services.auto_recap_engine import ShotDecision


class NarrativeTimelineCompiler:
    def __init__(self, *, min_speed: float = 0.8, max_speed: float = 1.2,
                 max_freeze: float = 4.0):
        self.min_speed = min_speed
        self.max_speed = max_speed
        self.max_freeze = max_freeze

    def compile(self, project: Any, normalize_plan) -> list[ShotDecision]:
        decisions: list[ShotDecision] = []
        output_cursor = 0.0
        for scene_index, scene in enumerate(project.scenes):
            scene.edit_output_start = output_cursor
            raw = normalize_plan(scene, scene.edit_plan)
            active = [row for row in raw if str(row.get("action", "KEEP")).upper() != "CUT"]
            if not active:
                active = [{"start": scene.start, "end": scene.end, "action": "KEEP", "speed": 1.0,
                           "freeze_duration": 0.0, "source_cue_ids": scene.source_cue_ids,
                           "reason": "Footage neo theo Narrative Segment."}]
            target = max(0.1, float(scene.tts_duration or scene.duration))
            source_total = sum(max(0.0, float(row["end"]) - float(row["start"])) for row in active)
            # Use light speed changes first. If footage is still too long, trim
            # its tail; if too short, slow it gently and only then freeze.
            speed = min(self.max_speed, max(self.min_speed, source_total / target)) if source_total else 1.0
            wanted_source = min(source_total, target * speed)
            remaining = wanted_source
            emitted: list[ShotDecision] = []
            for row in active:
                if remaining <= 0.001:
                    break
                cursor = float(row["start"])
                row_remaining = max(0.0, float(row["end"]) - cursor)
                while remaining > 0.001 and row_remaining > 0.001:
                    # Editorial shot rhythm is independent of cue boundaries.
                    duration = min(6.0, row_remaining, remaining)
                    visual_number = len(emitted)
                    emitted.append(ShotDecision(
                        shot_index=len(decisions) + visual_number, start_time=cursor, end_time=cursor + duration,
                        duration=duration, importance_score=100.0, action_type="KEEP", speed=speed,
                        zoom_scale=1.025 if visual_number % 2 == 0 else 1.0,
                        zoom_direction="in" if visual_number % 2 == 0 else "none",
                        keep_original=True, source_clip_id=f"{scene.scene_id}_visual_{visual_number+1:03d}",
                        recap_notes=f"{scene.scene_id} · narration-first · {row.get('reason', '')}",
                    ))
                    cursor += duration
                    row_remaining -= duration
                    remaining -= duration
            produced = sum(item.output_duration for item in emitted)
            shortfall = max(0.0, target - produced)
            if emitted and shortfall > 0.001:
                emitted[-1].freeze_duration = min(self.max_freeze, shortfall)
            if (emitted and scene_index == len(project.scenes) - 1
                    and (bool(scene.story_beat.get("is_ending_hook_candidate"))
                         or str(scene.story_beat.get("event_type", "")).lower() in {"danger", "twist", "climax"})):
                emitted[-1].freeze_duration = max(emitted[-1].freeze_duration, min(0.6, self.max_freeze))
            decisions.extend(emitted)
            output_cursor += sum(item.output_duration for item in emitted)
            scene.freeze_duration = emitted[-1].freeze_duration if emitted else 0.0
            scene.edit_output_end = output_cursor
        for index, decision in enumerate(decisions):
            decision.shot_index = index
        return decisions

from __future__ import annotations

from core.models import Segment


class SegmentService:
    def transcript_dicts_to_models(self, raw_segments) -> list[Segment]:
        return [
            Segment.from_transcript_dict(raw_segment, segment_id=index)
            for index, raw_segment in enumerate(raw_segments or [], start=1)
        ]

    def segment_dicts_to_models(self, segments, *, translated: bool = False) -> list[Segment]:
        models: list[Segment] = []
        for idx, seg in enumerate(segments or [], start=1):
            model = Segment.from_dict(seg, default_id=idx)
            if translated:
                translated_text = seg.get("text", "")
                model.apply_translation(translated_text, refined=bool(seg.get("polished")))
                if "words" in seg:
                    model.metadata["words"] = list(seg.get("words") or [])
                if "manual_highlights" in seg:
                    model.metadata["manual_highlights"] = list(seg.get("manual_highlights") or [])
                if "auto_highlights" in seg:
                    model.metadata["auto_highlights"] = list(seg.get("auto_highlights") or [])
            elif not model.original_text:
                model.original_text = str(seg.get("text", "") or "")
                model.status = "transcribed"
            models.append(model)
        return models

    def apply_translations(self, base_models, translated_segments) -> list[Segment]:
        models: list[Segment] = []
        base_models = base_models or []
        # An imported/edited SRT can add or remove cues.  Positional matching
        # is only safe while both lists have the same shape; otherwise use
        # the preserved cue timing to keep source text, speaker IDs, and
        # word metadata attached to the correct translated cue.
        base_by_timing = {}
        if len(base_models) != len(translated_segments or []):
            for base_model in base_models:
                key = (
                    round(float(getattr(base_model, "start", 0.0) or 0.0), 3),
                    round(float(getattr(base_model, "end", 0.0) or 0.0), 3),
                )
                base_by_timing.setdefault(key, []).append(base_model)
        for idx, seg in enumerate(translated_segments or [], start=1):
            model = Segment.from_dict(seg, default_id=idx)
            base_model = None
            if len(base_models) == len(translated_segments or []) and idx - 1 < len(base_models):
                base_model = base_models[idx - 1]
            elif base_by_timing:
                key = (
                    round(float((seg or {}).get("start", 0.0) or 0.0), 3),
                    round(float((seg or {}).get("end", 0.0) or 0.0), 3),
                )
                candidates = base_by_timing.get(key) or []
                if candidates:
                    base_model = candidates.pop(0)
            if base_model is not None:
                # Segment.from_dict treats its generic ``text`` field as an
                # original-text fallback. For translations that field is the
                # translated cue, so only an explicitly retained original
                # should win over the source model.
                explicit_original = str((seg or {}).get("original_text") or (seg or {}).get("source_text") or "").strip()
                if not explicit_original:
                    model.original_text = base_model.original_text
                source_words = base_model.metadata.get("words")
                if source_words and "words" not in seg:
                    model.metadata["words"] = list(source_words)
                source_speaker = str(base_model.metadata.get("speaker", "") or "").strip()
                if source_speaker and "speaker" not in seg:
                    model.metadata["speaker"] = source_speaker
                source_highlights = base_model.metadata.get("manual_highlights")
                if source_highlights and "manual_highlights" not in seg:
                    model.metadata["manual_highlights"] = list(source_highlights)
                source_auto_highlights = base_model.metadata.get("auto_highlights")
                if source_auto_highlights and "auto_highlights" not in seg:
                    model.metadata["auto_highlights"] = list(source_auto_highlights)
                source_voice_speed = getattr(base_model, "voice_speed", 1.0)
                if source_voice_speed != 1.0 and "voice_speed" not in seg:
                    model.voice_speed = source_voice_speed
            translated_text = seg.get("text", "")
            model.apply_translation(translated_text, refined=bool(seg.get("polished")))
            model.metadata["translation_provider"] = seg.get("provider", "")
            model.metadata["source_text"] = seg.get("source_text", "")
            if "words" in seg:
                model.metadata["words"] = list(seg.get("words") or [])
            if "manual_highlights" in seg:
                model.metadata["manual_highlights"] = list(seg.get("manual_highlights") or [])
            if "auto_highlights" in seg:
                model.metadata["auto_highlights"] = list(seg.get("auto_highlights") or [])
            for key in ("tts_group_id", "tts_group_start", "tts_group_end"):
                if key in seg:
                    model.metadata[key] = seg.get(key)
            models.append(model)
        return self.expand_short_segments_into_gaps(models)

    def expand_short_segments_into_gaps(self, models: list[Segment], safe_gap_seconds: float = 0.08) -> list[Segment]:
        try:
            from app.services.segment_regroup_service import SegmentRegroupService
        except ImportError:
            from services.segment_regroup_service import SegmentRegroupService

        if not models:
            return []

        raw_cues = []
        for model in models:
            s_start = float(getattr(model, "start", 0.0) or 0.0)
            s_end = float(getattr(model, "end", s_start) or s_start)
            cue = {
                "id": getattr(model, "id", 0),
                "start": s_start,
                "end": s_end,
                "sub_start": float(model.metadata.get("sub_start", s_start)),
                "sub_end": float(model.metadata.get("sub_end", s_end)),
                "voice_start": float(model.metadata.get("voice_start", s_start)),
                "voice_end": float(model.metadata.get("voice_end", s_end)),
                "final_text": getattr(model, "final_text", ""),
                "tts_text": getattr(model, "tts_text", ""),
                "dubbing_vi": getattr(model, "tts_text", "") or getattr(model, "final_text", ""),
                "raw_translation": getattr(model, "raw_translation", ""),
                "original_text": getattr(model, "original_text", ""),
                "text": getattr(model, "subtitle_text", ""),
            }
            raw_cues.append(cue)

        expanded = SegmentRegroupService.expand_short_cues_into_gaps(raw_cues, safe_gap_seconds=safe_gap_seconds)
        for model, exp in zip(models, expanded):
            # Subtitle timeline is strictly IMMUTABLE
            model.start = exp["sub_start"]
            model.end = exp["sub_end"]
            model.tts_text = exp.get("tts_text", model.tts_text)
            model.metadata["sub_start"] = exp["sub_start"]
            model.metadata["sub_end"] = exp["sub_end"]
            model.metadata["voice_start"] = exp["voice_start"]
            model.metadata["voice_end"] = exp["voice_end"]
            model.metadata["_audio_start"] = exp["voice_start"]
            model.metadata["_audio_end"] = exp["voice_end"]
            model.metadata["fit_quality"] = exp.get("fit_quality", "natural")
            model.metadata["timing_conflict"] = exp.get("timing_conflict", False)
            if "overflow_seconds" in exp:
                model.metadata["overflow_seconds"] = exp["overflow_seconds"]

        return models

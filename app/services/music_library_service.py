from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Callable


class MusicLibraryService:
    """Analyze a local music folder once, cache DSP metadata and match Scenes."""

    AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}

    @staticmethod
    def _fingerprint(path: str) -> str:
        stat = os.stat(path)
        raw = f"{os.path.abspath(path)}|{stat.st_size}|{stat.st_mtime_ns}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _features(y, sr: int) -> dict[str, Any]:
        import librosa
        import numpy as np

        if y is None or len(y) < 32:
            return {"energy": 0, "tension": 0, "bpm": 0.0, "vocal": False, "vocal_probability": 0.0, "mood": ["neutral"]}
        rms = float(np.mean(librosa.feature.rms(y=y)))
        db = 20.0 * math.log10(max(1e-7, rms))
        energy = int(round(max(0.0, min(100.0, (db + 48.0) / 36.0 * 100.0))))
        centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr))) / max(1.0, sr / 2.0)
        zcr = float(np.mean(librosa.feature.zero_crossing_rate(y)))
        onset = librosa.onset.onset_strength(y=y, sr=sr)
        onset_level = float(np.percentile(onset, 75)) if len(onset) else 0.0
        onset_score = max(0.0, min(1.0, onset_level / 3.0))
        tension = int(round(max(0.0, min(100.0, energy * 0.5 + centroid * 90.0 * 0.3 + onset_score * 100.0 * 0.2))))
        tempo_value, _beats = librosa.beat.beat_track(y=y, sr=sr)
        tempo = float(np.asarray(tempo_value).reshape(-1)[0]) if np.asarray(tempo_value).size else 0.0
        harmonic, percussive = librosa.effects.hpss(y)
        harmonic_ratio = float(np.mean(np.abs(harmonic))) / max(1e-7, float(np.mean(np.abs(y))))
        # This is an inexpensive signal heuristic, not source separation. It
        # is intentionally conservative so uncertain tracks are penalized by
        # the matcher instead of being declared vocal with false confidence.
        vocal_probability = max(0.0, min(1.0, (harmonic_ratio - 0.55) * 0.9 + max(0.0, 0.08 - zcr) * 2.0))
        vocal = vocal_probability >= 0.62
        if tension >= 72 and energy >= 68:
            mood = ["action", "danger", "tension"]
        elif tension >= 65:
            mood = ["dark", "suspense", "mysterious"]
        elif energy >= 62:
            mood = ["adventure", "positive", "energetic"]
        elif energy <= 35 and tension <= 38:
            mood = ["calm", "emotional", "neutral"]
        elif tension >= 48:
            mood = ["dramatic", "mysterious", "tension"]
        else:
            mood = ["neutral", "emotional", "adventure"]
        return {
            "energy": energy,
            "tension": tension,
            "bpm": round(tempo, 1),
            "vocal": vocal,
            "vocal_probability": round(vocal_probability, 3),
            "mood": mood,
        }

    def analyze_track(self, path: str) -> dict[str, Any]:
        import librosa

        duration = float(librosa.get_duration(path=path) or 0.0)
        # Analyze at most three minutes; segment metadata still covers the
        # useful musical progression without decoding very long files fully.
        y, sr = librosa.load(path, sr=16000, mono=True, duration=min(180.0, duration or 180.0))
        metadata = self._features(y, sr)
        segments = []
        window_seconds = 30.0
        samples = int(window_seconds * sr)
        for index, offset in enumerate(range(0, len(y), samples)):
            chunk = y[offset:offset + samples]
            if len(chunk) < sr * 3:
                continue
            item = self._features(chunk, sr)
            item.update({"start": round(index * window_seconds, 3), "end": round(min(len(y) / sr, (index + 1) * window_seconds), 3)})
            segments.append(item)
        metadata.update({
            "track": os.path.basename(path),
            "path": os.path.abspath(path),
            "duration": round(duration, 3),
            "fingerprint": self._fingerprint(path),
            "segments": segments,
        })
        return metadata

    def analyze_library(
        self,
        folder: str,
        output_path: str,
        progress: Callable[[int, int, str], None] | None = None,
    ) -> dict[str, Any]:
        files = sorted(
            str(path) for path in Path(folder).rglob("*")
            if path.is_file() and path.suffix.lower() in self.AUDIO_EXTENSIONS
        )
        old = self.load(output_path)
        cached = {item.get("fingerprint"): item for item in old.get("tracks", []) if isinstance(item, dict)}
        tracks = []
        for number, path in enumerate(files, start=1):
            fingerprint = self._fingerprint(path)
            item = cached.get(fingerprint)
            if item is None:
                item = self.analyze_track(path)
            tracks.append(item)
            if progress:
                progress(number, len(files), os.path.basename(path))
        payload = {"version": 1, "folder": os.path.abspath(folder), "tracks": tracks}
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        temporary = f"{output_path}.tmp"
        Path(temporary).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, output_path)
        return payload

    @staticmethod
    def load(path: str) -> dict[str, Any]:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {"tracks": []}
        except (OSError, ValueError):
            return {"tracks": []}

    @staticmethod
    def scene_profile(scene) -> dict[str, Any]:
        tone = str(getattr(scene, "tone", "NEUTRAL") or "NEUTRAL").upper()
        tone_profiles = {
            "PLAYFUL": (["positive", "playful", "adventure"], 58, 22),
            "TENSE": (["tension", "danger", "dark"], 74, 88),
            "SAD": (["emotional", "sad", "calm"], 30, 42),
            "EPIC": (["epic", "action", "adventure"], 88, 78),
            "TWIST": (["mysterious", "suspense", "tension"], 64, 84),
        }
        if tone in tone_profiles:
            mood, energy, tension = tone_profiles[tone]
            return {"mood": mood, "energy": energy, "tension": tension, "tone": tone}
        text = " ".join([
            str(getattr(scene, "review_text", "") or ""),
            " ".join(str(value) for value in (getattr(scene, "story_beat", {}) or {}).values()),
        ]).casefold()
        danger = ("tang thi", "quái vật", "nguy cấp", "đe dọa", "cấm khu", "diệt vong", "chết", "truy đuổi")
        action = ("chạy", "chiến", "xông", "đuổi", "ném", "tấn công")
        emotional = ("hối hận", "khuất phục", "cầu xin", "bị thương", "sợ hãi")
        mysterious = ("bí ẩn", "hệ thống", "tu tiên", "phong ấn", "khổng lồ")
        if any(word in text for word in danger):
            mood, energy, tension = ["danger", "dark", "tension"], 78, 88
        elif any(word in text for word in action):
            mood, energy, tension = ["action", "tension", "adventure"], 85, 76
        elif any(word in text for word in emotional):
            mood, energy, tension = ["emotional", "dramatic"], 45, 58
        elif any(word in text for word in mysterious):
            mood, energy, tension = ["mysterious", "adventure"], 55, 52
        else:
            mood, energy, tension = ["neutral", "calm"], 35, 30
        return {"mood": mood, "energy": energy, "tension": tension, "tone": tone}

    def match_scene(self, scene, library: dict[str, Any], previous_track: str = "") -> dict[str, Any]:
        tracks = [item for item in library.get("tracks", []) if isinstance(item, dict) and os.path.isfile(str(item.get("path", "")))]
        profile = self.scene_profile(scene)
        narration = float(getattr(scene, "tts_duration", 0.0) or 0.0)
        available = max(0.1, float(getattr(scene, "duration", 0.0) or 0.0))
        # Dense narration or a tiny bridge is often stronger without music.
        if not tracks or available < 3.0 or narration / available >= 0.82:
            return {"track": "NONE", "reason": "Cảnh ngắn hoặc narration dày; giữ khoảng thở.", **profile}
        best = None
        candidates = []
        for track in tracks:
            variants = track.get("segments", []) or [track]
            for segment in variants:
                mood_overlap = len(set(profile["mood"]) & set(segment.get("mood", [])))
                score = 0.45 * min(1.0, mood_overlap / 2.0)
                score += 0.25 * (1.0 - abs(profile["energy"] - float(segment.get("energy", 50))) / 100.0)
                score += 0.25 * (1.0 - abs(profile["tension"] - float(segment.get("tension", 50))) / 100.0)
                score += 0.05 if track.get("path") == previous_track else 0.0
                score -= 0.25 * float(track.get("vocal_probability", 1.0 if track.get("vocal") else 0.0) or 0.0)
                candidate = (score, track, segment)
                candidates.append(candidate)
                if best is None or score > best[0]:
                    best = candidate
        if best is None or best[0] < 0.43:
            return {"track": "NONE", "reason": "Không có bài đủ phù hợp.", **profile}
        score, track, segment = best
        return {
            "track": track["path"],
            "track_name": track.get("track", os.path.basename(track["path"])),
            "score": round(float(score), 3),
            "start": float(segment.get("start", 0.0) or 0.0),
            "duration": available,
            "volume_db": -18.0,
            "vocal": bool(track.get("vocal", False)),
            "vocal_probability": float(track.get("vocal_probability", 0.0) or 0.0),
            "mood": profile["mood"],
            "energy": profile["energy"],
            "tension": profile["tension"],
            "reason": "Khớp mood/energy/tension; ưu tiên instrumental và tính liên tục.",
            "top_candidates": [
                {"track": item[1].get("track"), "score": round(float(item[0]), 3)}
                for item in sorted(candidates, key=lambda value: value[0], reverse=True)[:5]
            ],
        }

    def plan_project(self, project, library: dict[str, Any]) -> list[dict[str, Any]]:
        plans = []
        previous = ""
        for scene in project.scenes:
            plan = self.match_scene(scene, library, previous)
            scene.mood = list(plan.get("mood", []))
            scene.energy = int(plan.get("energy", 0) or 0)
            scene.tension = int(plan.get("tension", 0) or 0)
            scene.music = plan
            if plan.get("track") not in {"", "NONE", None}:
                previous = str(plan["track"])
            plans.append(plan)
        return plans

    @staticmethod
    def render_music_bed(project, output_path: str, total_duration: float) -> str:
        from pydub import AudioSegment
        from app.services.auto_recap_engine import AutoRecapEngine

        ffmpeg = AutoRecapEngine._media_tool_path("ffmpeg")
        AudioSegment.converter = ffmpeg
        bed = AudioSegment.silent(duration=max(1, int(round(total_duration * 1000))), frame_rate=44100).set_channels(2)
        for scene in project.scenes:
            plan = getattr(scene, "music", {}) or {}
            track_path = str(plan.get("track", "") or "")
            if not track_path or track_path == "NONE" or not os.path.isfile(track_path):
                continue
            start_ms = max(0, int(round(scene.edit_output_start * 1000)))
            planned_duration = float(plan.get("duration", scene.duration) or scene.duration)
            edited_duration = max(0.0, float(scene.edit_output_end or 0.0) - float(scene.edit_output_start or 0.0))
            # A source-time music selection can outlast a compacted recap Scene.
            # Cap it to the output EDL so BGM from an earlier Scene cannot spill
            # across a cut and mask the next mood transition.
            if edited_duration > 0.0:
                planned_duration = min(planned_duration, edited_duration)
            duration_ms = max(500, int(round(planned_duration * 1000)))
            source_offset = max(0, int(round(float(plan.get("start", 0.0) or 0.0) * 1000)))
            source = AudioSegment.from_file(track_path)[source_offset:]
            if not source:
                continue
            repeats = max(1, math.ceil(duration_ms / len(source)))
            clip = (source * repeats)[:duration_ms]
            clip = clip + float(plan.get("volume_db", -18.0) or -18.0)
            fade = min(700, max(100, duration_ms // 4))
            clip = clip.fade_in(fade).fade_out(fade)
            bed = bed.overlay(clip, position=start_ms)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        bed.export(output_path, format="wav")
        return output_path

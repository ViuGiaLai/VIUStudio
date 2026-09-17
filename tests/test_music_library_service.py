import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "app"), str(ROOT)]

from app.services.movie_review_service import MovieReviewScene
from app.services.music_library_service import MusicLibraryService


def _scene(text="Tang thi đang truy đuổi.", duration=10.0, tts=3.0):
    return MovieReviewScene(
        "SCENE-0001", 0.0, duration, [1, 2], ["a", "b"],
        review_text=text, tts_duration=tts,
    )


def test_music_analysis_is_cached_by_file_fingerprint(tmp_path):
    folder = tmp_path / "mymusic"
    folder.mkdir()
    track = folder / "track.mp3"
    track.write_bytes(b"audio")
    output = tmp_path / "music_library.json"
    service = MusicLibraryService()
    metadata = {
        "track": track.name, "path": str(track), "duration": 30,
        "fingerprint": service._fingerprint(str(track)), "segments": [],
        "mood": ["dark"], "energy": 70, "tension": 80,
        "bpm": 120, "vocal": False, "vocal_probability": 0,
    }
    with patch.object(service, "analyze_track", return_value=metadata) as analyze:
        service.analyze_library(str(folder), str(output))
        service.analyze_library(str(folder), str(output))
    assert analyze.call_count == 1


def test_scene_matching_can_choose_track_or_none(tmp_path):
    track = tmp_path / "dark.mp3"
    track.write_bytes(b"audio")
    library = {"tracks": [{
        "track": track.name, "path": str(track), "mood": ["danger", "dark", "tension"],
        "energy": 80, "tension": 90, "vocal": False, "vocal_probability": 0,
        "segments": [{"start": 30, "end": 60, "mood": ["danger", "tension"], "energy": 82, "tension": 91}],
    }]}
    service = MusicLibraryService()
    selected = service.match_scene(_scene(), library)
    assert selected["track"] == str(track)
    assert selected["start"] == 30
    assert selected["top_candidates"]
    assert selected["vocal"] is False

    none = service.match_scene(_scene(duration=2.0, tts=1.8), library)
    assert none["track"] == "NONE"

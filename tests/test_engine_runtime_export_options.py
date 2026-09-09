import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "app")]

from app.services.engine_runtime import EngineRuntime


class _RecordingFFmpeg:
    def __init__(self):
        self.calls = []

    def embed_subtitles(self, *args, **kwargs):
        self.calls.append(("srt", args, kwargs))
        return True

    def embed_ass_subtitles(self, *args, **kwargs):
        self.calls.append(("ass", args, kwargs))
        return True


def test_engine_runtime_forwards_export_quality_options():
    runtime = EngineRuntime()
    adapter = _RecordingFFmpeg()
    runtime._instances["ffmpeg"] = adapter

    assert runtime.embed_subtitles(
        "input.mp4", "caption.srt", "output.mp4",
        export_preset="fast", video_bitrate_kbps=2400,
    )
    assert runtime.embed_ass_subtitles(
        "input.mp4", "caption.ass", "output.mp4",
        export_preset="max", video_bitrate_kbps=6000,
    )

    assert adapter.calls[0][2]["export_preset"] == "fast"
    assert adapter.calls[0][2]["video_bitrate_kbps"] == 2400
    assert adapter.calls[1][2]["export_preset"] == "max"
    assert adapter.calls[1][2]["video_bitrate_kbps"] == 6000

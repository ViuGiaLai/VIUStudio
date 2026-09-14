import json
import os
import subprocess
import sys
from unittest.mock import patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
from app.runtime_paths import bin_path, subprocess_hidden_kwargs
from app.services.timeline_sequence_export import _validate_playable_output, export_timeline_sequence


@pytest.mark.parametrize("failure", ["no_frames", "short_video", "decode_error"])
def test_rejects_unplayable_video(tmp_path, failure):
    output = tmp_path / "video.mp4"
    output.write_bytes(b"placeholder")
    metadata = {
        "format": {"duration": "10"},
        "streams": [
            {"codec_type": "video", "width": 320, "height": 180,
             "duration": "1" if failure == "short_video" else "10"},
            {"codec_type": "audio"},
        ],
    }
    probe = subprocess.CompletedProcess([], 0, json.dumps(metadata), "")
    decode = subprocess.CompletedProcess(
        [], 1 if failure == "decode_error" else 0, "# header only\n", ""
    )
    with patch("app.services.timeline_sequence_export.subprocess.run", side_effect=[probe, decode]):
        with pytest.raises(RuntimeError):
            _validate_playable_output(str(output), 10.0)


def test_single_source_export_decodes_at_both_ends(tmp_path):
    ffmpeg = str(bin_path("ffmpeg", "ffmpeg.exe"))
    if not os.path.isfile(ffmpeg):
        pytest.skip("Bundled FFmpeg unavailable")
    source = tmp_path / "source.mp4"
    subprocess.run(
        [ffmpeg, "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=24:d=3",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)],
        check=True, capture_output=True, timeout=30, **subprocess_hidden_kwargs(),
    )
    output = tmp_path / "output.mp4"
    export_timeline_sequence(
        [{"source": str(source), "source_duration": 3.0}], str(output), output_fps=24,
    )
    _validate_playable_output(str(output), 3.0)
    assert not list(tmp_path.glob("*.partial.mp4"))

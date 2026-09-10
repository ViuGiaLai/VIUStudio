import os
import subprocess
import sys
import tempfile
import unittest
import wave
from array import array
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "app")]

from app.runtime_paths import bin_path, subprocess_hidden_kwargs
from app.workflows.export_workflow import ExportWorkflow


class ExportAudioSyncTests(unittest.TestCase):
    def test_fast_mp4_mux_does_not_shift_replacement_voice(self):
        ffmpeg = bin_path("ffmpeg", "ffmpeg.exe")
        if not os.path.isfile(ffmpeg):
            self.skipTest("Bundled FFmpeg is unavailable")
        kwargs = subprocess_hidden_kwargs()
        with tempfile.TemporaryDirectory() as folder:
            video = os.path.join(folder, "source.mp4")
            voice = os.path.join(folder, "voice.wav")
            output = os.path.join(folder, "output.mp4")
            decoded = os.path.join(folder, "decoded.wav")
            subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                 "color=black:s=160x90:r=10:d=3", "-c:v", "libx264", "-pix_fmt", "yuv420p", video],
                check=True, **kwargs,
            )
            subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                 "sine=frequency=440:duration=1:sample_rate=16000", "-af", "adelay=1000",
                 "-c:a", "pcm_s16le", voice],
                check=True, **kwargs,
            )

            ExportWorkflow(str(ROOT))._export_single_clip_stream_copy(
                clip={"source": video, "source_start": 0.0, "source_duration": 3.0},
                output_path=output, mode="voice", audio_path=voice,
            )
            subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", output,
                 "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", decoded],
                check=True, **kwargs,
            )
            with wave.open(decoded, "rb") as stream:
                samples = stream.readframes(stream.getnframes())
            block_frames = 160
            first_sound = None
            for offset in range(0, len(samples), block_frames * 2):
                block = array("h")
                block.frombytes(samples[offset:offset + block_frames * 2])
                rms = (sum(value * value for value in block) / max(1, len(block))) ** 0.5
                if rms > 100:
                    first_sound = offset / 2 / 16000
                    break
            self.assertIsNotNone(first_sound)
            self.assertAlmostEqual(first_sound, 1.0, delta=0.03)


if __name__ == "__main__":
    unittest.main()

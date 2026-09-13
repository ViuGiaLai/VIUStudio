import os
import subprocess
import sys
import tempfile
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for entry in (ROOT, os.path.join(ROOT, "app"), os.path.join(ROOT, "ui")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from app.workflows.export_workflow import ExportWorkflow
from app.runtime_paths import bin_path
from app.video_processor import _build_logo_overlay_command, embed_ass_subtitles


class _OnePassEngine:
    def __init__(self):
        self.render_calls = []
        self.mux_calls = []

    def get_video_dimensions(self, _path):
        return 320, 180

    def embed_ass_subtitles(self, video_path, ass_path, output_path, **kwargs):
        self.render_calls.append((video_path, ass_path, output_path, dict(kwargs)))
        with open(output_path, "wb") as handle:
            handle.write(b"rendered")
        return True

    def mux_audio_for_preview(self, *args, **kwargs):
        self.mux_calls.append((args, kwargs))
        raise AssertionError("both-mode export must not create an intermediate mux")


class ExportOnePassTests(unittest.TestCase):
    def test_logo_graph_keeps_external_audio_outside_video_input_slots(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            logo = os.path.join(temp_dir, "logo.png")
            audio = os.path.join(temp_dir, "dub.wav")
            for path in (logo, audio):
                with open(path, "wb") as handle:
                    handle.write(b"placeholder")

            command = _build_logo_overlay_command(
                ffmpeg="ffmpeg",
                video_path="source.mp4",
                ass_path="subtitle.ass",
                output_path="final.mp4",
                logo_layers=[{"source": logo, "x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2}],
                blur_region=None,
                mask_regions=[],
                video_w=320,
                video_h=180,
                scale_chain="",
                blur_chain="",
                mask_chain="",
                output_fps=None,
                video_filter_state={},
                audio_input_path=audio,
            )

            graph = command[command.index("-filter_complex") + 1]
            self.assertIn("[1:v]format=rgba", graph)
            maps = [command[index + 1] for index, value in enumerate(command[:-1]) if value == "-map"]
            self.assertIn("2:a:0", maps)
            self.assertIn("-shortest", command)

    def test_both_mode_renders_source_and_external_audio_in_one_pass(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video = os.path.join(temp_dir, "source.mp4")
            audio = os.path.join(temp_dir, "mix.wav")
            ass = os.path.join(temp_dir, "live_preview_test.ass")
            output = os.path.join(temp_dir, "final.mp4")
            for path, payload in ((video, b"video"), (audio, b"audio")):
                with open(path, "wb") as handle:
                    handle.write(payload)
            with open(ass, "w", encoding="utf-8") as handle:
                handle.write("[Script Info]\nPlayResX: 320\nPlayResY: 180\n")

            workflow = ExportWorkflow(temp_dir)
            engine = _OnePassEngine()
            workflow.engine_runtime = engine

            result = workflow.run(
                video_path=video,
                output_path=output,
                mode="both",
                ass_path=ass,
                audio_path=audio,
                subtitle_style={},
                timeline_clips=[],
                anti_duplicate_enabled=False,
            )

            self.assertEqual(result, output)
            self.assertEqual(engine.mux_calls, [])
            self.assertEqual(len(engine.render_calls), 1)
            render_video, _render_ass, _render_output, kwargs = engine.render_calls[0]
            self.assertEqual(render_video, video)
            self.assertEqual(kwargs["audio_input_path"], audio)

    def test_voice_anti_duplicate_uses_render_path_instead_of_plain_mux(self):
        from app.anti_duplicate import AntiDuplicateSettings

        with tempfile.TemporaryDirectory() as temp_dir:
            video = os.path.join(temp_dir, "source.mp4")
            audio = os.path.join(temp_dir, "mix.wav")
            output = os.path.join(temp_dir, "final.mp4")
            for path, payload in ((video, b"video"), (audio, b"audio")):
                with open(path, "wb") as handle:
                    handle.write(payload)

            workflow = ExportWorkflow(temp_dir)
            engine = _OnePassEngine()
            workflow.engine_runtime = engine
            settings = AntiDuplicateSettings(enabled=True, continuous_mode=True)

            result = workflow.run(
                video_path=video,
                output_path=output,
                mode="voice",
                audio_path=audio,
                subtitle_style={},
                timeline_clips=[],
                anti_duplicate_enabled=True,
                anti_duplicate_settings=settings,
            )

            self.assertEqual(result, output)
            self.assertEqual(engine.mux_calls, [])
            self.assertEqual(len(engine.render_calls), 1)
            _video, _ass, _output, kwargs = engine.render_calls[0]
            self.assertEqual(kwargs["audio_input_path"], audio)
            self.assertTrue(kwargs["anti_duplicate_settings"].enabled)

    def test_ffmpeg_one_pass_replaces_audio_and_stops_at_shorter_track(self):
        ffmpeg = str(bin_path("ffmpeg", "ffmpeg.exe"))
        ffprobe = str(bin_path("ffmpeg", "ffprobe.exe"))
        if not os.path.isfile(ffmpeg) or not os.path.isfile(ffprobe):
            self.skipTest("Bundled FFmpeg is unavailable")

        with tempfile.TemporaryDirectory() as temp_dir:
            video = os.path.join(temp_dir, "source.mp4")
            audio = os.path.join(temp_dir, "dub.wav")
            ass = os.path.join(temp_dir, "subtitle.ass")
            output = os.path.join(temp_dir, "final.mp4")
            subprocess.run(
                [
                    ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=blue:s=320x180:r=24:d=2",
                    "-f", "lavfi", "-i", "sine=frequency=220:duration=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", video,
                ],
                check=True,
            )
            subprocess.run(
                [
                    ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "sine=frequency=880:duration=1",
                    "-c:a", "pcm_s16le", audio,
                ],
                check=True,
            )
            with open(ass, "w", encoding="utf-8") as handle:
                handle.write(
                    "[Script Info]\nScriptType: v4.00+\nPlayResX: 320\nPlayResY: 180\n\n"
                    "[V4+ Styles]\n"
                    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
                    "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
                    "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
                    "MarginR, MarginV, Encoding\n"
                    "Style: Default,Arial,20,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,"
                    "0,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1\n\n"
                    "[Events]\n"
                    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
                    "Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,One pass\n"
                )

            self.assertTrue(
                embed_ass_subtitles(
                    video,
                    ass,
                    output,
                    audio_input_path=audio,
                    export_preset="fast",
                    video_bitrate_kbps=1000,
                )
            )
            probe = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", output],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertLess(float(probe.stdout.strip()), 1.15)


if __name__ == "__main__":
    unittest.main()

import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Ensure app and ui packages are importable
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_DIR = os.path.join(ROOT_DIR, "app")
UI_DIR = os.path.join(ROOT_DIR, "ui")
for p in [ROOT_DIR, APP_DIR, UI_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from app.core.models.progress import ProgressEvent, MonotonicProgressTracker
from app.runtime_paths import sanitize_ffmpeg_diagnostics
from app.video_processor import build_export_h264_encoder_args, run_ffmpeg_with_progress
from ui.utils.progress_protocol import format_duration_clock


class TestProgressCore:
    def test_ffmpeg_illegal_icc_diagnostics_are_collapsed(self):
        raw = "[aac @ 1] illegal icc\n" * 20 + "real decode failure"
        cleaned = sanitize_ffmpeg_diagnostics(raw)
        assert "illegal icc" not in cleaned.lower()
        assert "real decode failure" in cleaned

    def test_progress_event_model(self):
        event = ProgressEvent(
            workflow="test_workflow",
            stage="transcribe",
            substage="chunk",
            percent=45,
            message="Transcribing chunk 3/10",
            current=3.0,
            total=10.0,
        )
        assert event.percent == 45
        assert str(event) == "Transcribing chunk 3/10"
        d = event.to_dict()
        assert d["workflow"] == "test_workflow"
        assert d["stage"] == "transcribe"
        assert d["current"] == 3.0
        assert d["total"] == 10.0

    def test_monotonic_tracker(self):
        tracker = MonotonicProgressTracker("render")
        events = []
        tracker.add_callback(lambda e: events.append(e))

        e1 = tracker.update(10.0, 100.0, stage="encoding", message="Starting")
        assert e1.percent == 10
        assert tracker.current_percent == 10

        # Non-monotonic drop should be suppressed
        e2 = tracker.update(8.0, 100.0, stage="encoding", message="Fluctuation")
        assert e2.percent == 10
        assert tracker.current_percent == 10

        # Increase works
        e3 = tracker.update(25.0, 100.0, stage="encoding", message="Quarter done")
        assert e3.percent == 25
        assert tracker.current_percent == 25

        # Complete
        e4 = tracker.complete("Done")
        assert e4.percent == 100
        assert len(events) == 4

    def test_format_duration_clock(self):
        assert format_duration_clock(45) == "00:45"
        assert format_duration_clock(125) == "02:05"
        assert format_duration_clock(3665) == "1:01:05"


class TestFFmpegProgressAndCancellation:
    @patch("app.video_processor._ffmpeg_supports_encoder", return_value=False)
    def test_export_profiles_use_speed_and_requested_bitrate(self, _mock_encoder):
        fast = build_export_h264_encoder_args("ffmpeg", "fast", 4000)
        balanced = build_export_h264_encoder_args("ffmpeg", "balanced", 2000)
        maximum = build_export_h264_encoder_args("ffmpeg", "max", 0)

        assert fast[:4] == ["-c:v", "libx264", "-preset", "ultrafast"]
        assert ["-b:v", "4000k"] == fast[4:6]
        assert "veryfast" in balanced
        assert "medium" in maximum
        assert ["-crf", "18"] == maximum[4:6]

    @patch("subprocess.Popen")
    def test_ffmpeg_progress_parsing(self, mock_popen):
        # Simulate FFmpeg -progress output
        mock_proc = MagicMock()
        mock_proc.stdout = iter([
            "out_time_ms=10000000\n",   # 10 seconds
            "progress=continue\n",
            "out_time_ms=20000000\n",   # 20 seconds
            "progress=continue\n",
            "out_time_ms=30000000\n",   # 30 seconds
            "progress=end\n",
        ])
        mock_proc.stderr = iter([])
        mock_proc.poll.return_value = 0
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        events = []
        ok, stdout, stderr = run_ffmpeg_with_progress(
            ["ffmpeg", "-i", "input.mp4", "output.mp4"],
            total_duration_seconds=30.0,
            progress_callback=lambda ev: events.append(ev),
        )
        assert ok is True
        assert len(events) >= 3
        assert events[-1].percent == 100

    @patch("subprocess.Popen")
    def test_ffmpeg_cancellation(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.stdout = iter([
            "out_time_ms=5000000\n",
            "progress=continue\n",
            "out_time_ms=10000000\n",
            "progress=continue\n",
            "out_time_ms=15000000\n",
            "progress=continue\n",
        ])
        mock_proc.stderr = iter([])
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        cancelled = False
        def check_cancel():
            return cancelled

        def on_prog(ev):
            nonlocal cancelled
            if ev.percent and ev.percent >= 20:
                cancelled = True

        with pytest.raises(InterruptedError):
            run_ffmpeg_with_progress(
                ["ffmpeg", "-i", "input.mp4", "output.mp4"],
                total_duration_seconds=30.0,
                progress_callback=on_prog,
                cancellation_check=check_cancel,
            )
        assert mock_proc.terminate.called or mock_proc.kill.called


class TestTTSAndTranslationProgressProtocol:
    def test_voice_workflow_cancellation(self, tmp_path):
        from app.workflows.voice_workflow import VoiceWorkflow

        wf = VoiceWorkflow(str(tmp_path))
        with pytest.raises(InterruptedError):
            wf.run(
                segments=[{"start": 0.0, "end": 2.0, "text": "Hello world"}],
                output_dir=str(tmp_path),
                cancellation_check=lambda: True,
            )

    def test_translation_orchestrator_cancellation(self):
        from app.translation.orchestrator import TranslationOrchestrator

        orch = TranslationOrchestrator()
        with pytest.raises(InterruptedError):
            orch.translate_segments(
                segments=[{"text": "Hello", "start": 0, "end": 1}],
                src_lang="en",
                target_lang="vi",
                cancellation_check=lambda: True,
            )


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestUIProgressComponents:
    def test_pipeline_progress_dialog_features(self, qapp):
        from ui.widgets.progress_dialog import PipelineProgressDialog

        dialog = PipelineProgressDialog()
        dialog.show()
        dialog.add_step("step1", "Speech Recognition")
        dialog.add_step("step2", "AI Translation")
        assert "step1" in dialog.steps
        assert "step2" in dialog.steps

        dialog.start_step("step1")
        assert dialog.steps["step1"].status == "running"

        dialog.update_step_progress("step1", 50, "Processing audio chunk 5/10")
        assert dialog.overall_progress.value() == 25  # 50% of step 1 out of 2 steps = 25%

        dialog.finish_step("step1")
        assert dialog.steps["step1"].status == "done"
        assert dialog.overall_progress.value() == 50

        # Test error panel
        dialog.set_error("step2", "API rate limit exceeded")
        assert not dialog.error_panel.isHidden()
        assert "API rate limit exceeded" in dialog.error_label.text()
        assert not dialog.retry_btn.isHidden()
        assert not dialog.copy_error_btn.isHidden()

        # Test retry signal
        retried = []
        dialog.retry_requested.connect(lambda s: retried.append(s))
        dialog.retry_btn.click()
        assert retried == ["step2"]

        dialog.close()

    def test_mini_progress_status_bar(self, qapp):
        from ui.widgets.progress_dialog import MiniProgressStatusBar

        bar = MiniProgressStatusBar()
        bar.show()
        assert bar.badge.text() == "IDLE"

        bar.set_active("Production Pipeline", "Transcribing…")
        assert bar.badge.text() == "RUNNING"
        assert not bar.stop_btn.isHidden()

        bar.set_progress(42, "Synthesizing voice 42/100", chip="TTS")
        assert bar.percent_label.text() == "42%"
        assert bar.chip_label.text() == "TTS"
        assert not bar.chip_label.isHidden()

        bar.set_done("Video complete")
        assert bar.badge.text() == "DONE"
        assert bar.percent_label.text() == "100%"
        assert bar.stop_btn.isHidden()

        bar.set_idle()
        assert bar.badge.text() == "IDLE"
        assert bar.percent_label.text() == "0%"
        bar.close()

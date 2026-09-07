import os
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "ui"), str(ROOT / "app"), str(ROOT)]

from PySide6.QtWidgets import QApplication, QPushButton, QLabel, QProgressBar
from PySide6.QtCore import QObject

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_vocal_separation_worker_progress_signal(qapp, monkeypatch):
    from worker_adapters.processing_workers import VocalSeparationWorker
    from services.engine_runtime import EngineRuntime

    # Mock separate_vocals to simulate progress updates
    def fake_separate(self, audio_path, output_dir, progress_callback=None, is_cancelled=None):
        if progress_callback:
            progress_callback(10, "Loading audio...")
            progress_callback(50, "Separating chunk 1/2 (50%)")
            progress_callback(100, "Done")
        return "fake_vocal.wav", "fake_music.wav"

    monkeypatch.setattr(EngineRuntime, "separate_vocals", fake_separate)

    worker = VocalSeparationWorker("dummy.wav", "dummy_out")
    emitted_progress = []
    worker.progress.connect(lambda pct, msg: emitted_progress.append((pct, msg)))

    finished_result = []
    worker.finished.connect(lambda v, m, err: finished_result.append((v, m, err)))

    worker.run()

    assert len(emitted_progress) == 3
    assert emitted_progress[0] == (10, "Loading audio...")
    assert emitted_progress[1] == (50, "Separating chunk 1/2 (50%)")
    assert emitted_progress[2] == (100, "Done")
    assert len(finished_result) == 1
    assert finished_result[0] == ("fake_vocal.wav", "fake_music.wav", "")


def test_vocal_separation_ui_progress_updates(qapp):
    from ui.widgets.progress_dialog import MiniProgressStatusBar
    from features.workflow_actions import WorkflowActionsMixin

    class DummyGUI(WorkflowActionsMixin, QObject):
        def __init__(self):
            super().__init__()
            self.audio_separation_btn = QPushButton("Separate Voice and Music")
            self.vocal_sep_btn = QPushButton("Separate Voice and Background")
            self.audio_stem_status_label = QLabel("No separated stems yet")
            self.mini_status_bar = MiniProgressStatusBar()
            self.progress_bar = QProgressBar()

    gui = DummyGUI()
    gui.mini_status_bar.set_active("Vocal Separation", "Tách Voice.wav & Music.wav…")

    # Simulate progress event at 45%
    gui.on_vocal_separation_progress(45, "Đang tách âm thanh AI: 79/176 đoạn (45%)")

    assert "45%" in gui.audio_separation_btn.text()
    assert "45%" in gui.vocal_sep_btn.text()
    assert "45%" in gui.audio_stem_status_label.text()
    assert gui.mini_status_bar.percent_label.text() == "45%"
    assert "45%" in gui.mini_status_bar.detail_label.text()
    assert gui.progress_bar.value() == 35 + int(45 * 0.15)


def test_vocal_separation_worker_stop(qapp, monkeypatch):
    from worker_adapters.processing_workers import VocalSeparationWorker
    from services.engine_runtime import EngineRuntime

    def fake_separate_cancel(self, audio_path, output_dir, progress_callback=None, is_cancelled=None):
        if is_cancelled and is_cancelled():
            return None, None
        return "vocal.wav", "music.wav"

    monkeypatch.setattr(EngineRuntime, "separate_vocals", fake_separate_cancel)

    worker = VocalSeparationWorker("dummy.wav", "dummy_out")
    worker.stop()

    finished_result = []
    worker.finished.connect(lambda v, m, err: finished_result.append((v, m, err)))

    worker.run()
    assert len(finished_result) == 1
    assert "stopped" in finished_result[0][2].lower()


def test_vocal_separation_worker_auto_extracts_from_video(qapp, monkeypatch, tmp_path):
    from worker_adapters.processing_workers import VocalSeparationWorker
    from services.engine_runtime import EngineRuntime

    fake_video = str(tmp_path / "sample.mp4")
    with open(fake_video, "w") as f:
        f.write("video content")

    target_audio = str(tmp_path / "sample.wav")
    extracted = []

    def fake_extract(self, vid, aud):
        extracted.append((vid, aud))
        with open(aud, "w") as f:
            f.write("audio content")
        return True

    def fake_separate(self, audio_path, output_dir, progress_callback=None, is_cancelled=None):
        return "vocal.wav", "music.wav"

    monkeypatch.setattr(EngineRuntime, "extract_audio", fake_extract)
    monkeypatch.setattr(EngineRuntime, "separate_vocals", fake_separate)

    worker = VocalSeparationWorker(target_audio, str(tmp_path), video_path=fake_video)
    progress_messages = []
    worker.progress.connect(lambda pct, msg: progress_messages.append((pct, msg)))

    finished = []
    worker.finished.connect(lambda v, m, err: finished.append((v, m, err)))

    worker.run()

    assert len(extracted) == 1
    assert extracted[0] == (fake_video, target_audio)
    assert any("Extracting" in m for _, m in progress_messages)
    assert finished == [("vocal.wav", "music.wav", "")]


def test_audio_separation_btn_enabled_with_video_only(qapp, tmp_path):
    from main_window import VideoTranslatorGUI
    from PySide6.QtCore import QTimer

    fake_video = str(tmp_path / "test.mp4")
    with open(fake_video, "w") as f:
        f.write("dummy video")

    gui = VideoTranslatorGUI()
    try:
        # Before video is loaded and audio is empty
        gui.video_path_edit.setText("")
        gui.audio_source_edit.setText("")
        gui.refresh_ui_state()
        assert gui.audio_separation_btn.isEnabled() is False

        # When only video is loaded (no audio extracted yet)
        gui.video_path_edit.setText(fake_video)
        gui.refresh_ui_state()
        # audio_separation_btn MUST BE ENABLED for loaded video!
        assert gui.audio_separation_btn.isEnabled() is True
    finally:
        for timer in gui.findChildren(QTimer):
            timer.stop()
        gui.hide()
        gui.deleteLater()
        qapp.processEvents()



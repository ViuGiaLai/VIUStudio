import pytest
from PySide6.QtWidgets import QApplication
from ui.dialogs.video_compare_dialog import VideoCompareDialog
from app.services.auto_recap_engine import ShotDecision


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_video_compare_dialog_initialization(qapp):
    decisions = [
        ShotDecision(
            shot_index=0,
            start_time=0.0,
            end_time=3.5,
            duration=3.5,
            importance_score=50.0,
            action_type="KEEP",
            zoom_scale=1.05,
            color_grade=True,
            pitch_shift=True,
            vignette=True,
            recap_notes="Score: 50 | Anti-Duplicate protected",
        ),
        ShotDecision(
            shot_index=1,
            start_time=3.5,
            end_time=7.0,
            duration=3.5,
            importance_score=75.0,
            action_type="KEEP",
            zoom_scale=1.10,
            horizontal_flip=True,
            color_grade=True,
            pitch_shift=True,
            vignette=True,
            recap_notes="Score: 75 | Reused 3rd: Horizontal Flip",
        ),
    ]

    dialog = VideoCompareDialog(
        original_video_path="dummy_orig.mp4",
        processed_video_path="dummy_proc.mp4",
        decisions=decisions,
    )
    assert dialog.windowTitle() == "So sánh Video: Gốc vs Đã xử lý Chống trùng lặp (Anti-Duplicate)"
    assert dialog.table.rowCount() == 2
    assert "Shot 1" in dialog.table.item(0, 0).text()
    assert "105%" in dialog.table.item(0, 2).text()
    assert "Đổi màu" in dialog.table.item(0, 3).text()
    assert "Pitch" in dialog.table.item(0, 5).text() or "Dịch cao độ" in dialog.table.item(0, 5).text()

    assert "Shot 2" in dialog.table.item(1, 0).text()
    assert "110%" in dialog.table.item(1, 2).text()
    assert "Lật an toàn" in dialog.table.item(1, 4).text()

    # Test audio toggling
    assert dialog._audio_source == "processed"
    dialog._toggle_audio_source()
    assert dialog._audio_source == "original"
    dialog._toggle_audio_source()
    assert dialog._audio_source == "processed"

    # Test formatting
    assert dialog._format_sec(65.0) == "01:05"
    assert dialog._format_sec(0.0) == "00:00"

    dialog.close()

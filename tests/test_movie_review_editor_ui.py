import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "ui"), str(ROOT / "app")]

from PySide6.QtCore import QSettings
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QLabel, QMessageBox

from views.movie_review_editor import MovieReviewEditorWindow, _ExportWarningDialog
from app.services.movie_review_service import MovieReviewProject, MovieReviewScene

SETTINGS_KEYS = ("tts_voice", "last_project_path", "last_project_dir")

SAMPLE_SRT = "1\n00:00:01,000 --> 00:00:02,000\nXin chào\n\n2\n00:00:03,000 --> 00:00:04,000\nTạm biệt\n"


def _scene(scene_id, start, end, review="", approved=False, confidence=0.9):
    return MovieReviewScene(
        scene_id, start, end, [1], ["cue"], review_text=review,
        confidence=confidence, source_alignment=confidence, approved=approved,
    )


class MovieReviewEditorUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.settings = QSettings("VIUStudio", "MovieReviewEditor")
        self.saved = {key: self.settings.value(key, None) for key in SETTINGS_KEYS}
        self.tmp = tempfile.TemporaryDirectory()
        # Never let a stray modal dialog hang the suite.
        self.dialogs = [
            patch("views.movie_review_editor.QMessageBox.warning"),
            patch("views.movie_review_editor.QMessageBox.information"),
            patch("views.movie_review_editor.QMessageBox.critical"),
            patch("views.movie_review_editor.QMessageBox.question", return_value=QMessageBox.Yes),
        ]
        for dialog in self.dialogs:
            dialog.start()
        self.window = MovieReviewEditorWindow(self.tmp.name)
        # Visibility checks only reflect real state once the widget is shown.
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        for dialog in self.dialogs:
            dialog.stop()
        self.tmp.cleanup()
        for key, value in self.saved.items():
            if value is None:
                self.settings.remove(key)
            else:
                self.settings.setValue(key, value)

    def _write_srt(self, name="input.srt"):
        path = Path(self.tmp.name) / name
        path.write_text(SAMPLE_SRT, encoding="utf-8")
        return path

    def _upload_srt(self):
        path = self._write_srt()
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "SubRip (*.srt)")):
            self.window._choose_srt()
        return path

    def _upload_video(self, name="movie.mp4"):
        path = Path(self.tmp.name) / name
        path.write_bytes(b"")
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "Video (*.mp4)")):
            self.window._choose_video()
        return path

    def test_startup_starts_clean_even_when_an_old_project_is_remembered(self):
        old_dir = Path(self.tmp.name) / "projects" / "movie_review_old"
        old_dir.mkdir(parents=True)
        (old_dir / "movie_review.json").write_text(
            json.dumps({"version": 1, "video_path": "old.mp4", "scenes": []}), encoding="utf-8"
        )
        self.settings.setValue("last_project_path", str(old_dir / "movie_review.json"))

        fresh = MovieReviewEditorWindow(self.tmp.name)
        fresh.show()
        self.app.processEvents()
        try:
            self.assertEqual(fresh.project.video_path, "")
            self.assertEqual(fresh._project_path, "")
            self.assertIn("Project: (chưa tạo)", fresh.video_path_label.text())
            self.assertIn("chưa có video", fresh.video_path_label.text())
            self.assertIn("chưa có SRT", fresh.video_path_label.text())
        finally:
            fresh.close()
            fresh.deleteLater()

    def test_srt_upload_creates_a_project_and_stores_its_own_copy(self):
        source = self._upload_srt()

        self.assertTrue(self.window._project_path)
        stored = Path(self.window.project.srt_path)
        self.assertTrue(stored.is_file())
        self.assertEqual(stored.name, "source.srt")
        self.assertEqual(stored.parent, Path(self.window._project_path).parent)
        self.assertEqual(self.window.project.source_srt_origin, str(source))
        self.assertEqual(len(self.window.project.source_segments), 2)
        self.assertIn("source.srt (2 dòng)", self.window.video_path_label.text())

    def test_uploading_a_video_after_the_srt_keeps_the_srt_and_shows_both(self):
        self._upload_srt()
        self._upload_video()

        self.assertTrue(self.window.project.video_path.endswith("movie.mp4"))
        self.assertEqual(len(self.window.project.source_segments), 2)
        self.assertTrue(Path(self.window.project.srt_path).is_file())
        label = self.window.video_path_label.text()
        self.assertIn("movie.mp4", label)
        self.assertIn("source.srt", label)

    def test_saved_project_round_trips_video_srt_and_scenes(self):
        self._upload_srt()
        self._upload_video()
        window = self.window
        window.project.scenes = [_scene("SCENE-0001", 1.0, 3.0, review="Cảnh mở đầu.", approved=True)]
        window._refresh_scene_list()
        window._save()
        self.assertTrue(Path(window._project_path).is_file())

        reopened = MovieReviewEditorWindow(self.tmp.name)
        reopened.show()
        self.app.processEvents()
        try:
            self.assertTrue(reopened._load_project_file(window._project_path))
            self.assertEqual(reopened.project.video_path, window.project.video_path)
            self.assertEqual(reopened.project.srt_path, window.project.srt_path)
            self.assertEqual(len(reopened.project.source_segments), 2)
            self.assertEqual([scene.scene_id for scene in reopened.project.scenes], ["SCENE-0001"])
            self.assertIn("1 Scene", reopened.video_path_label.text())
        finally:
            reopened.close()
            reopened.deleteLater()

    def test_project_folder_button_loads_the_project_in_a_selected_folder(self):
        self._upload_srt()
        folder = os.path.dirname(self.window._project_file())

        with patch("views.movie_review_editor.QFileDialog.getExistingDirectory", return_value=folder):
            self.window._open_project_folder()

        self.assertTrue(os.path.isdir(folder))
        self.assertTrue(os.path.isfile(os.path.join(folder, "source.srt")))
        self.assertIn(folder, self.window.status_label.text())

    def test_new_project_clears_video_srt_and_scenes(self):
        self._upload_srt()
        self._upload_video()
        self.window.project.scenes = [_scene("SCENE-0001", 1.0, 3.0, review="Cảnh mở đầu.")]
        self.window._refresh_scene_list()

        self.window._new_project()

        self.assertEqual(self.window.project.video_path, "")
        self.assertEqual(self.window.project.srt_path, "")
        self.assertEqual(self.window.project.source_segments, [])
        self.assertEqual(self.window.project.scenes, [])
        self.assertTrue(self.window._project_path.endswith("movie_review.json"))
        self.assertEqual(Path(self.window._project_path).parent.parent.name, "MovieReviewProjects")
        self.assertTrue(Path(self.window._project_path).is_file())
        self.assertIn("chưa có SRT", self.window.video_path_label.text())

    def _drain(self, timeout: float = 10.0):
        deadline = time.time() + timeout
        while self.window._threads and time.time() < deadline:
            self.app.processEvents()
            time.sleep(0.02)
        self.app.processEvents()

    def test_running_a_task_reports_progress_without_locking_the_preview(self):
        window = self.window
        observed = []

        def task(report, is_cancelled):
            report(42, "đang chạy")
            time.sleep(0.3)
            return "xong"

        results = []
        window._run_task(task, results.append, "test")
        deadline = time.time() + 5
        while window._threads and time.time() < deadline:
            self.app.processEvents()
            time.sleep(0.02)
            if window.progress_bar.isVisible():
                observed.append((
                    window.progress_bar.value(),
                    window.play_btn.isEnabled(),
                    window.build_btn.isEnabled(),
                    window.status_label.text(),
                ))
        self._drain()

        self.assertEqual(results, ["xong"])
        self.assertIn((42, True, False, "đang chạy"), observed)
        self.assertFalse(window.progress_bar.isVisible())
        self.assertTrue(window.build_btn.isEnabled())

    def test_cancel_stops_a_task_without_an_error_dialog(self):
        window = self.window

        def task(report, is_cancelled):
            report(10, "bước 1")
            for _ in range(400):
                if is_cancelled():
                    raise InterruptedError("Đã huỷ.")
                time.sleep(0.01)
            return "không được huỷ"

        with patch("views.movie_review_editor.QMessageBox.critical") as critical:
            window._run_task(task, lambda _value: None, "test")
            self.app.processEvents()
            window._cancel_task()
            self.assertTrue(window.cancel_btn.isVisible())
            self._drain()

        critical.assert_not_called()
        self.assertEqual(window.status_label.text(), "Đã huỷ tác vụ.")
        self.assertFalse(window.cancel_btn.isVisible())
        self.assertIsNone(window._cancel_event)

    def test_play_scene_seeks_to_the_scene_and_explains_unplayable_video(self):
        class _Player:
            def __init__(self):
                self.seeks = []
                self.plays = 0
                self.status = QMediaPlayer.NoMedia

            def mediaStatus(self):
                return self.status

            def setPosition(self, value):
                self.seeks.append(value)

            def play(self):
                self.plays += 1

            def pause(self):
                pass

            def stop(self):
                pass

        player = _Player()
        self.window.player = player
        self.window.project = MovieReviewProject(
            video_path=str(Path(self.tmp.name) / "movie.mp4"),
            scenes=[_scene("SCENE-0001", 1.0, 3.0, review="Cảnh mở đầu.", approved=True)],
        )
        self.window._refresh_scene_list()

        with patch("views.movie_review_editor.QMessageBox.warning") as warning:
            self.window._play_scene()
        self.assertEqual(player.plays, 0)
        self.assertTrue(warning.called)
        self.assertIn("trình phát ngoài", self.window.video_hint_label.text())

        player.status = QMediaPlayer.LoadedMedia
        self.window._play_scene()
        self.assertEqual(player.plays, 1)
        self.assertEqual(player.seeks[-1], 1000)

    def test_scene_list_and_qa_bar_mark_errors_and_warnings(self):
        self.window.project = MovieReviewProject(scenes=[
            _scene("SCENE-0001", 0.0, 3.0, review="Cảnh mở đầu nhưng đầy bất ngờ.", approved=True),
            _scene("SCENE-0002", 3.0, 6.0, review="Cảnh tiếp theo.", confidence=0.2),
            _scene("SCENE-0003", 6.0, 9.0),
        ])
        self.window._refresh_scene_list()

        rows = [self.window.scene_list.item(i).text() for i in range(self.window.scene_list.count())]
        self.assertIn("TTS —", rows[0])
        self.assertTrue(rows[0].startswith("✓"))
        self.assertTrue(rows[1].startswith("⚠"))
        self.assertTrue(rows[2].startswith("⛔"))
        self.assertIn("Chưa có lời review", self.window.scene_list.item(2).toolTip())
        self.assertIn("lỗi chặn Export", self.window.qa_label.text())
        self.assertTrue(self.window.qa_btn.isEnabled())

        # Selecting a Scene surfaces the same findings in the editor panel.
        self.window._select_scene(2)
        self.assertIn("⛔", self.window.warning_label.text())

    def test_approve_all_only_approves_scenes_that_have_a_review(self):
        self.window.project = MovieReviewProject(scenes=[
            _scene("SCENE-0001", 0.0, 3.0, review="Cảnh mở đầu."),
            _scene("SCENE-0002", 3.0, 6.0, review="Cảnh tiếp theo."),
            _scene("SCENE-0003", 6.0, 9.0),
        ])
        self.window._refresh_scene_list()

        self.window._approve_all()

        self.assertEqual([scene.approved for scene in self.window.project.scenes], [True, True, False])
        self.assertIn("2/3", self.window.status_label.text())
        self.assertIn("SCENE-0003", self.window.status_label.text())

    def test_export_warning_dialog_lists_findings_and_jumps_to_a_scene(self):
        issues = [
            {"scene_id": "SCENE-0002", "code": "low_confidence", "severity": "warning", "message": "Độ tin cậy thấp (20%)."},
            {"scene_id": "SCENE-0003", "code": "missing_review", "severity": "error", "message": "Chưa có lời review."},
        ]
        dialog = _ExportWarningDialog(issues, self.window, allow_export=False)
        self.assertEqual(dialog.list_widget.count(), 2)
        self.assertIsNone(dialog.export_btn)
        self.assertIn("⛔ SCENE-0003", dialog.list_widget.item(1).text())
        labels = [label.text() for label in dialog.findChildren(QLabel)]
        self.assertTrue(any("1 lỗi chặn Export" in text for text in labels))

        dialog.list_widget.setCurrentRow(0)
        dialog._jump()
        self.assertEqual(dialog.jump_scene_id, "SCENE-0002")
        self.assertEqual(dialog.result(), int(QDialog.Accepted))

        allowed = _ExportWarningDialog(issues[:1], self.window, allow_export=True)
        self.assertIsNotNone(allowed.export_btn)

    def test_voice_picker_prefers_vietnamese_and_always_keeps_a_default(self):
        catalog = [
            {"id": "en-US-AriaNeural", "name": "Aria", "provider": "edge",
             "provider_voice": "en-US-AriaNeural", "language": "en-US"},
            {"id": "edge:vi-VN-NamMinhNeural", "name": "NamMinh", "provider": "edge",
             "provider_voice": "vi-VN-NamMinhNeural", "language": "vi-VN"},
        ]
        with patch("services.voice_catalog_service.VoiceCatalogService.load_catalog", return_value=catalog):
            self.window._reload_voices()

        combo = self.window.voice_combo
        self.assertEqual(combo.itemData(0), "banmai")
        self.assertGreaterEqual(combo.findData("edge:vi-VN-NamMinhNeural"), 0)

        with patch("services.voice_catalog_service.VoiceCatalogService.load_catalog", return_value=[]):
            self.window._reload_voices()
        self.assertEqual(combo.count(), 1)
        self.assertEqual(self.window._selected_voice(), "banmai")

    def test_changing_the_voice_invalidates_rendered_review_audio(self):
        self.window.project = MovieReviewProject(scenes=[
            _scene("SCENE-0001", 0.0, 3.0, review="Cảnh mở đầu.", approved=True),
        ])
        scene = self.window.project.scenes[0]
        scene.tts_rendered = True
        scene.tts_audio_path = os.path.join(self.tmp.name, "scene-0001.wav")

        combo = self.window.voice_combo
        target = combo.findData("edge:vi-VN-HoaiMyNeural")
        self.assertGreaterEqual(target, 0)
        # Emit the signal the picker is wired to, so the assertion holds even
        # when the requested voice is already the current index.
        combo.currentIndexChanged.emit(target)

        self.assertFalse(scene.tts_rendered)
        self.assertEqual(scene.tts_audio_path, "")
        self.assertIn("cần tạo lại TTS", self.window.status_label.text())

    def _prepare_story_arc_project(self):
        self._upload_srt()
        self._upload_video()
        self.window.project.scenes = [
            _scene("SCENE-0001", 1.0, 3.0),
            _scene("SCENE-0002", 3.5, 6.0),
            _scene("SCENE-0003", 40.0, 45.0),
        ]
        self.window._refresh_scene_list()
        return self.window

    def test_story_arc_reports_progress_and_applies_each_arc_before_finishing(self):
        window = self._prepare_story_arc_project()
        observed = []
        original = window._on_task_progress

        def capture(percent, message):
            observed.append((percent, message))
            original(percent, message)

        window._on_task_progress = capture

        def fake_arc(project, start, end, **_kwargs):
            return {"scene_reviews": [
                {
                    "scene_id": scene.scene_id,
                    "review_text": f"Kể {scene.scene_id}.",
                    "confidence": 0.9,
                    "source_alignment": 0.9,
                    "summary": scene.scene_id,
                    "narration_plan": [],
                    "story_beat": {},
                }
                for scene in project.scenes[start:end]
            ]}

        with patch.object(window.service, "extract_keyframes", return_value=["k.jpg"]), \
             patch.object(window.service, "extract_story_arc_clip", return_value=window.project.video_path), \
             patch.object(window.ai, "review_story_arc", side_effect=fake_arc), \
             patch.object(window.ai, "plan_edit_scene", return_value={"edit_plan": []}):
            window._analyze_all()
            self._drain(15)

        self.assertTrue(window.project.scenes[0].review_text.startswith("Kể"))
        self.assertTrue(window.project.scenes[2].review_text.startswith("Kể"))
        messages = [msg for _percent, msg in observed]
        self.assertTrue(any("Story Arc 1/" in msg for msg in messages))
        self.assertTrue(any("keyframe" in msg or "cắt clip" in msg for msg in messages))
        self.assertIn("2 Story Arc", window.status_label.text())
        self.assertFalse(window.progress_bar.isVisible())

    def test_story_arc_fills_missing_scenes_instead_of_aborting(self):
        window = self._prepare_story_arc_project()

        def fake_arc(project, start, end, **_kwargs):
            first = project.scenes[start]
            return {"scene_reviews": [{
                "scene_id": first.scene_id,
                "review_text": f"Có {first.scene_id}.",
                "confidence": 0.9,
                "source_alignment": 0.9,
            }]}

        def fake_scene(project, index, **_kwargs):
            scene = project.scenes[index]
            return {
                "review_text": f"Bù {scene.scene_id}.",
                "confidence": 0.85,
                "source_alignment": 0.85,
                "summary": "",
                "narration_plan": [],
                "story_beat": {},
            }

        with patch.object(window.service, "extract_keyframes", return_value=["k.jpg"]), \
             patch.object(window.service, "extract_context_clip", return_value="clip.mp4"), \
             patch.object(window.service, "extract_story_arc_clip", return_value=window.project.video_path), \
             patch.object(window.ai, "review_story_arc", side_effect=fake_arc), \
             patch.object(window.ai, "review_scene", side_effect=fake_scene), \
             patch.object(window.ai, "plan_edit_scene", return_value={"edit_plan": []}):
            window._analyze_all()
            self._drain(15)

        self.assertIn("Có SCENE-0001", window.project.scenes[0].review_text)
        self.assertIn("Bù SCENE-0002", window.project.scenes[1].review_text)
        # SCENE-0003 is its own Story Arc window, so the partial Gemini payload
        # still covers it; only the omitted Scene inside a multi-Scene Arc is filled.
        self.assertIn("Có SCENE-0003", window.project.scenes[2].review_text)
        self.assertNotIn("Có lỗi", window.status_label.text())

    def test_story_arc_trims_overflow_narration_without_an_extra_gemini_call(self):
        window = self._prepare_story_arc_project()
        long_text = "Một câu ngắn. " + " ".join(["Một câu rất dài"] * 40) + "."

        def fake_arc(project, start, end, **_kwargs):
            return {"scene_reviews": [{
                "scene_id": scene.scene_id,
                "review_text": long_text,
                "confidence": 0.9,
                "source_alignment": 0.9,
            } for scene in project.scenes[start:end]]}

        with patch.object(window.service, "extract_keyframes", return_value=["k.jpg"]), \
             patch.object(window.service, "extract_story_arc_clip", return_value=window.project.video_path), \
             patch.object(window.ai, "review_story_arc", side_effect=fake_arc), \
             patch.object(window.ai, "review_scene") as review_scene, \
             patch.object(window.ai, "plan_edit_scene", return_value={"edit_plan": []}):
            window._analyze_all()
            self._drain(15)

        review_scene.assert_not_called()
        self.assertEqual(window.project.scenes[0].review_text, "Một câu ngắn.")
        self.assertLess(
            window.service.estimate_tts_duration(window.project.scenes[0].review_text),
            window._available_narration_window(0) + 0.2,
        )


if __name__ == "__main__":
    unittest.main()

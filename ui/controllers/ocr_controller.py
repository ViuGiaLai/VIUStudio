import os
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)
try:
    from ui.worker_adapters import OcrTranslatorCaptureWorker, OcrTranslatorTranslationWorker
except ImportError:
    from worker_adapters import OcrTranslatorCaptureWorker, OcrTranslatorTranslationWorker

try:
    from ui.utils.thread_lifecycle import release_thread_when_stopped
except ImportError:
    from utils.thread_lifecycle import release_thread_when_stopped



class OcrController:
    """Controller for OCR Region Editing and interactive OCR Translation tools."""

    def __init__(self, gui):
        self.gui = gui

    def toggle_ocr_region_editing(self, checked: bool):
        overlay = getattr(self.gui, "ocr_region_overlay", None)
        if overlay is None:
            return
        default_engine = "sensevoice"
        engine = os.getenv("TRANSCRIPTION_ENGINE", default_engine)
        if not checked or engine != "ocr":
            overlay.hide()
            overlay.set_editable(False)
            if hasattr(self.gui, "ocr_region_btn"):
                self.gui.ocr_region_btn.setStyleSheet("QPushButton { color: #6ee7d6; font-weight: bold; font-size: 10px; padding: 0; }")
            if hasattr(self.gui, "_sync_blur_controls"):
                self.gui._sync_blur_controls()
            return
        if hasattr(self.gui, "_blur_effect_enabled") and self.gui._blur_effect_enabled():
            if hasattr(self.gui, "video_view") and hasattr(self.gui.video_view, "set_blur_edit_enabled"):
                self.gui.video_view.set_blur_edit_enabled(False)
        overlay.set_editable(True)
        overlay.sync_to_view()
        if hasattr(self.gui, "apply_preview_blur_region"):
            self.gui.apply_preview_blur_region()
        self.gui.log("[OCR Region] drag inside the video preview to move or resize the OCR crop.")

    def toggle_ocr_translator(self, checked: bool):
        """Show the independent, on-demand OCR Translator selection."""
        overlay = getattr(self.gui, "ocr_translator_overlay", None)
        self.gui._ocr_translator_active = bool(checked)
        if overlay is None:
            return
        if not self.gui._ocr_translator_active:
            overlay.hide()
            return
        video_path = self.gui.resolve_canonical_video_path() if hasattr(self.gui, "resolve_canonical_video_path") else (self.gui.video_path_edit.text().strip() if hasattr(self.gui, "video_path_edit") else "")
        if not video_path or not os.path.isfile(video_path):
            self.gui._ocr_translator_active = False
            button = getattr(self.gui, "ocr_translator_btn", None)
            if button is not None:
                button.blockSignals(True)
                button.setChecked(False)
                button.blockSignals(False)
            QMessageBox.warning(self.gui, "OCR Translator", "Please load a video before capturing visual text.")
            return
        overlay.set_normalized_rect(getattr(self.gui, "_ocr_translator_rect", (0.2, 0.2, 0.6, 0.25)))
        overlay.sync_to_view()
        QTimer.singleShot(0, overlay.sync_to_view)
        self.gui.log("[OCR Translator] Selection active. Drag or resize it, then click Capture.")

    def on_ocr_translator_rect_changed(self, rect):
        self.gui._ocr_translator_rect = tuple(rect)

    def capture_ocr_translator_region(self):
        if getattr(self.gui, "_ocr_translator_capture_worker", None) is not None:
            return
        video_path = self.gui.resolve_canonical_video_path() if hasattr(self.gui, "resolve_canonical_video_path") else (self.gui.video_path_edit.text().strip() if hasattr(self.gui, "video_path_edit") else "")
        overlay = getattr(self.gui, "ocr_translator_overlay", None)
        if not video_path or overlay is None:
            return
        position_ms = int(self.gui.media_player.position()) if hasattr(self.gui, "media_player") else 0
        self.gui._ocr_translator_rect = overlay.normalized_rect()
        overlay.set_capturing(True)
        worker = OcrTranslatorCaptureWorker(video_path, position_ms / 1000.0, self.gui._ocr_translator_rect)
        self.gui._ocr_translator_capture_worker = worker
        worker.finished.connect(self.on_ocr_translator_capture_finished)
        worker.finished.connect(
            lambda *_args, worker=worker: release_thread_when_stopped(
                worker,
                lambda: setattr(self.gui, "_ocr_translator_capture_worker", None)
                if getattr(self.gui, "_ocr_translator_capture_worker", None) is worker
                else None,
            )
        )
        worker.start()
        self.gui.log(f"[OCR Translator] Capturing visual text at {position_ms / 1000.0:.2f}s.")

    def on_ocr_translator_capture_finished(self, text, error):
        overlay = getattr(self.gui, "ocr_translator_overlay", None)
        if overlay is not None:
            overlay.set_capturing(False)
        if error:
            QMessageBox.warning(self.gui, "OCR Translator", f"Could not capture text.\n\n{error}")
            return
        if not str(text or "").strip():
            QMessageBox.information(self.gui, "OCR Translator", "No text was detected in the selected region.")
            return
        self.gui.log("[OCR Translator] Capture complete.")
        self.show_ocr_translator_dialog(str(text).strip())

    def show_ocr_translator_dialog(self, original_text):
        overlay = getattr(self.gui, "ocr_translator_overlay", None)
        if overlay is not None:
            overlay.hide()
        dialog = QDialog(self.gui)
        dialog.setWindowTitle("OCR Translator")
        dialog.setWindowModality(Qt.WindowModal)
        dialog.setMinimumSize(520, 390)
        dialog.setStyleSheet(
            "QDialog { background: #101826; color: #e6eef9; }"
            "QLabel { color: #b9c8dc; font-weight: 700; }"
            "QTextEdit { background: #0b1220; color: #edf4ff; border: 1px solid #2b3b52; border-radius: 7px; padding: 7px; }"
            "QPushButton { background: #24364f; color: #ffffff; border: 1px solid #355271; border-radius: 7px; padding: 7px 12px; font-weight: 700; }"
            "QPushButton:hover { background: #315070; } QPushButton:disabled { color: #718198; background: #182334; }"
        )
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(8)
        layout.addWidget(QLabel("Original OCR Text"))
        original_edit = QTextEdit()
        original_edit.setPlainText(original_text)
        original_edit.setReadOnly(True)
        layout.addWidget(original_edit, 1)
        layout.addWidget(QLabel("Translated Text"))
        translated_edit = QTextEdit()
        translated_edit.setReadOnly(True)
        translated_edit.setPlaceholderText("Click Translate to translate the captured text.")
        layout.addWidget(translated_edit, 1)
        actions = QHBoxLayout()
        translate_btn = QPushButton("Translate")
        copy_original_btn = QPushButton("Copy Original")
        copy_translation_btn = QPushButton("Copy Translation")
        close_btn = QPushButton("Close")
        actions.addWidget(translate_btn)
        actions.addWidget(copy_original_btn)
        actions.addWidget(copy_translation_btn)
        actions.addStretch(1)
        actions.addWidget(close_btn)
        layout.addLayout(actions)

        def copy_text(edit):
            QApplication.clipboard().setText(edit.toPlainText())

        def translate():
            if getattr(self.gui, "_ocr_translator_translation_worker", None) is not None:
                return
            translate_btn.setEnabled(False)
            translate_btn.setText("Translating...")
            worker = OcrTranslatorTranslationWorker(
                original_text, self.gui.get_source_language_code(), self.gui.get_target_language_code()
            )
            self.gui._ocr_translator_translation_worker = worker

            def finished(translated, error):
                translate_btn.setEnabled(True)
                translate_btn.setText("Translate")
                if error:
                    QMessageBox.warning(dialog, "OCR Translator", f"Translation failed.\n\n{error}")
                    return
                translated_edit.setPlainText(translated)
                self.gui.log("[OCR Translator] Translation complete.")

            worker.finished.connect(finished)
            worker.finished.connect(
                lambda *_args, worker=worker: release_thread_when_stopped(
                    worker,
                    lambda: setattr(self.gui, "_ocr_translator_translation_worker", None)
                    if getattr(self.gui, "_ocr_translator_translation_worker", None) is worker
                    else None,
                )
            )
            worker.start()

        translate_btn.clicked.connect(translate)
        copy_original_btn.clicked.connect(lambda: copy_text(original_edit))
        copy_translation_btn.clicked.connect(lambda: copy_text(translated_edit))
        close_btn.clicked.connect(dialog.close)
        dialog.exec()

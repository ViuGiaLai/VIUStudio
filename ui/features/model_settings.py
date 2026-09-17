import os
import re
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QLineEdit,
                             QComboBox,
                             QFrame, QMessageBox,
                             QDialog, QLayout)
from PySide6.QtCore import QTimer

from utils.file_dialog_utils import (
    open_folder as open_folder_impl,
)
from runtime_paths import models_path
from runtime_profile import is_remote_profile



class ModelSettingsMixin:
    def open_model_settings_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Settings")
        dialog.setModal(True)
        dialog.setMinimumWidth(450)
        dialog.setStyleSheet(
            """
            QDialog {
                background-color: #0f1724;
            }
            QLabel {
                color: #d7e3f4;
                background: transparent;
            }
            QLabel#statusHeadline {
                color: #f8fbff;
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#helperLabel {
                color: #9fb3ca;
                font-size: 12px;
            }
            QComboBox, QLineEdit {
                background-color: #132033;
                color: #f8fbff;
                border: 1px solid #2f4868;
                border-radius: 10px;
                padding: 8px 10px;
                min-height: 18px;
            }
            QComboBox::drop-down {
                border: none;
                width: 28px;
            }
            QComboBox QAbstractItemView {
                background-color: #132033;
                color: #f8fbff;
                border: 1px solid #2f4868;
                selection-background-color: #24486c;
                selection-color: #ffffff;
            }
            QPushButton {
                background-color: #22344d;
                color: #f8fbff;
                border: 1px solid #34506f;
                border-radius: 10px;
                padding: 8px 16px;
                font-weight: 600;
                min-width: 84px;
            }
            QPushButton:hover {
                background-color: #29405d;
            }
            QPushButton:pressed {
                background-color: #1d2d42;
            }
            """
        )
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        layout.setSizeConstraint(QLayout.SetFixedSize)

        remote_mode = is_remote_profile()
        # Transcription Engine Section
        engine_title = QLabel("Subtitle source")
        engine_title.setObjectName("statusHeadline")
        layout.addWidget(engine_title)

        engine_combo = QComboBox(dialog)
        engine_combo.addItem("Audio (SenseVoice) - Chinese / English / Japanese / Korean only", "sensevoice")
        engine_combo.addItem("Audio (Whisper) - Multilingual quality", "whisper")
        engine_combo.addItem("Video (OCR)", "ocr")
        current_engine = self.get_transcription_engine()
        idx = engine_combo.findData(current_engine)
        if idx >= 0:
            engine_combo.setCurrentIndex(idx)
        layout.addWidget(engine_combo)

        # OCR Region combo (only visible when OCR selected)
        region_label = QLabel("Subtitle position:")
        region_label.setVisible(current_engine == "ocr")
        region_combo = QComboBox(dialog)
        region_combo.addItem("Bottom (default)", "bottom")
        region_combo.addItem("Top", "top")
        region_combo.addItem("Full frame", "full")
        current_region = (os.getenv("OCR_SUBTITLE_REGION") or "bottom").strip().lower()
        idx = region_combo.findData(current_region)
        if idx >= 0:
            region_combo.setCurrentIndex(idx)
        region_combo.setVisible(current_engine == "ocr")
        layout.addWidget(region_label)
        layout.addWidget(region_combo)

        sampling_label = QLabel("OCR sampling rate:")
        sampling_label.setToolTip("Higher rates catch shorter subtitle flashes but process more video frames.")
        sampling_label.setVisible(current_engine == "ocr")
        sampling_combo = QComboBox(dialog)
        sampling_combo.addItem("Auto (recommended)", "auto")
        sampling_combo.addItem("1 FPS (lighter)", "1")
        sampling_combo.addItem("1.5 FPS", "1.5")
        sampling_combo.addItem("2 FPS", "2")
        sampling_combo.addItem("3 FPS", "3")
        sampling_combo.addItem("4 FPS (short flashes)", "4")
        current_sampling_fps = str(os.getenv("OCR_SAMPLING_FPS") or "auto").strip().lower()
        idx = sampling_combo.findData(current_sampling_fps)
        sampling_combo.setCurrentIndex(idx if idx >= 0 else 0)
        sampling_combo.setVisible(current_engine == "ocr")
        layout.addWidget(sampling_label)
        layout.addWidget(sampling_combo)

        # Whisper Section
        is_whisper = current_engine == "whisper"
        whisper_title = QLabel("Whisper model")
        whisper_title.setObjectName("statusHeadline")
        whisper_title.setVisible(is_whisper)
        layout.addWidget(whisper_title)

        whisper_combo = QComboBox(dialog)
        is_gpu = os.environ.get("VIUSTUDIO_DEVICE", "cuda").strip().lower() == "cuda"
        if is_gpu:
            whisper_combo.addItem("Whisper Large-v3 (NÊN CÓ ⭐⭐⭐⭐⭐)", "large-v3")
            whisper_combo.addItem("Whisper Large-v3-Turbo (Tùy chọn ⭐⭐⭐⭐½)", "large-v3-turbo")
            whisper_combo.addItem("Whisper Medium (Cân bằng ⭐⭐⭐⭐)", "medium")
        else:
            whisper_combo.addItem("Whisper Medium", "medium")
        whisper_combo.addItem("Whisper Small (Fast)", "small")
        whisper_combo.addItem("Whisper Base", "base")
        current_whisper = str(getattr(self, "selected_whisper_model_name", "auto") or "auto").strip().lower()
        if current_whisper == "auto":
            current_whisper = self.get_whisper_model_name()
        whisper_index = whisper_combo.findData(current_whisper)
        whisper_combo.setCurrentIndex(whisper_index if whisper_index >= 0 else 0)
        whisper_combo.setVisible(is_whisper)
        layout.addWidget(whisper_combo)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("color: #2f4868;")
        layout.addWidget(divider)

        remote_title = QLabel("Remote API")
        remote_title.setObjectName("statusHeadline")
        remote_title.setVisible(remote_mode)
        layout.addWidget(remote_title)

        remote_url_layout = QVBoxLayout()
        remote_url_label = QLabel("PC API URL:")
        remote_url_edit = QLineEdit(dialog)
        remote_url_edit.setText(os.getenv("VIUSTUDIO_REMOTE_API_URL", "http://127.0.0.1:8765"))
        remote_url_layout.addWidget(remote_url_label)
        remote_url_layout.addWidget(remote_url_edit)
        remote_url_label.setVisible(remote_mode)
        remote_url_edit.setVisible(remote_mode)
        layout.addLayout(remote_url_layout)

        remote_token_layout = QVBoxLayout()
        remote_token_label = QLabel("API Token (optional):")
        remote_token_edit = QLineEdit(dialog)
        remote_token_edit.setEchoMode(QLineEdit.Password)
        remote_token_edit.setText(os.getenv("VIUSTUDIO_REMOTE_API_TOKEN", ""))
        remote_token_layout.addWidget(remote_token_label)
        remote_token_layout.addWidget(remote_token_edit)
        remote_token_label.setVisible(remote_mode)
        remote_token_edit.setVisible(remote_mode)
        layout.addLayout(remote_token_layout)

        remote_actions_layout = QHBoxLayout()
        test_remote_btn = QPushButton("Test Connection", dialog)
        test_remote_btn.setVisible(remote_mode)
        remote_actions_layout.addWidget(test_remote_btn)
        remote_actions_layout.addStretch()
        layout.addLayout(remote_actions_layout)

        remote_hint_label = QLabel(
            "Remote mode keeps Whisper and AI translation on your PC server. "
            "This laptop build only sends extracted audio and subtitle segments over HTTP."
        )
        remote_hint_label.setObjectName("helperLabel")
        remote_hint_label.setWordWrap(True)
        remote_hint_label.setVisible(remote_mode)
        layout.addWidget(remote_hint_label)

        remote_divider = QFrame()
        remote_divider.setFrameShape(QFrame.HLine)
        remote_divider.setStyleSheet("color: #2f4868;")
        remote_divider.setVisible(remote_mode)
        layout.addWidget(remote_divider)

        # AI Translation Section
        ai_title = QLabel("AI Translation")
        ai_title.setObjectName("statusHeadline")
        ai_title.setVisible(not remote_mode)
        layout.addWidget(ai_title)

        provider_layout = QHBoxLayout()
        provider_label = QLabel("Translator Provider:")
        provider_label.setVisible(not remote_mode)
        provider_layout.addWidget(provider_label)
        provider_combo = QComboBox(dialog)
        provider_combo.addItem("Google Translate (free, no key)", "google")
        provider_combo.addItem("Google AI Studio", "google_ai_studio")
        provider_combo.addItem("OpenAI", "openai")
        provider_combo.addItem("Ollama (Local)", "ollama")
        current_provider = (os.getenv("OPENAI_PROVIDER") or "google").strip().lower()
        if current_provider == "gemini":
            current_provider = "google_ai_studio"
        if current_provider not in {"google", "google_ai_studio", "openai", "ollama"}:
            current_provider = "google"
        idx = provider_combo.findData(current_provider)
        if idx >= 0:
            provider_combo.setCurrentIndex(idx)
        provider_combo.setVisible(not remote_mode)
        provider_layout.addWidget(provider_combo, 1)
        layout.addLayout(provider_layout)

        def _provider_values(provider):
            if provider == "google_ai_studio":
                legacy = str(os.getenv("OPENAI_PROVIDER") or "").strip().lower() == "gemini"
                return (
                    os.getenv("GOOGLE_AI_STUDIO_API_KEY", "") or (os.getenv("OPENAI_API_KEY", "") if legacy else ""),
                    os.getenv("GOOGLE_AI_STUDIO_MODEL", "") or (os.getenv("OPENAI_MODEL", "") if legacy else ""),
                    os.getenv("GOOGLE_AI_STUDIO_BASE_URL", "") or (os.getenv("OPENAI_BASE_URL", "") if legacy else ""),
                )
            return (os.getenv("OPENAI_API_KEY", ""), os.getenv("OPENAI_MODEL", ""), os.getenv("OPENAI_BASE_URL", ""))

        initial_key, initial_model, initial_base_url = _provider_values(current_provider)

        key_section_widget = QWidget(dialog)
        key_layout = QVBoxLayout(key_section_widget)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_label = QLabel("API Key:")
        key_edit = QLineEdit(dialog)
        key_edit.setEchoMode(QLineEdit.Password)
        key_edit.setText(initial_key)
        key_layout.addWidget(key_label)
        key_layout.addWidget(key_edit)
        key_section_widget.setVisible(not remote_mode)
        layout.addWidget(key_section_widget)

        model_layout = QVBoxLayout()
        model_label = QLabel("AI Model:")
        model_edit = QLineEdit(dialog)
        model_edit.setText(initial_model)
        model_layout.addWidget(model_label)
        model_layout.addWidget(model_edit)
        model_label.setVisible(not remote_mode)
        model_edit.setVisible(not remote_mode)
        layout.addLayout(model_layout)

        polish_model_layout = QVBoxLayout()
        polish_model_label = QLabel("Quality Model (fix / review sentences):")
        polish_model_edit = QLineEdit(dialog)
        polish_model_edit.setPlaceholderText("Blank = use AI Model above (e.g. gemini-3.6-flash)")
        polish_model_layout.addWidget(polish_model_label)
        polish_model_layout.addWidget(polish_model_edit)
        _polish_defaults = {
            "google_ai_studio": ("GOOGLE_AI_STUDIO_POLISH_MODEL", "gemini-3.6-flash"),
            "openai": ("OPENAI_POLISH_MODEL", ""),
        }
        _polish_env, _polish_default = _polish_defaults.get(current_provider, ("", ""))
        polish_model_edit.setText(os.getenv(_polish_env, "") or _polish_default)
        polish_model_label.setVisible(False)
        polish_model_edit.setVisible(False)
        layout.addLayout(polish_model_layout)

        base_url_layout = QVBoxLayout()
        base_url_label = QLabel("API URL:")
        base_url_edit = QLineEdit(dialog)
        base_url_edit.setText(initial_base_url)
        base_url_layout.addWidget(base_url_label)
        base_url_layout.addWidget(base_url_edit)
        base_url_label.setVisible(not remote_mode)
        base_url_edit.setVisible(not remote_mode)
        layout.addLayout(base_url_layout)

        provider_hint = QLabel("Get an API key at https://aistudio.google.com/apikey")
        provider_hint.setObjectName("helperLabel")
        provider_hint.setWordWrap(True)
        provider_hint.setVisible(not remote_mode)
        layout.addWidget(provider_hint)

        def _toggle_visible(widget, visible):
            widget.setVisible(visible)

        def update_provider_fields():
            p = provider_combo.currentData()
            model_edit.setPlaceholderText("")
            is_ai = p != "google"
            is_google_ai_studio = p == "google_ai_studio"
            is_openai = p == "openai"
            is_google = p == "google"
            _toggle_visible(key_section_widget, is_google_ai_studio or is_openai)
            _toggle_visible(base_url_label, not remote_mode and is_ai)
            _toggle_visible(base_url_edit, not remote_mode and is_ai)
            _toggle_visible(test_btn, not remote_mode and is_ai)
            _toggle_visible(test_status, not remote_mode and is_ai)
            _toggle_visible(model_label, not remote_mode and is_ai)
            _toggle_visible(model_edit, not remote_mode and is_ai)
            _toggle_visible(polish_model_label, not remote_mode and (is_google_ai_studio or is_openai))
            _toggle_visible(polish_model_edit, not remote_mode and (is_google_ai_studio or is_openai))
            if is_google:
                provider_hint.setText("Free Google web translate, no API key needed. Lower quality than AI translation.")
                key_edit.clear()
                model_edit.clear()
                base_url_edit.clear()
            elif is_google_ai_studio:
                model_label.setText("AI Model:")
                key, model, base_url = _provider_values(p)
                key_edit.setText(key)
                model_edit.setText(model)
                base_url_edit.setText(base_url or "https://generativelanguage.googleapis.com/v1beta/openai/")
                if not model_edit.text().strip():
                    model_edit.setText("gemini-3.6-flash")
                polish_model_edit.setText(os.getenv("GOOGLE_AI_STUDIO_POLISH_MODEL", "") or "gemini-3.6-flash")
                provider_hint.setText("Use a Google AI Studio Gemini API key: https://aistudio.google.com/apikey")
            elif is_openai:
                model_label.setText("AI Model:")
                key, model, base_url = _provider_values(p)
                key_edit.setText(key)
                model_edit.setText(model)
                base_url_edit.setText(base_url or "https://api.openai.com/v1/")
                if not model_edit.text().strip():
                    model_edit.setText("gpt-4o-mini")
                polish_model_edit.setText(os.getenv("OPENAI_POLISH_MODEL", ""))
                provider_hint.setText("Get an API key at https://platform.openai.com/api-keys")
            elif p == "ollama":
                model_label.setText("AI Model:")
                base_url_edit.setText("http://localhost:11434/v1")
                key_edit.clear()
                model_edit.setText("gemma4:31b-cloud")
                provider_hint.setText("Requires a running Ollama server. Default model: gemma4:31b-cloud")
            model_edit.setReadOnly(False)
            dialog.layout().invalidate()
            dialog.adjustSize()

        test_btn = QPushButton("Test Connection", dialog)
        test_btn.setVisible(not remote_mode)
        test_status = QLabel("")
        test_status.setObjectName("helperLabel")
        test_status.setVisible(not remote_mode)
        test_row = QHBoxLayout()
        test_row.addWidget(test_btn)
        test_row.addWidget(test_status, 1)
        layout.addLayout(test_row)

        def test_ai_connection():
            url = base_url_edit.text().strip()
            provider = provider_combo.currentData()
            key = key_edit.text().strip() or ("ollama" if provider == "ollama" else "")
            model = model_edit.text().strip()
            if not url:
                test_status.setText("Enter a server URL first.")
                return
            if not key:
                test_status.setText("Enter an API key first.")
                return
            if not model:
                test_status.setText("Enter a model name first.")
                return
            test_status.setText("Testing...")
            test_status.repaint()
            try:
                from openai import OpenAI
                client = OpenAI(api_key=key, base_url=url, timeout=15.0)
                # A tiny completion validates the endpoint, credential, and the
                # selected model.  Some compatible APIs do not expose /models.
                client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "Reply with OK."}],
                    max_tokens=8,
                )
                test_status.setText(f"Connected: {model}")
            except Exception as e:
                if provider == "ollama":
                    self.log(f"[Ollama] Connection test failed: {e}")
                    test_status.setText("Unable to connect to Ollama. Please check your connection and settings.")
                else:
                    test_status.setText(f"Failed: {e}")

        test_btn.clicked.connect(test_ai_connection)

        provider_combo.currentIndexChanged.connect(update_provider_fields)
        update_provider_fields()

        def update_engine_fields():
            engine_val = engine_combo.currentData()
            is_ocr = engine_val == "ocr"
            is_whisper = engine_val == "whisper"
            _toggle_visible(whisper_title, is_whisper)
            _toggle_visible(whisper_combo, is_whisper)
            _toggle_visible(region_label, is_ocr)
            _toggle_visible(region_combo, is_ocr)
            _toggle_visible(sampling_label, is_ocr)
            _toggle_visible(sampling_combo, is_ocr)
            dialog.layout().invalidate()
            dialog.adjustSize()

        engine_combo.currentIndexChanged.connect(update_engine_fields)

        local_download_layout = QHBoxLayout()
        manage_resources_btn = QPushButton("Manage Resources", dialog)
        open_voices_folder_btn = QPushButton("Open Voices Folder", dialog)
        local_download_layout.addWidget(manage_resources_btn)
        local_download_layout.addWidget(open_voices_folder_btn)
        manage_resources_btn.setVisible(not remote_mode)
        open_voices_folder_btn.setVisible(not remote_mode)
        layout.addLayout(local_download_layout)

        def _piper_models_dir() -> str:
            return models_path("piper")

        def open_voices_folder():
            voices_dir = _piper_models_dir()
            os.makedirs(voices_dir, exist_ok=True)
            open_folder_impl(self, voices_dir)

        open_voices_folder_btn.clicked.connect(open_voices_folder)
        manage_resources_btn.clicked.connect(self.open_resource_manager_dialog)
        def _test_remote_connection():
            try:
                payload = self._test_remote_api_connection(
                    remote_url_edit.text().strip(),
                    remote_token_edit.text().strip(),
                )
                service_name = str(payload.get("service", "viustudio-remote-api") or "viustudio-remote-api")
                profile_name = str(payload.get("profile", "local") or "local")
                QMessageBox.information(
                    dialog,
                    "Remote API",
                    f"Connected successfully.\n\nService: {service_name}\nProfile: {profile_name}",
                )
            except Exception as exc:
                QMessageBox.warning(
                    dialog,
                    "Remote API",
                    f"Could not connect to the PC server.\n\n{exc}",
                )

        test_remote_btn.clicked.connect(_test_remote_connection)

        # Buttons
        button_row = QHBoxLayout()
        button_row.addStretch()
        cancel_btn = QPushButton("Cancel", dialog)
        save_btn = QPushButton("Save", dialog)
        button_row.addWidget(cancel_btn)
        button_row.addWidget(save_btn)
        layout.addLayout(button_row)

        cancel_btn.clicked.connect(dialog.reject)
        save_btn.clicked.connect(dialog.accept)

        # The subtitle is a top-level overlay above MPV's native surface.
        # Hide it for this modal dialog so it cannot paint over Settings.
        subtitle_item = getattr(getattr(self, "video_view", None), "subtitle_item", None)
        text_overlay = getattr(getattr(self, "video_view", None), "text_overlay", None)
        subtitle_was_visible = bool(subtitle_item is not None and subtitle_item.isVisible())
        if subtitle_item is not None:
            subtitle_item.set_suppressed(True)
        if text_overlay is not None:
            text_overlay.set_suppressed(True)
        dialog_result = dialog.exec()
        if dialog_result != QDialog.Accepted:
            if subtitle_item is not None:
                subtitle_item.set_suppressed(False)
            if text_overlay is not None:
                text_overlay.set_suppressed(False)
            if subtitle_was_visible and not getattr(self, "_preview_video_has_burned_subtitles", False):
                QTimer.singleShot(0, self.sync_live_subtitle_preview)
            return

        # Save Logic
        new_whisper = str(whisper_combo.currentData() or "small").strip().lower()
        new_engine = str(engine_combo.currentData() or "sensevoice").strip().lower()
        new_ocr_region = str(region_combo.currentData() or "bottom").strip().lower()
        new_ocr_sampling_fps = str(sampling_combo.currentData() or "auto").strip().lower()
        new_key = key_edit.text().strip()
        new_model = model_edit.text().strip()
        new_provider = str(provider_combo.currentData()).strip()
        new_base_url = base_url_edit.text().strip()
        new_polish_model = polish_model_edit.text().strip()

        self.selected_whisper_model_name = new_whisper

        # Transcription engine settings (apply to all modes)
        # The subtitle source is project-local.  Do not write it into .env,
        # otherwise opening another project can inherit a stale OCR/Audio
        # choice from an earlier session.
        _engine_updates = {
            "OCR_SUBTITLE_REGION": new_ocr_region,
            "OCR_SAMPLING_FPS": new_ocr_sampling_fps,
        }

        # Write back to .env
        env_lines = []
        if os.path.exists(".env"):
            with open(".env", "r", encoding="utf-8") as f:
                env_lines = f.readlines()

        if remote_mode:
            updates = {
                "VIUSTUDIO_REMOTE_API_URL": remote_url_edit.text().strip() or "http://127.0.0.1:8765",
                "VIUSTUDIO_REMOTE_API_TOKEN": remote_token_edit.text().strip(),
            }
        else:
            if new_provider == "google":
                updates = {
                    "AI_POLISHER_PROVIDER": "google",
                    "OPENAI_PROVIDER": "google",
                }
            elif new_provider == "google_ai_studio":
                updates = {
                    "AI_POLISHER_PROVIDER": "google_ai_studio",
                    "OPENAI_PROVIDER": "google_ai_studio",
                    "GOOGLE_AI_STUDIO_API_KEY": new_key,
                    "GOOGLE_AI_STUDIO_MODEL": new_model or "gemini-3.6-flash",
                    "GOOGLE_AI_STUDIO_POLISH_MODEL": new_polish_model or "gemini-3.6-flash",
                    "GOOGLE_AI_STUDIO_BASE_URL": new_base_url or "https://generativelanguage.googleapis.com/v1beta/openai/",
                }
            elif new_provider == "ollama":
                updates = {
                    "AI_POLISHER_PROVIDER": "ollama",
                    "OPENAI_PROVIDER": "ollama",
                    "OPENAI_API_KEY": "ollama",
                    "OPENAI_MODEL": new_model,
                    "OPENAI_BASE_URL": new_base_url or "http://localhost:11434/v1",
                }
            else:
                updates = {
                    "AI_POLISHER_PROVIDER": "openai",
                    "OPENAI_PROVIDER": "openai",
                    "OPENAI_API_KEY": new_key,
                    "OPENAI_MODEL": new_model or "gpt-4o-mini",
                    "OPENAI_POLISH_MODEL": new_polish_model,
                    "OPENAI_BASE_URL": new_base_url or "https://api.openai.com/v1/",
                }

        updates.update(_engine_updates)

        new_env_lines = []
        handled_keys = set()
        for line in env_lines:
            match = re.match(r"^([^=]+)=.*", line)
            if match:
                k = match.group(1).strip()
                if k == "TRANSCRIPTION_ENGINE":
                    # Legacy global cache: source selection now belongs to
                    # the active project and must not survive here.
                    continue
                if k in updates:
                    new_env_lines.append(f"{k}={updates[k]}\n")
                    handled_keys.add(k)
                    continue
            new_env_lines.append(line)

        for k, v in updates.items():
            if k not in handled_keys:
                new_env_lines.append(f"{k}={v}\n")

        with open(".env", "w", encoding="utf-8") as f:
            f.writelines(new_env_lines)

        # Update os.environ so it takes effect immediately in this session
        for k, v in updates.items():
            os.environ[k] = v

        self.set_project_transcription_engine(new_engine)
        self.save_user_settings()
        self._update_ocr_overlay()
        QMessageBox.information(self, "Success", "Settings saved and updated!")
        if subtitle_item is not None:
            subtitle_item.set_suppressed(False)
        if text_overlay is not None:
            text_overlay.set_suppressed(False)
        if subtitle_was_visible and not getattr(self, "_preview_video_has_burned_subtitles", False):
            QTimer.singleShot(0, self.sync_live_subtitle_preview)

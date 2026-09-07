import os

from PySide6.QtCore import QUrl, Qt, QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from runtime_paths import workspace_root as default_workspace_root
from services import ResourceDownloadService


_STATUS_STYLES = {
    "installed": ("Ready", "#6ee7b7", "#0d291e"),
    "partial":   ("Partial", "#fde047", "#2b220e"),
    "missing":   ("Missing", "#fca5a5", "#2a181e"),
}


def _status_pill_widget(status_key: str, parent: QWidget, label_override: str = "") -> QLabel:
    status = str(status_key or "").strip().lower()
    default_label, fg, bg = _STATUS_STYLES.get(status, _STATUS_STYLES["missing"])
    label = str(label_override or default_label).strip() or default_label
    pill = QLabel(label, parent)
    pill.setAlignment(Qt.AlignCenter)
    border_color = "#165b40" if status == "installed" else ("#715518" if status == "partial" else "#4f202a")
    pill.setStyleSheet(
        f"color: {fg}; background-color: {bg}; border: 1px solid {border_color};"
        f" border-radius: 6px; padding: 2px 10px; font-weight: 600; font-size: 11px;"
    )
    pill.setFixedHeight(22)
    return pill


def _open_url(url: str) -> bool:
    target = str(url or "").strip()
    if not target:
        return False
    return QDesktopServices.openUrl(QUrl(target))


def _open_folder_dialog(gui_parent, path: str) -> None:
    target = str(path or "").strip()
    if not target:
        return
    from PySide6.QtWidgets import QMessageBox
    try:
        os.makedirs(target, exist_ok=True)
        os.startfile(os.path.abspath(target))
    except Exception as exc:
        QMessageBox.critical(gui_parent, "Error", f"Could not open folder:\n{exc}")


def open_resource_manager(workspace_root: str = None, parent=None,
                          on_finished=None, focus_resource_id: str | None = None,
                          auto_start: bool = False, show: bool = True):
    if workspace_root is None:
        workspace_root = default_workspace_root()

    service = ResourceDownloadService(workspace_root)

    dialog = QDialog(parent)
    dialog.setWindowTitle("Manage Resources")
    dialog.setModal(True)
    dialog.resize(840, 600)
    dialog.setStyleSheet("""
        QDialog {
            background-color: #0c0e14;
            color: #e2e8f0;
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Inter', Roboto, Arial, sans-serif;
        }
        QLabel { color: #cbd5e1; background-color: transparent; font-size: 12px; }
        QLabel#resourceTitle { color: #f8fafc; font-size: 16px; font-weight: 700; }
        QLabel#resourceHint { color: #94a3b8; font-size: 12px; }
        QWidget#resourceContent { background-color: transparent; }
        QScrollArea { border: none; background-color: transparent; }
        QFrame#resourceCard { background-color: #141824; border: 1px solid #23293a; border-radius: 10px; }
        QFrame#resourceCardFocused { background-color: #162035; border: 2px solid #3b82f6; border-radius: 10px; }
        QPushButton {
            background-color: #1c2230; color: #e2e8f0; border: 1px solid #2b354a;
            border-radius: 6px; padding: 6px 14px; font-weight: 600; min-width: 80px; font-size: 11px;
        }
        QPushButton:hover { background-color: #262e42; border-color: #3b82f6; color: #ffffff; }
        QPushButton:disabled { color: #475569; background-color: #11141d; border-color: #1e2433; }
        QPushButton#primaryBtn {
            background-color: #10b981; color: #ffffff; border: 1px solid #059669;
            font-weight: 700;
        }
        QPushButton#primaryBtn:hover { background-color: #059669; }
        QProgressBar {
            min-height: 16px; max-height: 16px; border: 1px solid #334155;
            border-radius: 6px; background: #0f1420; color: #f8fafc;
            text-align: center; font-size: 10px; font-weight: 700;
        }
        QProgressBar::chunk { background-color: #10b981; border-radius: 5px; }
        QScrollBar:vertical {
            border: none;
            background: #0e1118;
            width: 8px;
            margin: 0px;
        }
        QScrollBar::handle:vertical {
            background: #252b3d;
            min-height: 24px;
            border-radius: 4px;
        }
        QScrollBar::handle:vertical:hover {
            background: #38425d;
        }
    """)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(12)

    title = QLabel("Manage Resources", dialog)
    title.setObjectName("resourceTitle")
    layout.addWidget(title)

    hint = QLabel(
        "Use Install for supported resources; VIUStudio downloads, extracts, and verifies them automatically. "
        "Manual download links and storage folders are kept for advanced or external resources.",
        dialog,
    )
    hint.setObjectName("resourceHint")
    hint.setWordWrap(True)
    layout.addWidget(hint)

    scroll = QScrollArea(dialog)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    layout.addWidget(scroll, 1)

    content = QWidget(dialog)
    content.setObjectName("resourceContent")
    content_layout = QVBoxLayout(content)
    content_layout.setContentsMargins(0, 0, 0, 0)
    content_layout.setSpacing(10)
    scroll.setWidget(content)

    dialog._resource_rows = {}

    def _show_status_pill(row, status_key: str, status_label: str = ""):
        new_pill = _status_pill_widget(status_key, dialog, status_label)
        row["header_row"].replaceWidget(row["status_pill"], new_pill)
        row["status_pill"].deleteLater()
        row["status_pill"] = new_pill
        row["status_pill"].show()

    dialog._download_workers = {}

    def _start_resource_install(resource_id: str):
        row = dialog._resource_rows.get(resource_id)
        item = row.get("item", {}) if row else {}
        if not row or str(item.get("status", "")).lower() == "installed":
            return
        if resource_id in dialog._download_workers:
            return
        from ui.worker_adapters.processing_workers import ResourceDownloadWorker
        from utils.thread_lifecycle import release_thread_when_stopped
        worker = ResourceDownloadWorker(workspace_root, resource_id)
        worker.setParent(dialog)

        dialog._download_workers[resource_id] = worker
        close_button = getattr(dialog, "_resource_close_btn", None)
        if close_button is not None:
            close_button.setEnabled(False)
        install_btn = row.get("install_btn")
        if install_btn is not None:
            install_btn.setEnabled(False)
            install_btn.setText("Installing…")
        progress_label = row.get("progress_label")
        progress_bar = row.get("progress_bar")
        if progress_bar is not None:
            progress_bar.setRange(0, 100)
            progress_bar.setValue(0)
            progress_bar.setFormat("0%")
            progress_bar.show()

        def _on_progress(percent: int, message: str):
            if progress_label is not None:
                progress_label.setText(str(message))
            if progress_bar is not None:
                if percent >= 0:
                    progress_bar.setRange(0, 100)
                    progress_bar.setValue(max(0, min(100, percent)))
                    progress_bar.setFormat(f"{max(0, min(100, percent))}%")
                else:
                    progress_bar.setRange(0, 0)
                    progress_bar.setFormat("Working…")

        def _on_finished(done_id: str, error: str):
            verified = not error and service.is_resource_installed(done_id)
            if error or not verified:
                message = str(error).splitlines()[0] if error else "Installation finished but verification failed."
                if progress_label is not None:
                    progress_label.setText("Install failed: " + message)
                if progress_bar is not None:
                    progress_bar.setRange(0, 100)
                    progress_bar.setFormat("Failed")
                if install_btn is not None:
                    install_btn.setEnabled(True)
                    install_btn.setText("Retry")
            else:
                if progress_label is not None:
                    progress_label.setText("Installed and verified.")
                if progress_bar is not None:
                    progress_bar.setRange(0, 100)
                    progress_bar.setValue(100)
                    progress_bar.setFormat("100%")
                if install_btn is not None:
                    install_btn.setEnabled(False)
                    install_btn.setText("Installed")
                _refresh()
            def _release_row_worker():
                dialog._download_workers.pop(resource_id, None)
                close_button = getattr(dialog, "_resource_close_btn", None)
                if close_button is not None:
                    close_button.setEnabled(not dialog._download_workers)

            release_thread_when_stopped(worker, on_released=_release_row_worker)

        worker.progress.connect(_on_progress)
        worker.finished.connect(_on_finished)
        worker.start()

    def _add_card(item, target_layout):
        card = QFrame(dialog)
        card.setObjectName("resourceCard")
        outer = QVBoxLayout(card)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        name_label = QLabel(str(item.get("name", item.get("id", "Resource"))), dialog)
        name_label.setStyleSheet("color: #f8fbff; font-weight: 700; font-size: 14px; background-color: transparent;")
        header_row.addWidget(name_label, 1)

        required_for = str(item.get("required_for", "") or "").strip()
        if required_for:
            required_label = QLabel(f"Required for {required_for}", dialog)
            required_label.setStyleSheet(
                "color: #ffd28a; font-size: 10px; font-weight: 700; "
                "background-color: #4a3520; border: 1px solid #8b6734; "
                "border-radius: 6px; padding: 2px 6px;"
            )
            header_row.addWidget(required_label, 0, Qt.AlignVCenter)

        status_pill = _status_pill_widget(
            item.get("status", "missing"),
            dialog,
            item.get("status_label", ""),
        )
        header_row.addWidget(status_pill, 0, Qt.AlignVCenter | Qt.AlignRight)

        outer.addLayout(header_row)

        description = str(item.get("description", "")).strip()
        if description:
            desc_label = QLabel(description, dialog)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("color: #c0d0e3; font-size: 12px; background-color: transparent;")
            outer.addWidget(desc_label)

        target_dir = str(item.get("target_dir", "")).strip()
        if target_dir:
            path_row = QHBoxLayout()
            path_row.setSpacing(6)
            path_label = QLabel("Target folder:", dialog)
            path_label.setStyleSheet("color: #8ea3bb; font-size: 11px; background-color: transparent;")
            path_value = QLabel(target_dir, dialog)
            path_value.setStyleSheet("color: #d7e3f4; font-size: 11px; font-family: monospace; background-color: transparent;")
            path_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            path_value.setWordWrap(True)
            path_row.addWidget(path_label, 0)
            path_row.addWidget(path_value, 1)
            outer.addLayout(path_row)

        expected = str(item.get("expected_filename", "")).strip()
        if expected:
            file_row = QHBoxLayout()
            file_row.setSpacing(6)
            file_caption = QLabel("Expected file:", dialog)
            file_caption.setStyleSheet("color: #8ea3bb; font-size: 11px; background-color: transparent;")
            file_value = QLabel(expected, dialog)
            file_value.setStyleSheet("color: #d7e3f4; font-size: 11px; font-family: monospace; background-color: transparent;")
            file_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            file_value.setWordWrap(True)
            file_row.addWidget(file_caption, 0)
            file_row.addWidget(file_value, 1)
            outer.addLayout(file_row)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        button_row.addStretch(1)

        install_btn = None
        progress_label = QLabel("", dialog)
        progress_label.setStyleSheet("color: #8ea3bb; font-size: 10px; background: transparent;")
        progress_label.setWordWrap(True)
        progress_bar = QProgressBar(dialog)
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        progress_bar.setFormat("0%")
        progress_bar.hide()
        if bool(item.get("auto_download_supported")) and str(item.get("status", "")).lower() != "installed":
            install_btn = QPushButton("Install", dialog)
            install_btn.setObjectName("primaryBtn")
            install_btn.clicked.connect(
                lambda _checked=False, rid=item["id"]: _start_resource_install(rid)
            )
            button_row.addWidget(install_btn)

        # Most resources have one archive/download page.  SenseVoice is
        # intentionally represented as two direct files, so let resource
        # definitions expose separate buttons instead of making users find
        # the required pair themselves on Hugging Face.
        download_links = item.get("download_links") or []
        if download_links and install_btn is None and str(item.get("status", "")).lower() != "installed":
            for link in download_links:
                if not isinstance(link, dict):
                    continue
                label = str(link.get("label", "Download")).strip() or "Download"
                url = str(link.get("url", "")).strip()
                download_btn = QPushButton(label, dialog)
                download_btn.setObjectName("primaryBtn")
                download_btn.setEnabled(bool(url))
                if url:
                    download_btn.setToolTip(url)
                download_btn.clicked.connect(
                    lambda _checked=False, target_url=url: _open_url(target_url)
                )
                button_row.addWidget(download_btn)
        elif not install_btn:
            download_url = str(item.get("download_url", "")).strip()
            download_btn = QPushButton("Open Download Page", dialog)
            download_btn.setObjectName("primaryBtn")
            download_btn.setEnabled(bool(download_url))
            if download_url:
                download_btn.setToolTip(download_url)
            download_btn.clicked.connect(
                lambda _checked=False, url=download_url: _open_url(url)
            )
            button_row.addWidget(download_btn)

        open_folder_btn = QPushButton("Open Storage Folder", dialog)
        open_folder_btn.setEnabled(bool(target_dir))
        open_folder_btn.clicked.connect(
            lambda _checked=False, p=target_dir: _open_folder_dialog(dialog, p)
        )
        button_row.addWidget(open_folder_btn)

        outer.addLayout(button_row)
        if install_btn is not None:
            outer.addWidget(progress_label)
            outer.addWidget(progress_bar)

        target_layout.addWidget(card)
        dialog._resource_rows[item["id"]] = {
            "card": card,
            "item": item,
            "name_label": name_label,
            "status_pill": status_pill,
            "header_row": header_row,
            "install_btn": install_btn,
            "progress_label": progress_label,
            "progress_bar": progress_bar,
        }

    def _make_section(title_text, expanded):
        wrapper = QFrame()
        wrapper.setObjectName("statusCard")
        wrapper.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(8, 2, 8, 2)
        wrapper_layout.setSpacing(0)

        btn = QToolButton()
        btn.setText(("▼ " if expanded else "▶ ") + title_text)
        btn.setCheckable(True)
        btn.setChecked(expanded)
        btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        btn.setStyleSheet("QToolButton { text-align: left; font-weight: 700; color: #8ad7ff; border: none; padding: 2px 4px; margin: 0; }")

        inner = QWidget()
        inner.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 4)
        inner_layout.setSpacing(2)
        inner.setVisible(expanded)
        if not expanded:
            inner.setMaximumHeight(0)

        btn.toggled.connect(lambda c: (
            btn.setText(("▼ " if c else "▶ ") + title_text),
            inner.setVisible(c),
            inner.setMaximumHeight(16777215 if c else 0),
        ))
        wrapper_layout.addWidget(btn)
        wrapper_layout.addWidget(inner)
        return wrapper, inner_layout, btn

    def _refresh():
        resources = {item["id"]: item for item in service.list_resources()}
        for resource_id, row in dialog._resource_rows.items():
            item = resources.get(resource_id, row.get("item", {}))
            row["item"] = item
            status = str(item.get("status", "missing")).strip().lower()
            _show_status_pill(row, status, str(item.get("status_label", "") or ""))
            install_btn = row.get("install_btn")
            if install_btn is not None and resource_id not in dialog._download_workers:
                installed = status == "installed"
                install_btn.setEnabled(not installed)
                install_btn.setText("Installed" if installed else "Install")

    def _populate():
        for i in reversed(range(content_layout.count())):
            it = content_layout.takeAt(i)
            widget = it.widget() if it is not None else None
            if widget is not None:
                widget.deleteLater()
        dialog._resource_rows = {}

        resources = service.list_resources()
        preview_items = [r for r in resources if r.get("kind") == "preview"]
        cpu_items = [r for r in resources if r.get("kind") in {"sensevoice", "whisper_cpu"}]
        audio_items = [r for r in resources if r.get("kind") in {"separation", "diarization"}]
        gpu_kinds = {"ai", "whisper", "cuda"}
        gpu_items = [r for r in resources if r.get("kind") in gpu_kinds]
        llama_items = [r for r in resources if r.get("kind") == "llama"]
        voice_items = [r for r in resources if r.get("kind") == "voice"]

        seen_ids = {r.get("id") for r in (preview_items + cpu_items + audio_items + gpu_items + llama_items + voice_items)}
        other_items = [r for r in resources if r.get("id") not in seen_ids]

        if preview_items:
            preview_expand = any(
                r.get("id") == focus_resource_id or r.get("status") != "installed"
                for r in preview_items
            )
            preview_card, preview_layout, _ = _make_section(
                "Preview Runtime",
                expanded=preview_expand,
            )
            for item in preview_items:
                _add_card(item, preview_layout)
            content_layout.addWidget(preview_card)

        if cpu_items:
            cpu_card, cpu_layout, _ = _make_section("CPU Speech & Transcription Models", expanded=True)
            for item in cpu_items:
                _add_card(item, cpu_layout)
            content_layout.addWidget(cpu_card)

        if audio_items:
            audio_expand = True
            audio_card, audio_layout, _ = _make_section(
                "Audio & Separation Models (Tách Nhạc / Giọng & Diarization)",
                expanded=audio_expand,
            )
            for item in audio_items:
                _add_card(item, audio_layout)
            content_layout.addWidget(audio_card)

        if gpu_items:
            gpu_expand = any(r.get("id") == focus_resource_id for r in gpu_items)
            gpu_card, gpu_layout, _ = _make_section("GPU Acceleration Resource", expanded=gpu_expand)
            for item in gpu_items:
                _add_card(item, gpu_layout)
            content_layout.addWidget(gpu_card)

        if llama_items:
            llama_expand = any(r.get("id") == focus_resource_id for r in llama_items)
            llama_card, llama_layout, _ = _make_section(
                "LLM & Language Models (AI Viết Kịch Bản / Llama)",
                expanded=llama_expand,
            )
            for item in llama_items:
                _add_card(item, llama_layout)
            content_layout.addWidget(llama_card)

        if voice_items:
            voice_card, voice_layout, _ = _make_section(
                "Voice & TTS Models (Giọng Đọc - Piper & ZeroTTS)",
                expanded=True,
            )
            for item in voice_items:
                _add_card(item, voice_layout)
            content_layout.addWidget(voice_card)

        if other_items:
            other_card, other_layout, _ = _make_section("Other Resources", expanded=True)
            for item in other_items:
                _add_card(item, other_layout)
            content_layout.addWidget(other_card)

        content_layout.addStretch()

        if focus_resource_id and focus_resource_id in dialog._resource_rows:
            row = dialog._resource_rows[focus_resource_id]
            card = row.get("card")
            if card is not None:
                card.setObjectName("resourceCardFocused")
                card.setStyleSheet(
                    "QFrame#resourceCard, QFrame#resourceCardFocused { "
                    "background-color: #172338; "
                    "border: 2px solid #3b82f6; "
                    "border-radius: 10px; "
                    "}"
                )
                QTimer.singleShot(120, lambda c=card: scroll.ensureWidgetVisible(c, 50, 50))
            if auto_start:
                QTimer.singleShot(250, lambda rid=focus_resource_id: _start_resource_install(rid))

    _populate()

    footer_row = QHBoxLayout()
    footer_row.setSpacing(8)
    footer_hint = QLabel(
        "Tip: start with Setup & Resources for a guided first-time installation.",
        dialog,
    )
    footer_hint.setObjectName("resourceHint")
    footer_hint.setWordWrap(True)
    footer_row.addWidget(footer_hint, 1)

    refresh_btn = QPushButton("Refresh", dialog)
    refresh_btn.clicked.connect(_refresh)
    footer_row.addWidget(refresh_btn)

    close_btn = QPushButton("Close", dialog)
    dialog._resource_close_btn = close_btn
    close_btn.clicked.connect(dialog.accept)
    footer_row.addWidget(close_btn)

    layout.addLayout(footer_row)

    def _on_dialog_closed():
        if on_finished:
            try:
                on_finished()
            except Exception:
                pass

    dialog.accepted.connect(_on_dialog_closed)
    dialog.rejected.connect(_on_dialog_closed)
    if show:
        dialog.exec()
    return dialog

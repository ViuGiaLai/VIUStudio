from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from app.services.auto_recap_engine import AutoRecapConfig, AutoRecapEngine, ShotDecision
from ui.dialogs.auto_recap_dialog import AutoRecapSettingsDialog


class AutoRecapFeatureMixin:
    """Mixin class providing UI integration and feature actions for VIUStudio Auto Edit Recap."""

    def init_auto_recap_feature(self):
        """Initializes default Auto Recap configuration and EDL decision state."""
        if not hasattr(self, "auto_recap_config") or self.auto_recap_config is None:
            self.auto_recap_config = AutoRecapConfig()
        if not hasattr(self, "current_auto_recap_edl"):
            self.current_auto_recap_edl: List[ShotDecision] = []

    def open_auto_recap_settings_dialog(self):
        """Tier 2 UI: Opens the 12 Rules Customization Modal."""
        self.init_auto_recap_feature()
        dialog = AutoRecapSettingsDialog(self.auto_recap_config, parent=self)
        if dialog.exec():
            self.auto_recap_config = dialog.config
            if hasattr(self, "log"):
                self.log(
                    f"[Auto Recap] Configuration updated: Style={self.auto_recap_config.editing_style}, "
                    f"Flip={self.auto_recap_config.allow_horizontal_flip}, Speed={self.auto_recap_config.allow_speed_change}"
                )

    def run_auto_recap_workflow(self):
        """Action for running Auto Edit Recap from the Generate dropdown menu."""
        self.init_auto_recap_feature()
        if hasattr(self, "auto_recap_cb"):
            self.auto_recap_cb.setChecked(True)
        if hasattr(self, "anti_duplicate_cb") and self.anti_duplicate_cb.isChecked():
            if hasattr(self, "auto_recap_config") and self.auto_recap_config:
                self.auto_recap_config.anti_duplicate = True
        if hasattr(self, "log"):
            self.log("[Auto Recap] Bắt đầu phân tích cảnh và tạo video chống trùng lặp / Recap...")
        if hasattr(self, "pipeline_controller") and hasattr(self.pipeline_controller, "run_auto_recap_pipeline"):
            self.pipeline_controller.run_auto_recap_pipeline()
        elif hasattr(self, "run_auto_recap_pipeline"):
            self.run_auto_recap_pipeline()
        else:
            if hasattr(self, "log"):
                self.log("[Auto Recap] Lỗi: Không tìm thấy pipeline_controller.run_auto_recap_pipeline")

    def run_auto_recap_pipeline(self, video_path=None):
        """Delegates Auto Recap execution to pipeline_controller."""
        if hasattr(self, "pipeline_controller") and hasattr(self.pipeline_controller, "run_auto_recap_pipeline"):
            return self.pipeline_controller.run_auto_recap_pipeline(video_path=video_path)
        return None

    def open_video_compare_dialog(self):
        """Opens the Side-by-Side Video Comparison Dialog (Original vs Protected)."""
        from ui.dialogs.video_compare_dialog import VideoCompareDialog
        from PySide6.QtWidgets import QMessageBox

        orig_path = ""
        if hasattr(self, "resolve_canonical_video_path") and callable(self.resolve_canonical_video_path):
            orig_path = self.resolve_canonical_video_path() or ""
        if not orig_path and hasattr(self, "video_path_edit"):
            orig_path = str(self.video_path_edit.text() or "").strip()
        if not orig_path and hasattr(self, "pipeline_controller"):
            orig_path = self.pipeline_controller._resolve_pipeline_video_path()

        recap_path = str(getattr(self, "last_recap_video_path", "") or "").strip()
        if not recap_path or not os.path.exists(recap_path):
            QMessageBox.information(
                self,
                "So sánh Video",
                "Chưa có video đã xử lý chống trùng lặp. Vui lòng bấm '⚡ Phân tích && Tạo video Chống trùng' trước khi so sánh."
            )
            return

        if not orig_path or not os.path.exists(orig_path):
            possible = recap_path.replace("_recap.mp4", ".mp4")
            if os.path.exists(possible):
                orig_path = possible

        decisions = getattr(self, "current_auto_recap_edl", []) or []
        dialog = VideoCompareDialog(orig_path, recap_path, decisions, parent=self)
        dialog.exec()

    def is_auto_recap_enabled(self) -> bool:
        self.init_auto_recap_feature()
        if hasattr(self, "auto_recap_cb"):
            return self.auto_recap_cb.isChecked()
        return self.auto_recap_config.enabled

    def run_auto_recap_processing(self, segments: Optional[List[Dict[str, Any]]] = None, scenes: Optional[List[Dict[str, Any]]] = None) -> List[ShotDecision]:
        """Runs the 12 Core Rules Engine to produce EDL decisions during generation."""
        self.init_auto_recap_feature()

        if not self.is_auto_recap_enabled():
            if hasattr(self, "log"):
                self.log("[Auto Recap] Engine disabled by user settings. Skipping Auto Recap EDL.")
            return []

        if segments is not None:
            input_segments = segments
        elif hasattr(self, "get_active_segments"):
            # Prefer the text the user is actually previewing/editing (usually
            # translated text) over a stale raw transcript.
            input_segments = list(self.get_active_segments() or [])
        else:
            input_segments = list(getattr(self, "current_translated_segments", []) or getattr(self, "current_segments", []) or [])
        input_scenes = list(scenes or []) if scenes is not None else None
        video_path = str(getattr(self.video_path_edit, "text", lambda: "")() or "").strip() if hasattr(self, "video_path_edit") else ""
        timeline_clips = self.get_timeline_video_clips(existing_only=True) if hasattr(self, "get_timeline_video_clips") else []

        engine = AutoRecapEngine(self.auto_recap_config)
        if input_scenes is None and timeline_clips:
            input_scenes = []
            for clip in timeline_clips:
                detected = engine.detect_scenes_ffmpeg(str(clip["source"]), threshold=0.25)
                source_start = float(clip.get("source_start", 0.0) or 0.0)
                source_end = source_start + float(clip.get("source_duration", 0.0) or 0.0)
                timeline_start = float(clip.get("timeline_start", 0.0) or 0.0)
                speed = max(0.01, float(clip.get("speed", 1.0) or 1.0))
                for scene in detected:
                    start = max(source_start, float(scene.get("start", 0.0) or 0.0))
                    end = min(source_end, float(scene.get("end", 0.0) or 0.0))
                    if end > start:
                        item = dict(scene)
                        item["start"] = timeline_start + (start - source_start) / speed
                        item["end"] = timeline_start + (end - source_start) / speed
                        input_scenes.append(item)
        elif input_scenes is None and video_path and os.path.exists(video_path):
            if hasattr(self, "log"):
                self.log(f"[Auto Recap] Detecting effect boundaries for video: {video_path}")
            input_scenes = engine.detect_scenes_ffmpeg(video_path, threshold=0.25)
            if hasattr(self, "log"):
                self.log(f"[Auto Recap] Detected {len(input_scenes)} scenes for Auto Recap EDL.")

        if input_scenes:
            input_scenes = engine.apply_subtitles_to_scenes(input_scenes, input_segments)

        if not input_segments and not input_scenes:
            if hasattr(self, "log"):
                self.log("[Auto Recap] Warning: No segments or scenes found for Auto Recap EDL.")
            return []

        engine = AutoRecapEngine(self.auto_recap_config)
        decisions = engine.generate_edl(input_segments, input_scenes)
        self.current_auto_recap_edl = decisions

        if hasattr(self, "persist_auto_recap_project_data"):
            self.persist_auto_recap_project_data(decisions)

        if hasattr(self, "log"):
            self.log(f"[Auto Recap] Generated EDL with {len(decisions)} shot decisions using 12 Core Rules.")
            for d in decisions[:3]:
                self.log(f"  • Shot {d.shot_index + 1}: {d.recap_notes} (Zoom: {d.zoom_scale}x, Flip: {d.horizontal_flip})")

        return decisions

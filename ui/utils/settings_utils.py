import os


def save_user_settings(gui):
    s = gui.settings
    
    # Media / Output
    if hasattr(gui, "output_mode_combo"):
        s.setValue("output_mode", gui.output_mode_combo.currentText())
    if hasattr(gui, "output_quality_combo"):
        s.setValue("output_quality", gui.output_quality_combo.currentText())
    if hasattr(gui, "output_fps_combo"):
        s.setValue("output_fps", gui.output_fps_combo.currentText())
    if hasattr(gui, "output_ratio_combo"):
        s.setValue("output_ratio", gui.output_ratio_combo.currentText())
    if hasattr(gui, "output_scale_mode_combo"):
        s.setValue("output_scale_mode", gui.output_scale_mode_combo.currentText())

    # Audio
    if hasattr(gui, "audio_handling_combo"):
        s.setValue("audio_handling_mode", gui.audio_handling_combo.currentData() or gui.audio_handling_combo.currentText())

    # Language
    if hasattr(gui, "lang_whisper_combo"):
        s.setValue("source_lang", gui.lang_whisper_combo.currentText())
    if hasattr(gui, "lang_target_combo"):
        s.setValue("target_lang", gui.lang_target_combo.currentData() or gui.lang_target_combo.currentText())
    if hasattr(gui, "translation_engine_combo"):
        s.setValue("translation_engine", gui.translation_engine_combo.currentData() or gui.translation_engine_combo.currentText())
    if hasattr(gui, "llama_model_combo"):
        s.setValue("llama_app_model", gui.llama_model_combo.currentData() or "")
    if hasattr(gui, "translation_style_preset_combo"):
        s.setValue("translation_style_preset", gui.translation_style_preset_combo.currentData() or gui.translation_style_preset_combo.currentText())

    # Voice
    if hasattr(gui, "voice_engine_combo"):
        s.setValue("voice_engine", gui.voice_engine_combo.currentData() or gui.voice_engine_combo.currentText())
    if hasattr(gui, "free_voice_combo"):
        s.setValue("free_voice_name", gui.free_voice_combo.currentText())
    if hasattr(gui, "voice_gender_combo"):
        s.setValue("voice_gender", gui.voice_gender_combo.currentText())
    if hasattr(gui, "voice_speed_spin"):
        s.setValue("voice_speed", gui.voice_speed_spin.currentText())
    if hasattr(gui, "voice_timing_sync_combo"):
        s.setValue("voice_timing_sync_mode", gui.voice_timing_sync_combo.currentText())

    # Paths & Models
    s.setValue("whisper_model_name", getattr(gui, "selected_whisper_model_name", "auto"))
    if hasattr(gui, "final_output_folder_edit"):
        s.setValue("final_output_folder", gui.final_output_folder_edit.text())
    if hasattr(gui, "audio_folder_edit"):
        s.setValue("audio_folder", gui.audio_folder_edit.text())
    if hasattr(gui, "srt_output_folder_edit"):
        s.setValue("srt_output_folder", gui.srt_output_folder_edit.text())
    if hasattr(gui, "voice_output_folder_edit"):
        s.setValue("voice_output_folder", gui.voice_output_folder_edit.text())
    if hasattr(gui, "audio_source_edit"):
        s.setValue("audio_source", gui.audio_source_edit.text())
    if hasattr(gui, "bg_music_edit"):
        s.setValue("background_audio", gui.bg_music_edit.text())
    if hasattr(gui, "mixed_audio_edit"):
        s.setValue("mixed_audio", gui.mixed_audio_edit.text())

    # Advanced
    if hasattr(gui, "speaker_diarization_cb"):
        s.setValue("speaker_diarization", gui.speaker_diarization_cb.isChecked())
    if hasattr(gui, "speaker_diarization_speakers_combo"):
        s.setValue("speaker_diarization_num_speakers", gui.speaker_diarization_speakers_combo.currentData())
    if hasattr(gui, "anchor_inspector_cb"):
        s.setValue("anchor_inspector", gui.anchor_inspector_cb.isChecked())
    if hasattr(gui, "auto_preview_frame_cb"):
        s.setValue("auto_preview_frame", gui.auto_preview_frame_cb.isChecked())
    if hasattr(gui, "ai_dubbing_rewrite_cb"):
        s.setValue("ai_dubbing_rewrite", gui.ai_dubbing_rewrite_cb.isChecked())
    if hasattr(gui, "subtitle_single_line_cb"):
        s.setValue("subtitle_single_line", gui.subtitle_single_line_cb.isChecked())
    if hasattr(gui, "subtitle_words_per_segment_spin"):
        s.setValue("subtitle_words_per_segment", gui.subtitle_words_per_segment_spin.value())
    if hasattr(gui, "toggle_advanced_btn"):
        s.setValue("advanced_section_open", gui.toggle_advanced_btn.isChecked())


def load_user_settings(gui):
    s = gui.settings
    
    # Media / Output
    saved_output_mode = s.value("output_mode", None)
    if saved_output_mode and hasattr(gui, "output_mode_combo"):
        idx = gui.output_mode_combo.findText(saved_output_mode)
        if idx >= 0:
            gui.output_mode_combo.setCurrentIndex(idx)
    elif hasattr(gui, "output_mode_combo"):
        gui.output_mode_combo.setCurrentText("Vietnamese subtitles + voice")

    if hasattr(gui, "output_quality_combo"):
        saved_q = s.value("output_quality", None)
        if saved_q:
            idx = gui.output_quality_combo.findText(saved_q)
            if idx >= 0:
                gui.output_quality_combo.setCurrentIndex(idx)

    if hasattr(gui, "output_fps_combo"):
        saved_fps = s.value("output_fps", None)
        if saved_fps:
            idx = gui.output_fps_combo.findText(saved_fps)
            if idx >= 0:
                gui.output_fps_combo.setCurrentIndex(idx)

    if hasattr(gui, "output_ratio_combo"):
        saved_ratio = s.value("output_ratio", None)
        if saved_ratio:
            idx = gui.output_ratio_combo.findText(saved_ratio)
            if idx >= 0:
                gui.output_ratio_combo.setCurrentIndex(idx)

    if hasattr(gui, "output_scale_mode_combo"):
        saved_scale = s.value("output_scale_mode", None)
        if saved_scale:
            idx = gui.output_scale_mode_combo.findText(saved_scale)
            if idx >= 0:
                gui.output_scale_mode_combo.setCurrentIndex(idx)

    # Audio
    saved_audio_mode = s.value("audio_handling_mode", None)
    if saved_audio_mode and hasattr(gui, "audio_handling_combo"):
        idx = gui.audio_handling_combo.findData(saved_audio_mode)
        if idx < 0:
            idx = gui.audio_handling_combo.findText(saved_audio_mode)
        if idx >= 0:
            gui.audio_handling_combo.setCurrentIndex(idx)

    # Language
    source_lang = s.value("source_lang", None)
    if source_lang and hasattr(gui, "lang_whisper_combo"):
        source_index = gui.lang_whisper_combo.findText(source_lang)
        if source_index < 0:
            source_index = gui.lang_whisper_combo.findData(source_lang)
        if source_index >= 0:
            gui.lang_whisper_combo.setCurrentIndex(source_index)

    target_lang = s.value("target_lang", None)
    if target_lang and hasattr(gui, "lang_target_combo"):
        idx = gui.lang_target_combo.findData(target_lang)
        if idx < 0:
            idx = gui.lang_target_combo.findText(target_lang)
        if idx >= 0:
            gui.lang_target_combo.setCurrentIndex(idx)

    llama_model = ""
    if hasattr(gui, "_llama_model_from_env_file"):
        llama_model = str(gui._llama_model_from_env_file() or "").strip()
    if not llama_model:
        llama_model = str(s.value("llama_app_model", "") or "").strip()
    if llama_model:
        os.environ["LLAMA_APP_MODEL"] = llama_model
        s.setValue("llama_app_model", llama_model)
    trans_engine = s.value("translation_engine", None)
    if trans_engine and hasattr(gui, "translation_engine_combo"):
        idx = gui.translation_engine_combo.findData(trans_engine)
        if idx < 0:
            idx = gui.translation_engine_combo.findText(trans_engine)
        if idx >= 0:
            gui.translation_engine_combo.setCurrentIndex(idx)

    trans_style = s.value("translation_style_preset", None)
    if trans_style and hasattr(gui, "translation_style_preset_combo"):
        idx = gui.translation_style_preset_combo.findData(trans_style)
        if idx < 0:
            idx = gui.translation_style_preset_combo.findText(trans_style)
        if idx >= 0:
            gui.translation_style_preset_combo.setCurrentIndex(idx)

    # Voice
    voice_engine = s.value("voice_engine", "fast")
    if voice_engine and hasattr(gui, "voice_engine_combo"):
        idx = gui.voice_engine_combo.findData(voice_engine)
        if idx < 0:
            idx = gui.voice_engine_combo.findText(voice_engine)
        if idx >= 0:
            gui.voice_engine_combo.setCurrentIndex(idx)

    saved_gender = s.value("voice_gender", "Female")
    if saved_gender and hasattr(gui, "voice_gender_combo"):
        idx = gui.voice_gender_combo.findText(saved_gender)
        if idx >= 0:
            gui.voice_gender_combo.setCurrentIndex(idx)

    saved_voice = s.value("free_voice_name", "Ngọc Huyền (New) (Local)")
    if saved_voice and hasattr(gui, "free_voice_combo"):
        idx = gui.free_voice_combo.findText(saved_voice)
        if idx < 0:
            idx = gui.free_voice_combo.findData(saved_voice)
        if idx >= 0:
            gui.free_voice_combo.setCurrentIndex(idx)


    saved_speed = s.value("voice_speed", None)
    if saved_speed and hasattr(gui, "voice_speed_spin"):
        gui.voice_speed_spin.setCurrentText(str(saved_speed))

    saved_sync = s.value("voice_timing_sync_mode", None)
    if saved_sync and hasattr(gui, "voice_timing_sync_combo"):
        idx = gui.voice_timing_sync_combo.findText(saved_sync)
        if idx >= 0:
            gui.voice_timing_sync_combo.setCurrentIndex(idx)
        if hasattr(gui, "timeline") and gui.timeline is not None:
            gui.timeline.set_voice_sync_mode(saved_sync)

    # Whisper model
    gui.selected_whisper_model_name = str(
        s.value("whisper_model_name", getattr(gui, "selected_whisper_model_name", "auto")) or "auto"
    ).strip().lower()
    small_model_dir = os.path.join(gui.workspace_root, "models", "faster_whisper", "small")
    if gui.selected_whisper_model_name == "medium" and os.path.isdir(small_model_dir):
        gui.selected_whisper_model_name = "auto"

    # Paths
    if hasattr(gui, "final_output_folder_edit"):
        gui.final_output_folder_edit.setText(s.value("final_output_folder", gui.final_output_folder_edit.text()))
    if hasattr(gui, "audio_folder_edit"):
        gui.audio_folder_edit.setText(s.value("audio_folder", gui.audio_folder_edit.text()))
    if hasattr(gui, "srt_output_folder_edit"):
        gui.srt_output_folder_edit.setText(s.value("srt_output_folder", gui.srt_output_folder_edit.text()))
    if hasattr(gui, "voice_output_folder_edit"):
        gui.voice_output_folder_edit.setText(s.value("voice_output_folder", gui.voice_output_folder_edit.text()))
    if hasattr(gui, "audio_source_edit"):
        gui.audio_source_edit.setText(s.value("audio_source", gui.audio_source_edit.text()))
    if hasattr(gui, "bg_music_edit"):
        gui.bg_music_edit.setText(s.value("background_audio", gui.bg_music_edit.text()))
    if hasattr(gui, "mixed_audio_edit"):
        gui.mixed_audio_edit.setText(s.value("mixed_audio", gui.mixed_audio_edit.text()))

    # Advanced
    if hasattr(gui, "speaker_diarization_cb"):
        diar_enabled = str(s.value("speaker_diarization", "false")).lower() == "true"
        gui.speaker_diarization_cb.setChecked(diar_enabled)
        if hasattr(gui, "update_speaker_diarization_availability"):
            gui.update_speaker_diarization_availability()

    if hasattr(gui, "speaker_diarization_speakers_combo"):
        saved_spk_count = s.value("speaker_diarization_num_speakers", -1)
        try:
            saved_spk_count = int(saved_spk_count)
        except Exception:
            saved_spk_count = -1
        idx = gui.speaker_diarization_speakers_combo.findData(saved_spk_count)
        if idx >= 0:
            gui.speaker_diarization_speakers_combo.setCurrentIndex(idx)

    if hasattr(gui, "anchor_inspector_cb"):
        gui.anchor_inspector_cb.setChecked(
            str(s.value("anchor_inspector", gui.anchor_inspector_cb.isChecked())).lower() == "true"
        )
    auto_preview_enabled = str(s.value("auto_preview_frame", "false")).lower() == "true"
    if hasattr(gui, "auto_preview_frame_cb") and gui.auto_preview_frame_cb.isHidden():
        auto_preview_enabled = False
        s.setValue("auto_preview_frame", False)
    if hasattr(gui, "auto_preview_frame_cb"):
        gui.auto_preview_frame_cb.setChecked(auto_preview_enabled)

    if hasattr(gui, "ai_dubbing_rewrite_cb"):
        gui.ai_dubbing_rewrite_cb.setChecked(str(s.value("ai_dubbing_rewrite", "true")).lower() == "true")

    if hasattr(gui, "subtitle_single_line_cb"):
        saved_sl = s.value("subtitle_single_line", None)
        if saved_sl is not None:
            gui.subtitle_single_line_cb.setChecked(str(saved_sl).lower() == "true")
    if hasattr(gui, "subtitle_words_per_segment_spin"):
        saved_w = s.value("subtitle_words_per_segment", None)
        if saved_w is not None:
            try:
                gui.subtitle_words_per_segment_spin.setValue(int(saved_w))
            except Exception:
                pass

    advanced_open = str(s.value("advanced_section_open", "false")).lower() == "true"
    if hasattr(gui, "toggle_advanced_btn"):
        gui.toggle_advanced_btn.setChecked(advanced_open)
    elif hasattr(gui, "on_advanced_toggled"):
        gui.on_advanced_toggled(advanced_open)

    if hasattr(gui, "on_audio_source_mode_changed"):
        gui.on_audio_source_mode_changed()
    if hasattr(gui, "on_subtitle_preset_changed"):
        gui.on_subtitle_preset_changed()
    if hasattr(gui, "_capture_subtitle_custom_style_state"):
        gui._capture_subtitle_custom_style_state()
    if hasattr(gui, "update_subtitle_preview_style"):
        gui.update_subtitle_preview_style()
    if hasattr(gui, "on_output_mode_changed") and hasattr(gui, "output_mode_combo"):
        gui.on_output_mode_changed(gui.output_mode_combo.currentText())

    gui.refresh_ui_state()

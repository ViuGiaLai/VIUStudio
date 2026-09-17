"""Timeline selection and timed-layer preview feature."""


class TimelineSelectionMixin:
    def _set_layer_timing_controls(self, prefix: str, layer) -> None:
        """Populate an overlay inspector's Start/End controls without edits."""
        for suffix, value in (("start", float(layer.start)), ("end", float(layer.end))):
            control = getattr(self, f"{prefix}_inspector_{suffix}_spin", None)
            if control is None:
                continue
            control.blockSignals(True)
            control.setValue(value)
            control.blockSignals(False)

    def _layer_is_active_at_preview_time(self, layer, time_seconds=None) -> bool:
        """Return whether a layer should be visible at the current playhead."""
        if not bool(getattr(layer, "visible", True)):
            return False
        if time_seconds is None:
            try:
                time_seconds = self.timeline_position_seconds() if hasattr(self, "timeline_position_seconds") else float(self.media_player.position()) / 1000.0
            except Exception:
                time_seconds = 0.0
        start = max(0.0, float(getattr(layer, "start", 0.0) or 0.0))
        end = float(getattr(layer, "end", 0.0) or 0.0)
        # Legacy layers without a valid duration continue to be visible.
        return end <= start or (start <= float(time_seconds) < end)

    def _preview_is_playing(self) -> bool:
        # The timeline keeps an explicit review/edit state synchronized from
        # the media-state callback. Prefer it here: native backends can report
        # a transient PlayingState while a pause/seek event is still being
        # delivered, which used to disable range actions immediately after a
        # range was created.
        timeline = getattr(self, "timeline", None)
        if timeline is not None and hasattr(timeline, "_playing"):
            return bool(getattr(timeline, "_playing", False))
        try:
            return bool(self.media_player.is_playing())
        except Exception:
            return False

    def _deferred_effect_layer_id_for(self, layer_type: str) -> str:
        """Return the one effect clip temporarily hidden during an edit."""
        if self._preview_is_playing():
            return ""
        if str(getattr(self, "_deferred_effect_edit_type", "") or "") != str(layer_type):
            return ""
        return str(getattr(self, "_deferred_effect_edit_layer_id", "") or "")

    def _set_deferred_effect_edit_target(self, track=None, layer=None) -> bool:
        """Suppress one selected Mask effect while paused.

        Overlay geometry continues to update normally; only the MPV filter
        contribution of the selected clip is deferred until it is committed.
        """
        next_type = ""
        next_id = ""
        if layer is not None and not self._preview_is_playing():
            layer_type = str(getattr(getattr(layer, "type", ""), "value", getattr(layer, "type", ""))).lower()
            track_name = str(getattr(track, "name", "") or "")
            if layer_type == "mask" and track_name == "M1":
                next_type, next_id = "mask", str(getattr(layer, "id", "") or "")
        changed = (
            next_type != str(getattr(self, "_deferred_effect_edit_type", "") or "")
            or next_id != str(getattr(self, "_deferred_effect_edit_layer_id", "") or "")
        )
        if changed:
            previous_id = str(getattr(self, "_deferred_effect_edit_layer_id", "") or "")
            # Restore the previously edited layer before changing the shared
            # target. This prevents a stale suppression from surviving a
            # Blur A -> Blur B or Mask A -> Mask B selection switch.
            if previous_id and not self._preview_is_playing():
                self._deferred_effect_edit_type = ""
                self._deferred_effect_edit_layer_id = ""
                self._timed_layer_preview_signature = None
                self.refresh_timed_layer_preview()
            self._deferred_effect_edit_type = next_type
            self._deferred_effect_edit_layer_id = next_id
            self._timed_layer_preview_signature = None
        return changed

    def commit_deferred_effect_editing(self, *, refresh: bool = True) -> bool:
        """Restore a deferred Blur/Mask effect using its final geometry."""
        if not getattr(self, "_deferred_effect_edit_layer_id", ""):
            return False
        self._deferred_effect_edit_type = ""
        self._deferred_effect_edit_layer_id = ""
        self._timed_layer_preview_signature = None
        if refresh:
            self.refresh_timed_layer_preview()
        return True

    def prepare_preview_for_review_mode(self) -> None:
        """Commit paused edits and remove every preview editing affordance.

        Called immediately before playback starts so the frame entering
        Review Mode already contains the final Blur/Mask graph, rather than
        waiting for the asynchronous media-player state notification.
        """
        self._preview_edit_layer_id = ""
        self.commit_deferred_effect_editing(refresh=False)
        if hasattr(self, "video_view"):
            if hasattr(self.video_view, "subtitle_item"):
                self.video_view.subtitle_item.set_editable(False)
            if hasattr(self.video_view, "set_blur_edit_enabled"):
                self.video_view.set_blur_edit_enabled(False)
            mask_overlay = getattr(self.video_view, "mask_overlay", None)
            if mask_overlay is not None:
                mask_overlay.set_editable(False)
            logo_overlay = getattr(self.video_view, "logo_overlay", None)
            if logo_overlay is not None:
                logo_overlay.set_editable(False)
        self._timed_layer_preview_signature = None
        self._refresh_text_layer_preview("")
        self.refresh_timed_layer_preview()

    def refresh_timed_layer_preview(self, position_ms=None) -> None:
        """Show only overlay layers whose timeline interval contains the playhead."""
        if not hasattr(self, "timeline") or not self.timeline._timeline:
            return
        if position_ms is None and hasattr(self, "timeline_position_seconds"):
            time_seconds = self.timeline_position_seconds()
        else:
            time_seconds = float(position_ms if position_ms is not None else self.media_player.position()) / 1000.0
        tracked = []
        for track in self.timeline._timeline.tracks:
            for layer in track.layers:
                layer_type = str(getattr(getattr(layer, "type", ""), "value", getattr(layer, "type", ""))).lower()
                is_logo = layer_type == "image" and str(getattr(track, "name", "")) == "L1 Logo"
                if layer_type in {"blur", "mask", "text"} or is_logo:
                    tracked.append((layer.id, self._layer_is_active_at_preview_time(layer, time_seconds)))
        signature = tuple(tracked)
        if signature == getattr(self, "_timed_layer_preview_signature", None):
            return
        self._timed_layer_preview_signature = signature
        selected_id = str(getattr(self.timeline, "_selected_layer_id", "") or "")

        # Text layers are rendered independently, so filtering their payload
        # makes them disappear/reappear without changing their saved state.
        self._refresh_text_layer_preview(selected_id)

        for track in self.timeline._timeline.tracks:
            if str(getattr(track, "name", "")) == "L1 Logo":
                # The L1 header Hide/Show state is independent from playback
                # and timing.  Do not let a timed refresh recreate a hidden
                # logo when playback advances or resumes.
                if not bool(getattr(self, "_logo_track_preview_visible", True)):
                    if hasattr(self.video_view, "clear_logo"):
                        self.video_view.clear_logo()
                    continue
                active = [l for l in track.layers if self._layer_is_active_at_preview_time(l, time_seconds)]
                if active:
                    is_selected_logo = (
                        selected_id in {l.id for l in active}
                        and selected_id == str(getattr(self, "_preview_edit_layer_id", "") or "")
                        and not self._preview_is_playing()
                    )
                    target = next((l for l in active if l.id == selected_id), active[0])
                    self._show_logo_overlay(track, target, editable=is_selected_logo)
                elif hasattr(self.video_view, "clear_logo"):
                    self.video_view.clear_logo()
            elif str(getattr(track, "name", "")) == "M1":
                active_layers = [l for l in track.layers if self._layer_is_active_at_preview_time(l, time_seconds)]
                # Keep the selected region in the editor overlay, but remove
                # only that one layer from the expensive rendered effect
                # while it is being edited on a paused frame.
                overlay_regions = self._current_mask_regions_payload(time_seconds=time_seconds)
                suppressed_id = self._deferred_effect_layer_id_for("mask")
                effect_regions = self._current_mask_regions_payload(
                    time_seconds=time_seconds, exclude_layer_id=suppressed_id,
                )
                if hasattr(self.video_view, "set_mask_regions"):
                    active_index = next((i for i, l in enumerate(active_layers) if l.id == selected_id), 0)
                    self.video_view.set_mask_regions(
                        overlay_regions,
                        active_index=active_index,
                        editable=bool(
                            active_layers
                            and selected_id in {l.id for l in active_layers}
                            and selected_id == str(getattr(self, "_preview_edit_layer_id", "") or "")
                            and self._deferred_effect_layer_id_for("mask") == selected_id
                            and not self._preview_is_playing()
                        ),
                    )
                # The mask effect is independent of selection/edit handles.
                # Keep it applied when the preview is paused as well.
                self._apply_mask_to_preview(regions=effect_regions)
            elif str(getattr(track, "name", "")) == "B1":
                overlay_regions = []
                active_layers = [l for l in track.layers if self._layer_is_active_at_preview_time(l, time_seconds)]
                for layer in active_layers:
                    overlay_regions.append({
                        "x": float(getattr(layer, "position_x", 0.0)), "y": float(getattr(layer, "position_y", 0.0)),
                        "width": float(getattr(layer, "width", 0.0)), "height": float(getattr(layer, "height", 0.0)),
                        "blur_strength": float(getattr(layer, "blur_strength", 20.0)),
                        "blur_opacity": float(getattr(layer, "blur_opacity", 1.0)),
                        "pixelate": bool(getattr(layer, "pixelate", False)),
                        "pixelate_size": int(getattr(layer, "pixelate_size", 12)),
                    })
                if hasattr(self.video_view, "set_blur_regions_normalized"):
                    self.video_view.set_blur_regions_normalized(overlay_regions)
                if hasattr(self.video_view, "set_blur_edit_enabled"):
                    # B1's effect remains rendered, but its border/handles
                    # are shown only while a B1 layer is selected and the
                    # preview is paused.
                    is_selected_blur = selected_id in {l.id for l in active_layers}
                    try:
                        is_playing = bool(self.media_player.is_playing())
                    except Exception:
                        is_playing = False
                    self.video_view.set_blur_edit_enabled(bool(
                        is_selected_blur
                        and selected_id == str(getattr(self, "_preview_edit_layer_id", "") or "")
                        and not is_playing
                        and self._blur_effect_enabled()
                    ))
                # Blur has a separate MPV filter in addition to its editable
                # outline. Update that filter with the same time-filtered
                # regions; otherwise a filter applied at playback start
                # continues blurring after the outline has disappeared.
                self.apply_preview_blur_region(regions=overlay_regions)

        # Rebuild both managed effect payloads once from the complete active
        # timeline after all overlay bookkeeping. This is the authoritative
        # multi-layer path: one selected layer may be suppressed, but every
        # other active Blur/Mask layer is always included.
        suppressed_mask_id = self._deferred_effect_layer_id_for("mask")
        self._apply_mask_to_preview(
            regions=self._current_mask_regions_payload(
                time_seconds=time_seconds,
                exclude_layer_id=suppressed_mask_id,
            )
        )
        blur_effect_regions = []
        for track in self.timeline._timeline.tracks:
            if str(getattr(track, "name", "")) != "B1":
                continue
            for layer in track.layers:
                if not self._layer_is_active_at_preview_time(layer, time_seconds):
                    continue
                blur_effect_regions.append({
                    "x": float(getattr(layer, "position_x", 0.0)),
                    "y": float(getattr(layer, "position_y", 0.0)),
                    "width": float(getattr(layer, "width", 0.0)),
                    "height": float(getattr(layer, "height", 0.0)),
                    "blur_strength": float(getattr(layer, "blur_strength", 20.0)),
                    "blur_opacity": float(getattr(layer, "blur_opacity", 1.0)),
                    "pixelate": bool(getattr(layer, "pixelate", False)),
                    "pixelate_size": int(getattr(layer, "pixelate_size", 12)),
                })
        self.apply_preview_blur_region(regions=blur_effect_regions)

    def _wire_layer_timing_controls(self, prefix: str) -> None:
        """Wire one inspector's common Start/End controls once."""
        wired_name = f"_{prefix}_layer_timing_wired"
        if getattr(self, wired_name, False):
            return
        setattr(self, wired_name, True)
        start_control = getattr(self, f"{prefix}_inspector_start_spin", None)
        end_control = getattr(self, f"{prefix}_inspector_end_spin", None)
        if start_control is None or end_control is None:
            return

        def _selected_layer():
            selected_id = str(getattr(self.timeline, "_selected_layer_id", "") or "")
            for track in getattr(getattr(self.timeline, "_timeline", None), "tracks", []):
                for layer in track.layers:
                    if layer.id == selected_id:
                        return track, layer
            return None, None

        def _apply_timing(_value=None):
            track, layer = _selected_layer()
            if layer is None:
                return
            start = max(0.0, float(start_control.value()))
            end = max(start + float(getattr(self.timeline, "MIN_DUR", 0.1)), float(end_control.value()))
            duration = float(getattr(self.timeline, "_duration", 0.0) or 0.0)
            if duration > 0:
                start = min(start, max(0.0, duration - float(getattr(self.timeline, "MIN_DUR", 0.1))))
                end = min(end, duration)
                end = max(end, start + float(getattr(self.timeline, "MIN_DUR", 0.1)))
            layer.start, layer.end = start, end
            self._set_layer_timing_controls(prefix, layer)
            self.timeline._redraw()
            self.persist_current_timeline_project_data()
            self._timed_layer_preview_signature = None
            self.refresh_timed_layer_preview()
            if prefix == "mask":
                self._apply_mask_to_preview(
                    regions=self._current_mask_regions_payload(include_inactive=True)
                )

        start_control.valueChanged.connect(_apply_timing)
        end_control.valueChanged.connect(_apply_timing)

    def on_timeline_layer_timing_changed(self, layer_id: str, start: float, end: float):
        """Persist timeline-handle duration edits for all non-subtitle layers."""
        if self._preview_is_playing():
            return
        if not hasattr(self, "timeline") or not self.timeline._timeline:
            return
        for track in self.timeline._timeline.tracks:
            for layer in track.layers:
                if layer.id != layer_id:
                    continue
                if bool(getattr(layer, "locked", False)):
                    return
                layer_type = str(getattr(getattr(layer, "type", ""), "value", getattr(layer, "type", ""))).lower()
                is_v1_clip = layer_type in {"video", "image"} and str(getattr(track, "name", "")).startswith("V1")
                if is_v1_clip or str(getattr(track, "name", "")).startswith("V1"):
                    from app.services.timeline_video_sequence import normalize_v1_sequence, ordered_video_layers, is_image_file

                    # Track first video start before normalizing
                    first_vid_before = next((float(l.start) for l in ordered_video_layers(self.timeline._timeline) if not is_image_file(l.source)), None)

                    normalize_v1_sequence(self.timeline._timeline)
                    self.timeline.set_duration(int(self.timeline._timeline.duration * 1000))
                    self.timeline._redraw()

                    # Track first video start after normalizing and shift timed elements
                    first_vid_after = next((float(l.start) for l in ordered_video_layers(self.timeline._timeline) if not is_image_file(l.source)), None)
                    if first_vid_before is not None and first_vid_after is not None:
                        shift_delta = first_vid_after - first_vid_before
                        if abs(shift_delta) > 0.001 and hasattr(self, "shift_timeline_timed_elements"):
                            self.shift_timeline_timed_elements(shift_delta, after_time=0.0)

                    if hasattr(self, "_sync_canonical_source_after_change"):
                        self._sync_canonical_source_after_change()
                    if hasattr(self, "refresh_source_video_list"):
                        self.refresh_source_video_list()
                    self.persist_current_timeline_project_data()
                    return
                is_logo = layer_type == "image" and str(getattr(track, "name", "")) == "L1 Logo"
                if layer_type not in {"blur", "mask", "text", "subtitle", "dub_subtitle"} and not is_logo:
                    return
                layer.start = max(0.0, float(start))
                layer.end = max(layer.start + float(getattr(self.timeline, "MIN_DUR", 0.1)), float(end))
                self.persist_current_timeline_project_data()
                self._timed_layer_preview_signature = None
                self.refresh_timed_layer_preview()
                if layer_type == "mask":
                    self._apply_mask_to_preview(
                        regions=self._current_mask_regions_payload(include_inactive=True)
                    )
                # Refresh the visible inspector values while keeping its
                # layer-specific visual controls and preview selection intact.
                self.on_timeline_layer_selected(layer_id)
                return

    def on_timeline_layer_selected(self, layer_id: str):
        if not hasattr(self, "timeline") or not self.timeline._timeline:
            return
        track = None
        layer = None
        for t in self.timeline._timeline.tracks:
            for l in t.layers:
                if l.id == layer_id:
                    layer = l
                    track = t
                    break
            if layer:
                break
        # The subtitle overlay should only capture the mouse when a concrete
        # subtitle segment (TS1/S1) is selected in the timeline.  Otherwise
        # it stays click-through, preventing accidental moves while editing
        # other video layers.
        is_review_mode = self._preview_is_playing()
        if hasattr(self, "video_view") and hasattr(self.video_view, "subtitle_item"):
            layer_type = str(getattr(getattr(layer, "type", ""), "value", getattr(layer, "type", ""))).lower() if layer else ""
            self.video_view.subtitle_item.set_editable(
                not is_review_mode and layer_type in {"subtitle", "dub_subtitle"}
            )
        # During review mode a layer may still be inspected/focused, but it
        # must never acquire preview drag handles. A real paused selection is
        # the only entry point into preview editing.
        self._preview_edit_layer_id = "" if is_review_mode else str(layer_id or "")
        # Selection changes are the commit boundary for deferred Blur/Mask
        # geometry. Selecting a Blur/Mask while paused starts a new light-
        # weight edit session; selecting anything else restores the old one.
        self._set_deferred_effect_edit_target(track, layer)
        if not layer:
            self._show_default_inspector()
            # Deselecting a layer only removes edit chrome. Effects and
            # rendered layer content remain visible in the preview.
            self._timed_layer_preview_signature = None
            self.refresh_timed_layer_preview()
            return
        # A selection must respect timing immediately, including before the
        # next playback positionChanged signal is emitted.
        self._timed_layer_preview_signature = None
        self.refresh_timed_layer_preview()
        layer_type = str(getattr(layer.type, "value", layer.type)).lower()
        can_modify_layer = not bool(getattr(track, "locked", False)) and not bool(getattr(layer, "locked", False))
        if hasattr(self, "timeline_split_btn"):
            self.timeline_split_btn.setEnabled(
                not is_review_mode and can_modify_layer and (
                    layer_type in {"video", "subtitle", "dub_subtitle", "blur", "mask", "text"}
                    or (layer_type == "image" and str(getattr(track, "name", "")) in {"L1 Logo", "V1 Video"})
                    or str(getattr(track, "name", "")).startswith("V1")
                )
            )
        if hasattr(self, "timeline_delete_btn"):
            self.timeline_delete_btn.setEnabled(not is_review_mode and can_modify_layer)
        if hasattr(self, "inspector_delete_segment_btn"):
            self.inspector_delete_segment_btn.setEnabled(not is_review_mode and can_modify_layer)
        if layer_type == "subtitle":
            self._show_subtitle_inspector_for_layer(layer_id)
        elif layer_type == "dub_subtitle":
            self._show_dub_subtitle_inspector_for_layer(layer_id, layer)
        elif layer_type == "audio":
            if str(getattr(track, "name", "")) != "A1 Audio":
                self._show_audio_inspector_for_track(track, layer)
        elif layer_type == "blur":
            self._show_blur_inspector_for_track(track, layer)
        elif layer_type == "video":
            self._show_video_inspector_for_track(track, layer)
        elif layer_type == "image" and str(getattr(track, "name", "")) == "L1 Logo":
            self._show_logo_overlay(track, layer)
            self._show_logo_inspector_for_track(track, layer)
        elif layer_type == "mask" or str(getattr(track, "name", "")) == "M1":
            self._show_mask_overlay(track, layer)
            self._show_mask_inspector_for_track(track, layer)
        elif layer_type == "text":
            self._show_text_inspector_for_track(track, layer)
            self._refresh_text_layer_preview(layer.id)
        else:
            # Image, sticker: show default with info
            self._show_default_inspector_for_layer(track, layer)
            # Do not clear unrelated visual layers when changing inspector
            # panels. Their effects are independent of selection.
            self._timed_layer_preview_signature = None
            self.refresh_timed_layer_preview()

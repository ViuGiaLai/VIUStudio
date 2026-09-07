"""Visual logo, mask, blur, and inspector feature."""


class VisualLayerEditorMixin:
    def _show_logo_overlay(self, track, layer, *, editable=True):
        """Show the draggable logo overlay for the selected logo layer."""
        if not hasattr(self, "video_view"):
            return
        # This method is also called by selection/project-restoration paths,
        # so guard it here as well as in the timed playback refresh.
        if not bool(getattr(self, "_logo_track_preview_visible", True)):
            if hasattr(self.video_view, "clear_logo"):
                self.video_view.clear_logo()
            return
        path = str(getattr(layer, "source", "") or "")
        if not path:
            return
        try:
            from app.layers.transform import Transform
            transform = getattr(layer, "transform", None) or Transform()
        except Exception:
            transform = None
        # Store the handler lambdas as attributes so we can disconnect
        # them by reference. This avoids the libpyside RuntimeWarning
        # that occurs when calling disconnect() with no args or with
        # a lambda that was never connected.
        prev_moved = getattr(self, "_logo_moved_handler", None)
        if prev_moved is not None:
            try:
                self.video_view.logoMoved.disconnect(prev_moved)
            except (RuntimeError, TypeError, Exception):
                pass
        prev_deleted = getattr(self, "_logo_deleted_handler", None)
        if prev_deleted is not None:
            try:
                self.video_view.logoDeleted.disconnect(prev_deleted)
            except (RuntimeError, TypeError, Exception):
                pass

        self._logo_overlay_layer = layer

        def _moved_handler(nx, ny, nw, nh, l=layer):
            self._on_logo_moved(l, nx, ny, nw, nh)

        def _deleted_handler(l=layer):
            self._delete_logo_layer(l)

        self._logo_moved_handler = _moved_handler
        self._logo_deleted_handler = _deleted_handler

        self.video_view.logoMoved.connect(_moved_handler)
        self.video_view.logoDeleted.connect(_deleted_handler)

        logos = []
        active_index = 0
        for index, candidate in enumerate(track.layers):
            if not self._layer_is_active_at_preview_time(candidate):
                continue
            source = str(getattr(candidate, "source", "") or "")
            candidate_transform = getattr(candidate, "transform", None)
            if candidate_transform is not None:
                val_x = getattr(candidate_transform, "x", 0.0)
                raw_x = float(val_x if val_x is not None else 0.0)
                logo_x = raw_x / 100.0 if raw_x > 1.0 else raw_x
                val_y = getattr(candidate_transform, "y", 0.0)
                raw_y = float(val_y if val_y is not None else 0.0)
                logo_y = raw_y / 100.0 if raw_y > 1.0 else raw_y
                val_sx = getattr(candidate_transform, "scale_x", 0.2)
                raw_scale_x = float(val_sx if val_sx is not None else 0.2)
                logo_w = raw_scale_x / 100.0 if raw_scale_x > 1.0 else raw_scale_x
                val_sy = getattr(candidate_transform, "scale_y", 0.2)
                raw_scale_y = float(val_sy if val_sy is not None else 0.2)
                logo_h = raw_scale_y / 100.0 if raw_scale_y > 1.0 else raw_scale_y
                val_rot = getattr(candidate_transform, "rotation", 0.0)
                logo_rotation = float(val_rot if val_rot is not None else 0.0)
            else:
                logo_x, logo_y, logo_w, logo_h, logo_rotation = 0.0, 0.0, 0.2, 0.2, 0.0
            logos.append({
                "source": source, "x": logo_x, "y": logo_y,
                "width": logo_w, "height": logo_h,
                "opacity": float(getattr(candidate, "opacity", 1.0) or 1.0),
                "rotation": logo_rotation,
            })
            if candidate is layer:
                active_index = len(logos) - 1
        if not logos:
            if hasattr(self.video_view, "clear_logo"):
                self.video_view.clear_logo()
            return
        self.video_view.set_logos(
            logos,
            active_index=active_index,
            editable=bool(editable and not self._preview_is_playing()
                          and str(getattr(layer, "id", "") or "") == str(getattr(self, "_preview_edit_layer_id", "") or "")),
        )

        # Push opacity + rotation from the layer to the overlay. We
        # default to fully opaque + 0° for a freshly created logo.
        opacity = float(getattr(layer, "opacity", 1.0) or 1.0)
        rotation = 0.0
        if transform is not None and hasattr(transform, "rotation"):
            try:
                rotation = float(getattr(transform, "rotation", 0.0) or 0.0)
            except (TypeError, ValueError):
                rotation = 0.0
        self.video_view.set_logo_opacity(opacity)
        self.video_view.set_logo_rotation(rotation)

    def _delete_logo_layer(self, layer):
        """Remove the logo layer from the L1 track and clean up."""
        if not hasattr(self, "timeline") or not self.timeline._timeline:
            return
        remaining_track = None
        remaining_layer = None
        for track in self.timeline._timeline.tracks:
            if layer in track.layers:
                track.layers.remove(layer)
                if not track.layers:
                    try:
                        self.timeline._timeline.tracks.remove(track)
                    except ValueError:
                        pass
                    if hasattr(self.timeline, "_track_heights") and track.id in self.timeline._track_heights:
                        del self.timeline._track_heights[track.id]
                else:
                    remaining_track = track
                    remaining_layer = track.layers[0]
                break
        try:
            self.timeline._selected_layer_id = remaining_layer.id if remaining_layer else ""
        except Exception:
            pass
        if hasattr(self.timeline, "_redraw"):
            self.timeline._redraw()
        if hasattr(self.timeline, "viewport"):
            self.timeline.viewport().update()
        if remaining_layer is not None:
            self._show_logo_overlay(remaining_track, remaining_layer)
        elif hasattr(self, "video_view") and hasattr(self.video_view, "clear_logo"):
            self.video_view.clear_logo()
        try:
            self.persist_current_timeline_project_data()
        except Exception:
            pass
        if hasattr(self, "_show_default_inspector"):
            self._show_default_inspector()

    def _show_mask_overlay(self, track, layer):
        """Show the draggable mask overlay for the selected mask layer."""
        if not hasattr(self, "video_view"):
            return
        if not bool(getattr(self, "_mask_track_preview_visible", True)):
            # Hide/Show controls both the visual effect and its edit chrome.
            # A later focus/selection event must not resurrect either one.
            if hasattr(self.video_view, "clear_mask_region"):
                self.video_view.clear_mask_region()
            return
        # Disconnect any previous handlers to avoid the libpyside
        # RuntimeWarning that occurs when calling disconnect() with no
        # args or a lambda that was never connected.
        prev_moved = getattr(self, "_mask_moved_handler", None)
        if prev_moved is not None:
            try:
                self.video_view.maskMoved.disconnect(prev_moved)
            except (RuntimeError, TypeError, Exception):
                pass
        prev_changed = getattr(self, "_mask_region_changed_handler", None)
        if prev_changed is not None:
            try:
                self.video_view.maskRegionChanged.disconnect(prev_changed)
            except (RuntimeError, TypeError, Exception):
                pass
        prev_deleted = getattr(self, "_mask_deleted_handler", None)
        if prev_deleted is not None:
            try:
                self.video_view.maskDeleted.disconnect(prev_deleted)
            except (RuntimeError, TypeError, Exception):
                pass

        self._mask_overlay_layer = layer

        def _moved_handler(nx, ny, nw, nh, l=layer):
            self._on_mask_moved(l, nx, ny, nw, nh)

        def _region_changed_handler(t=track, l=layer):
            # Fired continuously while the user drags the overlay. Push
            # the new region back to the layer + mpv filter so the
            # green mask follows the overlay in real time.
            self._on_mask_overlay_changed(t, l)

        def _deleted_handler(l=layer):
            self._delete_mask_layer(l)

        self._mask_moved_handler = _moved_handler
        self._mask_region_changed_handler = _region_changed_handler
        self._mask_deleted_handler = _deleted_handler

        self.video_view.maskMoved.connect(_moved_handler)
        self.video_view.maskRegionChanged.connect(_region_changed_handler)
        self.video_view.maskDeleted.connect(_deleted_handler)

        visible_layers = [candidate for candidate in track.layers
                          if self._layer_is_active_at_preview_time(candidate)]
        regions = self._current_mask_regions_payload()
        try:
            active_index = visible_layers.index(layer)
        except ValueError:
            active_index = 0
        # The overlay is always shown so the user can move / resize
        # the region regardless of the M1 track toggle. The toggle
        # only controls whether the mpv filter is applied (see
        # on_track_mask_toggled). Without this, the overlay would
        # only appear after the user clicked the mask layer track
        # to re-select it, even though the layer already exists.
        is_playing = False
        try:
            is_playing = bool(self.media_player.is_playing())
        except Exception:
            is_playing = False
        if hasattr(self, "track_label_bar"):
            self.track_label_bar.set_controls_enabled(not is_playing)
        self.video_view.set_mask_regions(
            regions, active_index=active_index, editable=not is_playing,
        )
        # Re-apply the complete active M1 payload after rebinding the
        # editable overlay. set_mask_regions only updates editor chrome; it
        # must never leave the other mask effects cleared when selection
        # changes between multiple layers.
        try:
            self._apply_mask_to_preview(
                regions=self._current_mask_regions_payload(
                    exclude_layer_id=self._deferred_effect_layer_id_for("mask")
                )
            )
        except Exception:
            pass

    def _on_mask_moved(self, layer, x, y, w, h):
        """Update Mask geometry without rebuilding its MPV effect per move."""
        if self._preview_is_playing():
            return
        try:
            layer.position_x = float(x)
            layer.position_y = float(y)
            layer.width = float(w)
            layer.height = float(h)
        except Exception:
            return
        # Persist coalesced geometry only. The selected M1 effect has already
        # been removed from the filter graph for this paused edit session.
        self.schedule_timeline_project_persist(mask_state=True)
        try:
            if (hasattr(self, "mask_inspector_x_spin")
                    and self.timeline._selected_layer_id == layer.id):
                for control, value in (
                    (self.mask_inspector_x_spin, x),
                    (self.mask_inspector_y_spin, y),
                    (self.mask_inspector_w_spin, w),
                    (self.mask_inspector_h_spin, h),
                ):
                    control.blockSignals(True)
                    control.setValue(float(value))
                    control.blockSignals(False)
        except Exception:
            pass

    def _resync_visual_layers_after_state(self):
        """Finalize overlay effects/handles after a playback state change."""
        try:
            self._timed_layer_preview_signature = None
            self.refresh_timed_layer_preview()
            self._apply_mask_to_preview()
            self._sync_blur_controls()
        except Exception:
            pass
        # Both project settings and timeline JSON are disk-backed.  Defer
        # those writes during the drag while keeping all preview state live.
        self.schedule_timeline_project_persist(mask_state=True)

    def _on_mask_overlay_changed(self, track, layer):
        """Read the current overlay region and update the layer
        position. The mpv filter is NOT re-applied here — it is
        only applied while the video is playing, to avoid lag
        during the drag. When the user presses play, the latest
        layer position is pushed to mpv via `_apply_mask_to_preview`
        (called from `toggle_play` and the stateChanged handler).
        """
        if self._preview_is_playing() or not hasattr(self, "video_view"):
            return
        overlay = getattr(self.video_view, "mask_overlay", None)
        if overlay is None or not overlay._regions:
            return
        try:
            active_index = int(getattr(overlay, "_active_index", -1))
            rect = overlay._regions[active_index]
            x = float(rect.x())
            y = float(rect.y())
            w = float(rect.width())
            h = float(rect.height())
        except Exception:
            return
        try:
            layer.position_x = x
            layer.position_y = y
            layer.width = w
            layer.height = h
        except Exception:
            return
        self.schedule_timeline_project_persist(mask_state=True)

    def _delete_mask_layer(self, layer):
        """Remove the mask layer from the M1 track and clean up."""
        if not hasattr(self, "timeline") or not self.timeline._timeline:
            return
        for track in self.timeline._timeline.tracks:
            if layer in track.layers:
                track.layers.remove(layer)
                if not track.layers:
                    try:
                        self.timeline._timeline.tracks.remove(track)
                    except ValueError:
                        pass
                    if hasattr(self.timeline, "_track_heights") and track.id in self.timeline._track_heights:
                        del self.timeline._track_heights[track.id]
                break
        if hasattr(self.timeline, "_redraw"):
            self.timeline._redraw()
        if hasattr(self.timeline, "viewport"):
            self.timeline.viewport().update()
        try:
            if hasattr(self, "_apply_mask_to_preview"):
                self._apply_mask_to_preview()
        except Exception:
            pass
        try:
            if hasattr(self, "persist_project_mask_state"):
                self.persist_project_mask_state()
        except Exception:
            pass
        # The mask-specific delete path returns before the shared Delete
        # handler can persist the serialized timeline.  Write timeline.json
        # here as well so a deleted M1 layer cannot reappear on reopen.
        try:
            self.persist_current_timeline_project_data()
        except Exception:
            pass
        if hasattr(self, "_show_default_inspector"):
            self._show_default_inspector()
        self._clear_effect_selection_after_delete()

    def _clear_effect_selection_after_delete(self):
        """Leave deleted Blur/Mask layers in a neutral, non-editing state."""
        self._deferred_effect_edit_type = ""
        self._deferred_effect_edit_layer_id = ""
        self._preview_edit_layer_id = ""
        self._timed_layer_preview_signature = None
        timeline = getattr(self, "timeline", None)
        model = getattr(timeline, "_timeline", None) if timeline is not None else None
        video_layer_id = ""
        video_layer = None
        for track in getattr(model, "tracks", []) or []:
            track_type = str(getattr(getattr(track, "type", ""), "value", getattr(track, "type", ""))).lower()
            if track_type != "video" and str(getattr(track, "name", "")) != "V1 Video":
                continue
            if track.layers:
                video_layer = track.layers[0]
                video_layer_id = str(getattr(video_layer, "id", "") or "")
                break
        # If the M1 track was removed with its final layer, clear the
        # independent top-level overlay as well as the MPV effect. The
        # overlay is not owned by the timeline scene and can otherwise keep
        # painting its last region after the model is empty.
        has_mask_layers = any(
            str(getattr(track, "name", "")) == "M1" and bool(getattr(track, "layers", []))
            for track in getattr(model, "tracks", []) or []
        )
        if not has_mask_layers and hasattr(self, "video_view"):
            try:
                if hasattr(self.video_view, "clear_mask_region"):
                    self.video_view.clear_mask_region()
                elif getattr(self.video_view, "mask_overlay", None) is not None:
                    self.video_view.mask_overlay.clear_region()
            except Exception:
                pass
        if video_layer_id:
            timeline._selected_layer_id = video_layer_id
            self.on_timeline_layer_selected(video_layer_id)
        else:
            timeline._selected_layer_id = ""
            self.refresh_timed_layer_preview()

    def _show_subtitle_inspector_for_layer(self, layer_id: str):
        """Show subtitle inspector and select the matching segment."""
        self._switch_inspector("subtitle")
        if hasattr(self, "timeline") and self.timeline:
            idx = self.timeline.segment_index_for_layer_id(layer_id)
            if idx >= 0:
                self.set_selected_segment_index(idx, sync_ui=True)

    def _show_dub_subtitle_inspector_for_layer(self, layer_id: str, layer=None):
        """Show the inspector for a dub subtitle layer."""
        self._switch_inspector("subtitle")
        if hasattr(self, "timeline") and self.timeline:
            idx = self.timeline.segment_index_for_layer_id(layer_id)
            if idx >= 0:
                self.set_selected_segment_index(idx, sync_ui=True)

    def _show_audio_inspector_for_track(self, track, layer=None):
        """Show audio inspector populated with the selected track's settings."""
        self._switch_inspector("audio")
        # The Dub Voice section is only for A2 Dub/TS1. Hide it for
        # A1 Audio (or any other audio track).
        track_name = str(getattr(track, "name", "") or "")
        dub_section = getattr(self, "audio_inspector_dub_section", None)
        if dub_section is not None:
            dub_section.setVisible(track_name in ("A2 Dub", "TS1"))
        if track is None:
            return
        track_name = str(getattr(track, "name", "Audio"))
        if hasattr(self, "audio_inspector_track_name_label"):
            self.audio_inspector_track_name_label.setText(track_name)
        if hasattr(self, "audio_inspector_layer_count_label"):
            count = len(list(getattr(track, "layers", [])))
            if layer is not None:
                layer_label = f"Selected: {layer.name}"
            else:
                layer_label = "No layer selected"
            self.audio_inspector_layer_count_label.setText(
                f"{layer_label}    •    {count} layer(s) in track"
            )
        if hasattr(self, "audio_inspector_summary_label"):
            self.audio_inspector_summary_label.setText(
                f"Audio settings for {track_name}. Adjust volume, gain, "
                "speed or mute the track for preview."
            )
        # Load current track metadata into the controls
        meta = getattr(track, "metadata", None) or {}
        try:
            gain = float(meta.get("_gain_db", 0.0))
        except (TypeError, ValueError):
            gain = 0.0
        try:
            speed = float(meta.get("_speed", 1.0))
        except (TypeError, ValueError):
            speed = 1.0
        muted = bool(meta.get("_muted", False))
        solo = bool(meta.get("_solo", False))
        try:
            fade_in = float(meta.get("_fade_in", 0.0))
        except (TypeError, ValueError):
            fade_in = 0.0
        try:
            fade_out = float(meta.get("_fade_out", 0.0))
        except (TypeError, ValueError):
            fade_out = 0.0
        if hasattr(self, "audio_inspector_gain_spin"):
            self.audio_inspector_gain_spin.blockSignals(True)
            self.audio_inspector_gain_spin.setValue(gain)
            self.audio_inspector_gain_spin.blockSignals(False)
        if hasattr(self, "audio_inspector_speed_spin"):
            self.audio_inspector_speed_spin.blockSignals(True)
            self.audio_inspector_speed_spin.setValue(speed)
            self.audio_inspector_speed_spin.blockSignals(False)
        if hasattr(self, "audio_inspector_mute_btn"):
            self.audio_inspector_mute_btn.blockSignals(True)
            self.audio_inspector_mute_btn.setChecked(muted)
            self.audio_inspector_mute_btn.setText("Unmute Track" if muted else "Mute Track")
            self.audio_inspector_mute_btn.blockSignals(False)
        if hasattr(self, "audio_inspector_solo_btn"):
            self.audio_inspector_solo_btn.blockSignals(True)
            self.audio_inspector_solo_btn.setChecked(solo)
            self.audio_inspector_solo_btn.blockSignals(False)
        if hasattr(self, "audio_inspector_fade_in_spin"):
            self.audio_inspector_fade_in_spin.blockSignals(True)
            self.audio_inspector_fade_in_spin.setValue(fade_in)
            self.audio_inspector_fade_in_spin.blockSignals(False)
        if hasattr(self, "audio_inspector_fade_out_spin"):
            self.audio_inspector_fade_out_spin.blockSignals(True)
            self.audio_inspector_fade_out_spin.setValue(fade_out)
            self.audio_inspector_fade_out_spin.blockSignals(False)
        if hasattr(self, "_refresh_audio_inspector_dub_voice_buttons"):
            try:
                self._refresh_audio_inspector_dub_voice_buttons()
            except Exception:
                pass

    def _show_default_inspector_for_layer(self, track, layer):
        self._switch_inspector("default")
        if hasattr(self, "default_inspector_summary_label"):
            tname = getattr(track, "name", "Track") if track else "Track"
            lname = getattr(layer, "name", "Layer") if layer else "Layer"
            ltype = str(getattr(layer.type, "value", layer.type)) if layer else "?"
            self.default_inspector_summary_label.setText(
                f"Selected: {tname} → {lname} ({ltype}).\n"
                "No per-layer settings available for this track type yet."
            )

    def _show_blur_inspector_for_track(self, track, layer=None):
        """Show the Blur Track Inspector populated with the selected track."""
        self._switch_inspector("blur")
        self._wire_blur_inspector_controls()
        self._wire_layer_timing_controls("blur")
        if track is None:
            return
        if layer is not None:
            # Subtitle playback may temporarily change Timeline selection.
            # The open Blur inspector must keep editing the B1 region the
            # user explicitly selected instead of silently becoming inert.
            self._blur_inspector_layer_id = str(getattr(layer, "id", "") or "")
        # B1 mirrors M1 interaction: all regions remain visible in the
        # preview, but only the layer selected in the timeline is editable.
        if layer is not None:
            self._set_layer_timing_controls("blur", layer)
            try:
                visible_layers = [candidate for candidate in track.layers
                                  if self._layer_is_active_at_preview_time(candidate)]
                active_index = visible_layers.index(layer) if layer in visible_layers else 0
                self.video_view.set_blur_active_index(active_index)
            except (AttributeError, ValueError):
                pass
        track_name = str(getattr(track, "name", "Blur"))
        if hasattr(self, "blur_inspector_track_name_label"):
            self.blur_inspector_track_name_label.setText(track_name)
        if hasattr(self, "blur_inspector_layer_count_label"):
            count = len(list(getattr(track, "layers", [])))
            if layer is not None:
                self.blur_inspector_layer_count_label.setText(
                    f"Selected: {layer.name}    •    {count} blur region(s) in track"
                )
            else:
                self.blur_inspector_layer_count_label.setText(
                    f"{count} blur region(s) in track"
                )
        # Load radius / opacity / pixelate from the selected layer
        # (fall back to defaults when no layer is selected).
        if layer is not None:
            try:
                strength = int(round(float(getattr(layer, "blur_strength", 20.0))))
            except (TypeError, ValueError):
                strength = 20
            strength = max(1, min(100, strength))
            try:
                opacity = float(getattr(layer, "blur_opacity", 1.0))
            except (TypeError, ValueError):
                opacity = 1.0
            opacity = max(0.0, min(1.0, opacity))
            pixelate = bool(getattr(layer, "pixelate", False))
            try:
                pixel_size = int(getattr(layer, "pixelate_size", 12))
            except (TypeError, ValueError):
                pixel_size = 12
            pixel_size = max(2, min(60, pixel_size))
        else:
            strength, opacity, pixelate, pixel_size = 36, 1.0, False, 12

        if hasattr(self, "blur_inspector_radius_slider"):
            self.blur_inspector_radius_slider.blockSignals(True)
            self.blur_inspector_radius_slider.setValue(strength)
            self.blur_inspector_radius_slider.blockSignals(False)
        if hasattr(self, "blur_inspector_radius_value_label"):
            self.blur_inspector_radius_value_label.setText(f"{strength} / 100")
        if hasattr(self, "blur_inspector_opacity_slider"):
            self.blur_inspector_opacity_slider.blockSignals(True)
            self.blur_inspector_opacity_slider.setValue(int(round(opacity * 100)))
            self.blur_inspector_opacity_slider.blockSignals(False)
        if hasattr(self, "blur_inspector_opacity_value_label"):
            self.blur_inspector_opacity_value_label.setText(
                f"{int(round(opacity * 100))}%"
            )
        if hasattr(self, "blur_inspector_pixelate_cb"):
            self.blur_inspector_pixelate_cb.blockSignals(True)
            self.blur_inspector_pixelate_cb.setChecked(pixelate)
            self.blur_inspector_pixelate_cb.blockSignals(False)
        if hasattr(self, "blur_inspector_pixel_size_slider"):
            self.blur_inspector_pixel_size_slider.blockSignals(True)
            self.blur_inspector_pixel_size_slider.setValue(pixel_size)
            self.blur_inspector_pixel_size_slider.blockSignals(False)
        if hasattr(self, "blur_inspector_pixel_size_value_label"):
            self.blur_inspector_pixel_size_value_label.setText(str(pixel_size))

        if hasattr(self, "blur_inspector_summary_label"):
            self.blur_inspector_summary_label.setText(
                f"Blur regions in '{track_name}'. Use the B1 layer "
                "visibility control in the timeline to show or hide it."
            )

    def _wire_blur_inspector_controls(self):
        """One-time wiring of the Blur Inspector's per-region controls."""
        if getattr(self, "_blur_inspector_wired", False):
            return
        self._blur_inspector_wired = True

        def _selected_blur_layer():
            """Return the currently selected BlurLayer (or None)."""
            if not hasattr(self, "timeline") or not self.timeline._timeline:
                return None, None
            selected_id = str(getattr(self.timeline, "_selected_layer_id", "") or "")
            inspector_id = str(getattr(self, "_blur_inspector_layer_id", "") or "")
            for sid in (selected_id, inspector_id):
                if not sid:
                    continue
                for tr in self.timeline._timeline.tracks:
                    for l in tr.layers:
                        layer_type = str(
                            getattr(getattr(l, "type", ""), "value", getattr(l, "type", ""))
                        ).lower()
                        if l.id == sid and layer_type == "blur":
                            self._blur_inspector_layer_id = str(l.id)
                            return l, tr
            return None, None

        def _on_radius_changed(value):
            if hasattr(self, "blur_inspector_radius_value_label"):
                self.blur_inspector_radius_value_label.setText(f"{int(value)} / 100")
            layer, _ = _selected_blur_layer()
            if layer is None:
                return
            try:
                layer.blur_strength = int(value)
            except Exception:
                return
            self._sync_blur_layer_to_preview(layer)

        def _on_opacity_changed(value):
            layer, _ = _selected_blur_layer()
            if layer is None:
                return
            opacity = max(0.0, min(1.0, float(value) / 100.0))
            try:
                layer.blur_opacity = opacity
            except Exception:
                return
            if hasattr(self, "blur_inspector_opacity_value_label"):
                self.blur_inspector_opacity_value_label.setText(f"{int(value)}%")
            self._sync_blur_layer_to_preview(layer)

        def _on_pixelate_toggled(checked):
            layer, _ = _selected_blur_layer()
            if layer is None:
                return
            try:
                layer.pixelate = bool(checked)
            except Exception:
                return
            self._sync_blur_layer_to_preview(layer)

        def _on_pixel_size_changed(value):
            layer, _ = _selected_blur_layer()
            if layer is None:
                return
            try:
                layer.pixelate_size = int(value)
            except Exception:
                return
            if hasattr(self, "blur_inspector_pixel_size_value_label"):
                self.blur_inspector_pixel_size_value_label.setText(str(int(value)))
            self._sync_blur_layer_to_preview(layer)

        self._blur_radius_handler = _on_radius_changed
        self._blur_opacity_handler = _on_opacity_changed
        self._blur_pixelate_handler = _on_pixelate_toggled
        self._blur_pixel_size_handler = _on_pixel_size_changed

        if hasattr(self, "blur_inspector_radius_slider"):
            self.blur_inspector_radius_slider.valueChanged.connect(_on_radius_changed)
        if hasattr(self, "blur_inspector_opacity_slider"):
            self.blur_inspector_opacity_slider.valueChanged.connect(_on_opacity_changed)
        if hasattr(self, "blur_inspector_pixelate_cb"):
            self.blur_inspector_pixelate_cb.toggled.connect(_on_pixelate_toggled)
        if hasattr(self, "blur_inspector_pixel_size_slider"):
            self.blur_inspector_pixel_size_slider.valueChanged.connect(_on_pixel_size_changed)

    def _sync_blur_layer_to_preview(self, layer):
        """Push a BlurLayer's per-region style back to the video preview
        + persisted state + B1 timeline regions (so the export matches).
        """
        if not hasattr(self, "video_view"):
            return
        # The timeline model is authoritative for Blur geometry and style.
        # The preview rectangle is an editing surface only; depending on its
        # private `_regions` list caused slider updates to be discarded when
        # the overlay had not yet been created/restored.
        blur_layers = []
        active_layers = []
        if hasattr(self, "timeline") and self.timeline._timeline:
            for tr in self.timeline._timeline.tracks:
                if str(getattr(tr, "name", "") or "") == "B1" and layer in tr.layers:
                    blur_layers = list(tr.layers)
                    active_layers = [candidate for candidate in blur_layers
                                     if self._layer_is_active_at_preview_time(candidate)]
                    break
        if not blur_layers:
            return

        def _payload_for(candidate):
            try:
                return {
                    "x": float(candidate.position_x),
                    "y": float(candidate.position_y),
                    "width": float(candidate.width),
                    "height": float(candidate.height),
                    "start": float(getattr(candidate, "start", 0.0) or 0.0),
                    "end": float(getattr(candidate, "end", 0.0) or 0.0),
                    "blur_strength": int(getattr(candidate, "blur_strength", 36)),
                    "blur_opacity": float(getattr(candidate, "blur_opacity", 1.0)),
                    "pixelate": bool(getattr(candidate, "pixelate", False)),
                    "pixelate_size": int(getattr(candidate, "pixelate_size", 12)),
                }
            except (AttributeError, TypeError, ValueError):
                return None

        # Rebuild every active region from the live model. Sending only the
        # selected item would replace other B1 regions in MPV.
        payload = [entry for candidate in active_layers
                   if (entry := _payload_for(candidate)) is not None]
        if not payload:
            # A timed layer can be edited while the playhead is outside it.
            # Persist that edit, but correctly show no effect at this frame.
            payload = []
        try:
            if hasattr(self.video_view, "set_blur_regions_normalized"):
                self.video_view.set_blur_regions_normalized(payload)
        except Exception:
            pass
        # Re-apply immediately for live feedback. Disk writes are debounced so
        # dragging a slider does not block the UI on every valueChanged event.
        if hasattr(self, "apply_preview_blur_region"):
            try:
                self.apply_preview_blur_region(regions=payload, force=True)
            except Exception:
                pass
        if hasattr(self, "schedule_timeline_project_persist"):
            self.schedule_timeline_project_persist(blur_state=True)

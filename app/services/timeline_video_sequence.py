from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Iterable

_SERVICES_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_DIR = os.path.dirname(_SERVICES_DIR)
_REPO_ROOT = os.path.dirname(_APP_DIR)
for _p in (_REPO_ROOT, _APP_DIR):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

from app.layers.audio import AudioLayer
from app.layers.base import LayerType
from app.layers.timeline import Timeline, Track
from app.layers.transform import Transform
from app.layers.video import VideoLayer

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


def is_image_file(path: str) -> bool:
    if not path:
        return False
    return os.path.splitext(str(path).strip())[1].lower() in IMAGE_EXTENSIONS


@dataclass(frozen=True)
class TimelineVideoClip:
    layer_id: str
    source: str
    timeline_start: float
    timeline_end: float
    source_start: float
    speed: float
    muted: bool
    volume: float

    @property
    def duration(self) -> float:
        return max(0.0, self.timeline_end - self.timeline_start)

    @property
    def source_duration(self) -> float:
        return self.duration * max(0.01, self.speed)

    @property
    def is_image(self) -> bool:
        return is_image_file(self.source)

    def to_dict(self) -> dict:
        return {
            "layer_id": self.layer_id,
            "source": self.source,
            "timeline_start": self.timeline_start,
            "timeline_end": self.timeline_end,
            "source_start": self.source_start,
            "source_duration": self.source_duration,
            "speed": self.speed,
            "muted": self.muted,
            "volume": self.volume,
            "is_image": self.is_image,
        }


def video_track(timeline: Timeline | None) -> Track | None:
    if timeline is None:
        return None
    for track in timeline.tracks:
        if track.type == LayerType.VIDEO and (
            str(track.name).strip().lower().startswith("v1")
            or str(track.id).strip().lower() == "v1"
        ):
            return track
    return next((track for track in timeline.tracks if track.type == LayerType.VIDEO), None)


def audio_track(timeline: Timeline | None) -> Track | None:
    if timeline is None:
        return None
    for track in timeline.tracks:
        if track.type == LayerType.AUDIO and (
            str(track.name).strip().lower().startswith("a1")
            or str(track.id).strip().lower() == "a1"
        ):
            return track
    return next((track for track in timeline.tracks if track.type == LayerType.AUDIO), None)


def ordered_video_layers(timeline: Timeline | None) -> list[VideoLayer]:
    track = video_track(timeline)
    if track is None:
        return []
    layers = [layer for layer in track.layers if isinstance(layer, VideoLayer) and layer.source]
    return sorted(layers, key=lambda layer: (float(layer.start), int(layer.z_index), layer.id))


def timeline_video_clips(timeline: Timeline | None, *, existing_only: bool = False) -> list[TimelineVideoClip]:
    clips = []
    for layer in ordered_video_layers(timeline):
        source = os.path.abspath(str(layer.source))
        if existing_only and not os.path.isfile(source):
            continue
        start = max(0.0, float(layer.start))
        end = max(start, float(layer.end))
        if end - start <= 0.001:
            continue
        clips.append(
            TimelineVideoClip(
                layer_id=str(layer.id),
                source=source,
                timeline_start=start,
                timeline_end=end,
                source_start=max(0.0, float(layer.source_start)),
                speed=max(0.01, float(layer.speed or 1.0)),
                muted=bool(layer.muted),
                volume=max(0.0, float(layer.volume)),
            )
        )
    return clips


def resolve_timeline_time(timeline: Timeline | None, seconds: float) -> tuple[TimelineVideoClip | None, float]:
    position = max(0.0, float(seconds))
    clips = timeline_video_clips(timeline)
    if not clips:
        return None, 0.0
    for clip in clips:
        if clip.timeline_start <= position < clip.timeline_end:
            local = clip.source_start + (position - clip.timeline_start) * clip.speed
            return clip, local
    clip = clips[-1] if position >= clips[-1].timeline_end else clips[0]
    local = clip.source_start + min(clip.duration, max(0.0, position - clip.timeline_start)) * clip.speed
    return clip, local


def _ensure_audio_track(timeline: Timeline) -> Track:
    track = audio_track(timeline)
    if track is None:
        track = timeline.add_track("A1 Audio", LayerType.AUDIO)
        track.height = 80
    return track


def normalize_v1_sequence(timeline: Timeline, layers: Iterable[VideoLayer] | None = None) -> list[VideoLayer]:
    """Pack V1 clips without gaps and rebuild matching original-audio clips."""
    track = video_track(timeline)
    if track is None:
        track = timeline.add_track("V1 Video", LayerType.VIDEO)
        track.height = 80
    ordered = list(layers) if layers is not None else ordered_video_layers(timeline)
    cursor = 0.0
    for index, layer in enumerate(ordered):
        duration = max(0.001, float(layer.end) - float(layer.start))
        if getattr(layer, "source", "") and not is_image_file(layer.source):
            try:
                from ui.views.editor.timeline import EditorTimeline
                source_dur = EditorTimeline._probe_video_duration(layer.source)
                if source_dur > 0:
                    max_dur = (source_dur - float(getattr(layer, "source_start", 0.0))) / max(0.01, float(getattr(layer, "speed", 1.0)))
                    duration = min(duration, max_dur)
            except Exception:
                pass
        layer.start = round(cursor, 6)
        layer.end = round(cursor + duration, 6)
        layer.z_index = index
        cursor = layer.end
    track.layers = ordered

    a1 = _ensure_audio_track(timeline)
    previous = {
        str(layer.metadata.get("video_layer_id", "")): layer
        for layer in a1.layers
        if isinstance(layer, AudioLayer) and isinstance(layer.metadata, dict)
    }
    audio_layers = []
    for index, video in enumerate(ordered):
        is_img = is_image_file(video.source)
        if is_img:
            continue
        audio = previous.get(str(video.id))
        if audio is None:
            audio = AudioLayer()
        audio.name = f"Audio {index + 1} · {os.path.basename(video.source)}"
        audio.source = video.source
        audio.start = video.start
        audio.end = video.end
        audio.source_start = video.source_start
        audio.speed = video.speed
        audio.volume = video.volume
        audio.muted = video.muted
        audio.z_index = index
        audio.metadata["video_layer_id"] = video.id
        audio_layers.append(audio)
    a1.layers = audio_layers
    timeline.duration = max(0.0, cursor)
    return ordered


def append_video(timeline: Timeline, source: str, duration: float) -> VideoLayer:
    source = os.path.abspath(str(source))
    duration = max(0.001, float(duration))
    track = video_track(timeline)
    if track is None:
        track = timeline.add_track("V1 Video", LayerType.VIDEO)
        track.height = 80
    is_img = is_image_file(source)
    end = max((float(layer.end) for layer in ordered_video_layers(timeline)), default=0.0)
    layer = VideoLayer(
        name=os.path.basename(source),
        source=source,
        start=end,
        end=end + duration,
        volume=0.0 if is_img else 1.0,
        muted=True if is_img else False,
        transform=Transform(x=0, y=0, scale_x=1.0, scale_y=1.0),
    )
    if is_img:
        layer.metadata["media_type"] = "image"
    track.layers.append(layer)
    normalize_v1_sequence(timeline)
    return layer


def insert_media(timeline: Timeline, source: str, duration: float, index: int = 0) -> VideoLayer:
    """Insert a video or image clip at a specific index in the V1 sequence (e.g. index=0 for intro)."""
    source = os.path.abspath(str(source))
    duration = max(0.001, float(duration))
    track = video_track(timeline)
    if track is None:
        track = timeline.add_track("V1 Video", LayerType.VIDEO)
        track.height = 80
    is_img = is_image_file(source)
    layer = VideoLayer(
        name=os.path.basename(source),
        source=source,
        start=0.0,
        end=duration,
        volume=0.0 if is_img else 1.0,
        muted=True if is_img else False,
        transform=Transform(x=0, y=0, scale_x=1.0, scale_y=1.0),
    )
    if is_img:
        layer.metadata["media_type"] = "image"
    current = ordered_video_layers(timeline)
    insert_at = max(0, min(int(index), len(current)))
    current.insert(insert_at, layer)
    normalize_v1_sequence(timeline, current)
    return layer


def move_video(timeline: Timeline, layer_id: str, offset: int) -> bool:
    layers = ordered_video_layers(timeline)
    index = next((i for i, layer in enumerate(layers) if layer.id == layer_id), -1)
    target = index + int(offset)
    if index < 0 or target < 0 or target >= len(layers):
        return False
    layers[index], layers[target] = layers[target], layers[index]
    normalize_v1_sequence(timeline, layers)
    return True


def remove_video(timeline: Timeline, layer_id: str) -> bool:
    layers = ordered_video_layers(timeline)
    remaining = [layer for layer in layers if layer.id != layer_id]
    if len(remaining) == len(layers):
        return False
    normalize_v1_sequence(timeline, remaining)
    return True


def clip_is_image(clip) -> bool:
    """True when a timeline clip is a still image (intro/bumper), not video.

    ``get_timeline_video_clips()`` returns dicts from ``TimelineVideoClip.to_dict()``.
    ``getattr(clip, "is_image", False)`` is always False on a dict, so callers
    must use this helper (or ``is_image_file(source)``) instead.
    """
    if clip is None:
        return False
    if isinstance(clip, dict):
        if "is_image" in clip:
            return bool(clip.get("is_image"))
        return is_image_file(str(clip.get("source", "") or ""))
    explicit = getattr(clip, "is_image", None)
    if isinstance(explicit, bool):
        return explicit
    return is_image_file(str(getattr(clip, "source", "") or ""))


def clip_timeline_start(clip) -> float:
    try:
        if isinstance(clip, dict):
            return max(0.0, float(clip.get("timeline_start", 0.0) or 0.0))
        return max(0.0, float(getattr(clip, "timeline_start", 0.0) or 0.0))
    except (TypeError, ValueError):
        return 0.0


def resolve_timeline_content_offset(timeline_clips: list | None) -> float:
    """Calculate the global timeline offset where primary video content begins,
    accounting for preceding intro image/video bumper clips.
    This is the single source of truth for intro offset across all exporters.
    """
    if not timeline_clips:
        return 0.0
    for clip in timeline_clips:
        if clip_is_image(clip):
            continue
        if isinstance(clip, dict):
            source = str(clip.get("source", "") or "").strip()
            if source and is_image_file(source):
                continue
            if not source and "is_image" not in clip:
                continue
        return clip_timeline_start(clip)
    return 0.0


def is_already_timeline_relative(cues_or_segments: list[dict] | None, content_offset: float) -> bool:
    """Detect whether subtitles or audio cues are ALREADY positioned in timeline-relative space.
    Guards against double-offsetting when downstream exporters process cues.
    """
    if not cues_or_segments or content_offset <= 0.05:
        return True
    if any(bool(s.get("_timeline_relative")) for s in cues_or_segments if isinstance(s, dict)):
        return True
    first_start = float(cues_or_segments[0].get("start", 0.0) or 0.0)
    return first_start >= content_offset - 0.05


def resolve_source_audio_position_ms(
    local_ms: int,
    *,
    baked_offset_ms: int = 0,
    is_intro_image: bool = False,
) -> int | None:
    """Sidecar seek for a source-video-relative WAV (t=0 = first video frame).

    Intro images live on the timeline *before* that clock, so the return is
    ``None`` (mute) while an intro is showing. Otherwise the sidecar plays at
    local video time plus any intro that was baked into the WAV at mix time.
    """
    if is_intro_image:
        return None
    try:
        local = max(0, int(local_ms or 0))
    except (TypeError, ValueError):
        local = 0
    try:
        baked = max(0, int(baked_offset_ms or 0))
    except (TypeError, ValueError):
        baked = 0
    return local + baked


def resolve_voice_export_delay_seconds(
    content_offset: float,
    baked_offset: float = 0.0,
) -> float:
    """Silence to prepend (positive) or trim (negative) so voice sits on the timeline.

    Voice WAVs are mixed in source-video time. Export prepends the *current*
    intro duration minus whatever intro was already baked into the file.
    """
    try:
        current = max(0.0, float(content_offset or 0.0))
    except (TypeError, ValueError):
        current = 0.0
    try:
        baked = max(0.0, float(baked_offset or 0.0))
    except (TypeError, ValueError):
        baked = 0.0
    return round(current - baked, 3)

import os
import sys

import pytest

_app_dir = os.path.join(os.path.dirname(__file__), "..", "app")
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)

from app.layers.base import LayerType
from app.layers.timeline import Timeline, Track
from app.layers.subtitle import SubtitleLayer
from app.services.movie_review_service import (
    MovieReviewProject,
    MovieReviewScene,
    MovieReviewService,
    REVIEW_TRACK_NAME,
)
from ui.helpers.srt_helpers import format_segments_to_srt, parse_srt_to_segments


def _segments():
    return [
        {"start": 10.0, "end": 12.0, "text": "Anh đã đến."},
        {"start": 12.1, "end": 15.0, "text": "Cuối cùng cũng chịu xuất hiện."},
        {"start": 15.1, "end": 18.0, "text": "Tôi tưởng anh không dám quay lại."},
        {"start": 18.1, "end": 21.0, "text": "Chuyện năm đó chưa kết thúc."},
        {"start": 28.0, "end": 31.0, "text": "Ở một nơi khác."},
        {"start": 31.1, "end": 34.0, "text": "Cô gái mở cánh cửa."},
    ]


def test_groups_consecutive_subtitles_as_scenes_and_preserves_source_ids():
    scenes = MovieReviewService().group_subtitles_into_scenes(_segments())
    assert len(scenes) == 2
    assert scenes[0].source_cue_ids == [1, 2, 3, 4]
    assert scenes[0].start == 10.0
    assert scenes[0].end == 21.0
    assert scenes[1].source_cue_ids == [5, 6]


def test_scene_cut_can_split_a_long_continuous_dialogue():
    scenes = MovieReviewService().group_subtitles_into_scenes(
        _segments()[:4],
        detected_scenes=[{"start_time": 15.05}],
    )
    assert [scene.source_cue_ids for scene in scenes] == [[1, 2], [3, 4]]


def test_cut_scan_is_restricted_to_the_subtitle_window():
    service = MovieReviewService()
    captured = {}

    class _Engine:
        def detect_scene_cuts(self, video_path, start, end, *, threshold=0.3, total_budget_seconds=45.0):
            captured.update(
                video_path=video_path, start=start, end=end,
                threshold=threshold, budget=total_budget_seconds,
            )
            return [15.05]

    service.scene_engine = _Engine()
    segments = _segments()[:4]
    scenes = service.detect_and_group("movie.mp4", segments, scan_budget_seconds=12.0)

    # Only the SRT span is scanned: intros/credits outside it are never decoded.
    assert captured["start"] == 10.0
    assert captured["end"] == 21.0
    assert captured["video_path"] == "movie.mp4"
    assert captured["budget"] == 12.0
    assert [scene.source_cue_ids for scene in scenes] == [[1, 2], [3, 4]]


def test_source_time_window_tolerates_broken_cues():
    assert MovieReviewService.source_time_window([]) == (0.0, 0.0)
    assert MovieReviewService.source_time_window([
        {"start": 5.0, "end": 7.0},
        {"start": "bad", "end": 3.0},
        {"start": 12.5, "end": 20.0},
    ]) == (5.0, 20.0)


def test_context_expands_without_changing_scene_source_links():
    service = MovieReviewService()
    project = MovieReviewProject(source_segments=_segments())
    project.scenes = service.group_subtitles_into_scenes(project.source_segments)
    original_links = list(project.scenes[1].source_cue_ids)
    project.scenes[1].context_radius = 2
    context = service.context_payload(project, 1)
    assert context["before_ids"] == [1, 2, 3, 4]
    assert project.scenes[1].source_cue_ids == original_links


def test_story_arc_windows_group_consecutive_scenes_before_narration():
    scenes = [
        MovieReviewScene("SCENE-0001", 0, 8, [1], ["a"]),
        MovieReviewScene("SCENE-0002", 11, 20, [2], ["b"]),
        MovieReviewScene("SCENE-0003", 25, 35, [3], ["c"]),
        MovieReviewScene("SCENE-0004", 80, 90, [4], ["d"]),
    ]
    project = MovieReviewProject(scenes=scenes)

    assert MovieReviewService.story_arc_windows(project) == [(0, 3), (3, 4)]


def test_normal_review_srt_maps_to_original_cues_by_timestamp():
    service = MovieReviewService()
    project = MovieReviewProject(source_segments=[
        {"start": 10.0, "end": 13.0, "text": "Anh ta bước vào."},
        {"start": 13.0, "end": 17.0, "text": "Mọi thứ im lặng."},
        {"start": 17.0, "end": 21.0, "text": "Có tiếng động."},
    ])
    review = service.import_review_srt(project, [
        {"start": 10.0, "end": 17.0, "text": "Anh ta bước vào căn nhà yên tĩnh."},
        {"start": 17.0, "end": 21.0, "text": "Một tiếng động khiến anh cảnh giác."},
    ])
    assert [item.source_cue_ids for item in review] == [[1, 2], [3]]
    assert project.scenes
    assert "Anh ta bước vào căn nhà yên tĩnh." in project.scenes[0].review_text
    assert "Một tiếng động khiến anh cảnh giác." in project.scenes[0].review_text
    assert all(scene.source_cue_ids for scene in project.scenes)


def test_metadata_review_srt_uses_explicit_source_links():
    service = MovieReviewService()
    project = MovieReviewProject(source_segments=[
        {"start": 10.0, "end": 13.0, "text": "Một."},
        {"start": 13.0, "end": 17.0, "text": "Hai."},
    ])
    review = service.import_review_srt(
        project,
        [{"start": 10.0, "end": 17.0, "text": "Tóm tắt."}],
        {"segments": [{
            "source_cue_ids": [2], "source_start": 13.0, "source_end": 17.0,
            "edit_action": "SPEED_UP", "speed": 1.2,
        }]},
    )
    assert review[0].source_cue_ids == [2]
    assert project.scenes[0].edit_plan[0]["action"] == "SPEED_UP"
    assert project.scenes[0].edit_plan[0]["speed"] == 1.2


def test_edit_plan_normalizes_actions_and_preserves_source_links():
    service = MovieReviewService()
    scene = MovieReviewScene("SCENE-0001", 10.0, 21.0, [1, 2, 3, 4], ["a", "b", "c", "d"])
    plan = service.normalize_edit_plan(scene, [
        {"start": 10, "end": 17, "action": "SPEED_UP", "speed": 1.2, "source_cue_ids": [1, 2]},
        {"start": 17, "end": 21, "action": "FREEZE", "freeze_duration": 2, "source_cue_ids": [3, 4]},
    ])
    assert [item["action"] for item in plan] == ["SPEED_UP", "KEEP"]
    assert plan[0]["speed"] == 1.2
    assert plan[1]["freeze_duration"] == 2.0
    assert plan[1]["source_cue_ids"] == [3, 4]


def test_edit_plan_clamps_limits_and_rejects_strong_action_without_context():
    service = MovieReviewService()
    scene = MovieReviewScene("SCENE-0001", 10.0, 12.0, [1], ["Anh ta mở cửa."])
    plan = service.normalize_edit_plan(scene, [
        {"start": 10, "end": 12, "action": "FREEZE", "freeze_duration": 20, "speed": 2.0},
    ])
    assert plan == [{
        "start": 10.0,
        "end": 12.0,
        "action": "KEEP",
        "speed": 1.0,
        "freeze_duration": 0.0,
        "source_cue_ids": [1],
        "reason": "",
    }]

    scene.context_after_ids = [2]
    plan = service.normalize_edit_plan(scene, [
        {"start": 10, "end": 12, "action": "FREEZE", "freeze_duration": 20},
    ])
    assert plan[0]["action"] == "KEEP"
    assert plan[0]["freeze_duration"] == service.MAX_HOLD_DURATION

    plan = service.normalize_edit_plan(scene, [
        {"start": 10, "end": 12, "action": "SPEED_UP", "speed": 2.0},
    ])
    assert plan[0]["speed"] == service.MAX_EDIT_SPEED


def test_edit_decisions_remove_cut_and_shift_output_clock():
    service = MovieReviewService()
    scene = MovieReviewScene("SCENE-0001", 0.0, 10.0, [1, 2], ["a", "b"])
    scene.edit_plan = [
        {"start": 0.0, "end": 4.0, "action": "CUT", "source_cue_ids": [1]},
        {"start": 4.0, "end": 10.0, "action": "KEEP", "source_cue_ids": [2]},
    ]
    project = MovieReviewProject(scenes=[scene])
    decisions = service.build_edit_decisions(project, 10.0)
    assert [item.action_type for item in decisions] == ["CUT", "KEEP"]
    assert sum(item.output_duration for item in decisions) == pytest.approx(6.0)
    assert scene.edit_output_start == 0.0
    assert scene.edit_output_end == 6.0


def test_recap_pacing_cuts_long_inter_scene_gap_and_shifts_output_clock():
    service = MovieReviewService()
    first = MovieReviewScene("SCENE-0001", 0.0, 4.0, [1, 2], ["a", "b"], review_text="Cảnh một.", tts_duration=2.0)
    second = MovieReviewScene("SCENE-0002", 14.0, 18.0, [3, 4], ["c", "d"], review_text="Cảnh hai.", tts_duration=2.0)
    project = MovieReviewProject(scenes=[first, second], auto_recap_pacing=True)

    decisions = service.build_edit_decisions(project, 18.0)

    gap_decisions = [item for item in decisions if item.source_clip_id == "source_gap"]
    assert [item.action_type for item in gap_decisions] == ["KEEP", "CUT", "KEEP"]
    assert sum(item.output_duration for item in gap_decisions) == pytest.approx(1.8)
    assert second.edit_output_start == pytest.approx(5.8)


def test_recap_pacing_compacts_keep_only_scene_but_preserves_head_and_tail():
    service = MovieReviewService()
    scene = MovieReviewScene(
        "SCENE-0001", 0.0, 30.0, [1, 2], ["a", "b"],
        review_text="Một câu kể ngắn.", tts_duration=4.0,
        edit_plan=[{"start": 0.0, "end": 30.0, "action": "KEEP", "source_cue_ids": [1, 2]}],
    )
    project = MovieReviewProject(scenes=[scene], auto_recap_pacing=True)

    decisions = service.build_edit_decisions(project, 30.0)

    assert [item.action_type for item in decisions] == ["KEEP", "CUT", "KEEP"]
    assert decisions[0].end_time == pytest.approx(5.0)
    assert decisions[-1].duration == pytest.approx(1.5)
    assert sum(item.output_duration for item in decisions) == pytest.approx(6.5)


def test_recap_pacing_can_be_disabled_to_preserve_source_timing():
    service = MovieReviewService()
    first = MovieReviewScene("SCENE-0001", 0.0, 2.0, [1], ["a"], review_text="Một.", tts_duration=1.0)
    second = MovieReviewScene("SCENE-0002", 12.0, 14.0, [2], ["b"], review_text="Hai.", tts_duration=1.0)
    project = MovieReviewProject(scenes=[first, second], auto_recap_pacing=False)

    decisions = service.build_edit_decisions(project, 14.0)

    gap = [item for item in decisions if item.source_clip_id == "source_gap"]
    assert len(gap) == 1
    assert gap[0].action_type == "KEEP"
    assert gap[0].duration == pytest.approx(10.0)


def test_narration_plan_infers_story_pace_and_clamps_model_values():
    scene = MovieReviewScene(
        "SCENE-0001", 0.0, 12.0, [1, 2], ["a", "b"],
        review_text="Thế nhưng anh không có dị năng. Ngay lúc đó, tang thi lao tới!",
    )
    plan = MovieReviewService.normalize_narration_plan(scene, [
        {"text": "Thế nhưng anh không có dị năng.", "pace": "slow", "speed": 0.2,
         "pause_before_ms": 5000, "pause_after_ms": 300, "emphasis": ["không có dị năng", "không tồn tại"]},
        {"text": "Ngay lúc đó, tang thi lao tới!", "pace": "fast", "speed": 2.0},
    ])

    assert [item["pace"] for item in plan] == ["slow", "fast"]
    assert plan[0]["speed"] == MovieReviewService.MIN_NARRATION_SPEED
    assert plan[1]["speed"] == MovieReviewService.MAX_NARRATION_SPEED
    assert plan[0]["pause_before_ms"] == MovieReviewService.MAX_NARRATION_PAUSE_MS
    assert plan[0]["emphasis"] == ["không có dị năng"]


def test_narration_plan_never_rewrites_approved_sentence():
    scene = MovieReviewScene(
        "SCENE-0001", 0.0, 5.0, [1], ["a"],
        review_text="Phương Nguyên mở chiếc hộp đen.",
    )
    plan = MovieReviewService.normalize_narration_plan(scene, [
        {"text": "Một nội dung bịa hoàn toàn khác.", "speed": 1.0},
    ])
    assert plan[0]["text"] == scene.review_text


def test_timing_preserves_source_duration_without_automatic_speed_or_freeze():
    service = MovieReviewService()
    first = MovieReviewScene("SCENE-0001", 0.0, 4.0, [1], ["source"])
    second = MovieReviewScene("SCENE-0002", 5.5, 8.0, [2], ["source 2"])
    first.review_text = " ".join(["Một câu review khá dài"] * 12) + "."
    project = MovieReviewProject(scenes=[first, second])
    service.plan_hybrid_timing(project, 0)
    assert first.voice_speed == 1.0
    assert first.freeze_duration == 0.0
    assert first.review_segments
    assert all(item.source_cue_ids == [1] for item in first.review_segments)


def test_project_hybrid_clock_shifts_later_review_only_after_manual_freeze():
    service = MovieReviewService()
    first = MovieReviewScene("SCENE-0001", 0.0, 2.0, [1], ["a"], review_text=" ".join(["dài"] * 30))
    second = MovieReviewScene("SCENE-0002", 2.0, 5.0, [2], ["b"], review_text="Cảnh tiếp theo.")
    first.freeze_manual = True
    first.freeze_duration = 1.5
    project = MovieReviewProject(scenes=[first, second])
    service.plan_project_hybrid(project)
    assert first.freeze_duration == 1.5
    assert second.review_segments[0].start >= second.start + 1.5 - 0.001
    assert first.review_segments[-1].end <= second.review_segments[0].start + 0.001


def test_rendered_review_caption_ends_with_measured_tts_not_whole_scene(tmp_path):
    service = MovieReviewService()
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"rendered")
    scene = MovieReviewScene(
        "SCENE-0001", 0.0, 10.0, [1], ["source"],
        review_text="Một câu ngắn.", tts_duration=2.4,
        tts_audio_path=str(audio), tts_rendered=True,
    )
    project = MovieReviewProject(scenes=[scene])

    service.plan_project_hybrid(project)

    assert scene.review_segments[-1].end == pytest.approx(2.4)


def test_validation_finds_low_confidence_unapproved_and_duplicate():
    service = MovieReviewService()
    scenes = [
        MovieReviewScene("SCENE-0001", 0, 3, [1], ["a"], review_text="Người đàn ông bước vào phòng.", confidence=0.9, source_alignment=0.9, approved=True),
        MovieReviewScene("SCENE-0002", 3, 6, [2], ["b"], review_text="Người đàn ông bước vào phòng.", confidence=0.4, source_alignment=0.3, approved=False),
    ]
    project = MovieReviewProject(scenes=scenes)
    for index in range(2):
        service.plan_hybrid_timing(project, index)
    codes = {item["code"] for item in service.validate_project(project)}
    assert {"low_confidence", "source_mismatch", "not_approved", "duplicate_review"} <= codes


def test_review_project_roundtrip_and_separate_timeline_track(tmp_path):
    service = MovieReviewService()
    scene = MovieReviewScene(
        "SCENE-0001", 1.0, 5.0, [7, 8], ["a", "b"],
        review_text="Hai người gặp nhau.", confidence=0.91, source_alignment=0.95, approved=True,
    )
    project = MovieReviewProject(video_path="movie.mp4", srt_path="source.srt", source_segments=_segments(), scenes=[scene])
    service.plan_hybrid_timing(project, 0)
    path = tmp_path / "movie_review.json"
    service.save(project, str(path))
    loaded = service.load(str(path))
    assert loaded.scenes[0].source_cue_ids == [7, 8]

    original = Track(name="S1 Original", type=LayerType.SUBTITLE)
    original.layers.append(SubtitleLayer(start=1, end=2, text="original"))
    timeline = Timeline(tracks=[original])
    layers = service.sync_review_track(timeline, loaded)
    assert original.layers[0].text == "original"
    review_track = next(track for track in timeline.tracks if track.name == REVIEW_TRACK_NAME)
    assert review_track is not original
    assert review_track.metadata["preserves_source_srt"] is True
    assert layers[0].metadata["source_cue_ids"] == [7, 8]


def test_uncertain_scenes_warn_without_blocking_export():
    service = MovieReviewService()
    scene = MovieReviewScene(
        "SCENE-0001", 0.0, 3.0, [1], ["a"],
        review_text="Một cảnh mơ hồ.", confidence=0.2, source_alignment=0.3, approved=False,
    )
    project = MovieReviewProject(scenes=[scene])
    service.plan_hybrid_timing(project, 0)
    issues = service.validate_project(project)
    codes = {item["code"] for item in issues}
    assert {"low_confidence", "source_mismatch", "not_approved"} <= codes
    # A 60-scene movie must stay exportable after a review pass, so these stay
    # advisory: they are reported but do not invalidate the output.
    assert service.blocking_issues(issues) == []
    assert {item["code"] for item in service.advisory_issues(issues)} >= {"low_confidence"}


def test_structurally_broken_scenes_still_block_export():
    service = MovieReviewService()
    scene = MovieReviewScene(
        "SCENE-0001", 4.0, 4.0, [], [],
        review_text="", confidence=0.9, source_alignment=0.9, approved=True,
    )
    project = MovieReviewProject(scenes=[scene])
    codes = {item["code"] for item in service.blocking_issues(service.validate_project(project))}
    assert {"invalid_timestamp", "missing_source_link", "missing_review"} <= codes


def test_manual_freeze_survives_replan_and_shifts_later_scenes():
    service = MovieReviewService()
    first = MovieReviewScene("SCENE-0001", 0.0, 5.0, [1], ["a"], review_text="Một cảnh rất ngắn.")
    second = MovieReviewScene("SCENE-0002", 5.5, 8.0, [2], ["b"], review_text="Cảnh tiếp theo.")
    project = MovieReviewProject(scenes=[first, second])
    service.plan_hybrid_timing(project, 0)
    assert first.freeze_duration == 0.0

    first.freeze_manual = True
    first.freeze_duration = 2.0
    service.plan_project_hybrid(project)

    assert first.freeze_duration == 2.0
    assert second.review_segments[0].start >= second.start + 2.0 - 0.001


def test_manual_freeze_survives_ai_plan_on_another_scene():
    service = MovieReviewService()
    first = MovieReviewScene("SCENE-0001", 0.0, 5.0, [1], ["a"], review_text="Một cảnh rất ngắn.")
    second = MovieReviewScene("SCENE-0002", 5.5, 8.0, [2], ["b"], review_text="Cảnh tiếp theo.")
    second.edit_plan = [{"start": 5.5, "end": 8.0, "action": "KEEP"}]
    second.has_ai_edit_plan = True
    first.freeze_manual = True
    first.freeze_duration = 2.0
    project = MovieReviewProject(scenes=[first, second])

    service.plan_project_hybrid(project)

    assert first.has_ai_edit_plan is False
    assert first.edit_plan[0]["freeze_duration"] == 2.0


def test_hold_decisions_cover_source_timeline_and_add_holds_in_order():
    service = MovieReviewService()
    first = MovieReviewScene("SCENE-0001", 0.0, 4.0, [1], ["a"], review_text="Cảnh một.")
    second = MovieReviewScene("SCENE-0002", 4.0, 9.0, [2], ["b"], review_text="Cảnh hai.")
    first.freeze_manual = True
    first.freeze_duration = 1.5
    project = MovieReviewProject(scenes=[first, second])

    decisions = service.build_hold_decisions(project, 12.0)

    # One shot ends at the held scene's end, the rest of the movie follows it.
    assert [d.start_time for d in decisions] == [0.0, 4.0]
    assert [d.end_time for d in decisions] == [4.0, 12.0]
    assert decisions[0].freeze_duration == 1.5
    assert decisions[1].freeze_duration == 0.0
    # 12s of source plus the 1.5s hold inserted at the first scene's end: this
    # is the clock the review subtitles and TTS delays were planned on.
    assert sum(d.output_duration for d in decisions) == pytest.approx(13.5)


def test_review_srt_formatter_keeps_valid_timestamps():
    rendered = format_segments_to_srt([{"start": 1.25, "end": 3.5, "text": "Lời review."}])
    assert "00:00:01,250 --> 00:00:03,500" in rendered
    assert parse_srt_to_segments(rendered) == [{"start": 1.25, "end": 3.5, "text": "Lời review."}]

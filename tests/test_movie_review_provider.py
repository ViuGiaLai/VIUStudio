import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "ui"), str(ROOT / "app"), str(ROOT)]

from app.services.movie_review_service import (
    GeminiMovieReviewClient,
    MovieReviewProject,
    MovieReviewScene,
    MovieReviewService,
)
from app.services.gemini_key_pool import GeminiKeyPool


class _FakeProvider:
    """Minimal stand-in for the app's OpenAI-compatible polisher provider."""

    provider_id = "openai"
    display_name = "Fake Provider"
    config_error = ""
    model_name = "fake-model"
    api_key = "test-key"

    def __init__(self, content: str, configured: bool = True):
        self._content = content
        self._configured = configured
        self.calls: list[dict] = []
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.calls.append(kwargs)
                message = SimpleNamespace(content=outer._content)
                return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        completions = _Completions()
        self.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    def is_configured(self) -> bool:
        return self._configured

    def _get_client(self):
        return self.client


def _project() -> MovieReviewProject:
    scene = MovieReviewScene("SCENE-0001", 1.0, 4.0, [1], ["Anh ấy mở cửa."])
    return MovieReviewProject(
        video_path="movie.mp4",
        srt_path="source.srt",
        source_segments=[{"start": 1.0, "end": 4.0, "text": "Anh ấy mở cửa."}],
        scenes=[scene],
    )


def test_review_scene_sends_scene_context_and_parses_model_json():
    provider = _FakeProvider(json.dumps({
        "review_text": "Người đàn ông mở cánh cửa.",
        "summary": "Mở cửa",
        "confidence": 0.8,
        "source_alignment": 0.9,
        "needs_more_context": False,
        "reason": "ok",
    }))
    client = GeminiMovieReviewClient()
    with patch.object(client.orchestrator, "_resolve_ai_provider", return_value=("openai", provider)):
        payload = client.review_scene(_project(), 0)

    assert payload["review_text"] == "Người đàn ông mở cánh cửa."
    assert payload["source_alignment"] == 0.9
    assert payload["provider"] == "openai"

    prompt = provider.calls[0]["messages"][0]["content"]
    # The scene's own subtitles and its source cue ids must reach the model.
    assert "SCENE-0001" in prompt
    assert "[1.000-4.000] #1: Anh ấy mở cửa." in prompt
    assert "story state và Glossary" in prompt
    assert "story_beat" in prompt
    assert "Chưa lập edit plan ở bước này" in prompt
    assert isinstance(prompt, str)
    assert provider.calls[0]["model"] == "fake-model"


def test_edit_plan_is_requested_only_after_review_script_exists():
    provider = _FakeProvider(json.dumps({
        "edit_plan": [{
            "start": 1.0, "end": 4.0, "action": "KEEP", "speed": 1.0,
            "freeze_duration": 0.0, "source_cue_ids": [1], "reason": "Khớp narration",
        }],
    }))
    client = GeminiMovieReviewClient()
    with patch.object(client.orchestrator, "_resolve_ai_provider", return_value=("openai", provider)):
        payload = client.plan_edit_scene(
            _project(), 0,
            review_payload={
                "review_text": "Người đàn ông mở cánh cửa.",
                "story_beat": {"what": "Mở cửa", "who": "Người đàn ông"},
            },
        )

    assert payload["edit_plan"][0]["action"] == "KEEP"
    prompt = provider.calls[0]["messages"][0]["content"]
    assert "lập EDIT PLAN sau khi Review Script" in prompt
    assert "Người đàn ông mở cánh cửa." in prompt


def test_review_text_is_trimmed_to_the_available_duration():
    text = "Một câu ngắn. " + " ".join(["Một câu rất dài"] * 30) + "."
    trimmed = MovieReviewService.fit_review_to_duration(text, 2.0)
    assert trimmed == "Một câu ngắn."
    assert MovieReviewService.estimate_tts_duration(trimmed) / 1.12 <= 2.0


def test_single_sentence_is_never_cut_into_an_incomplete_fragment():
    text = "Phương Nguyên vừa xuyên không thì đúng lúc tận thế bất ngờ ập đến."
    assert MovieReviewService.fit_review_to_duration(text, 1.0) == text


def test_story_arc_is_written_continuously_before_scene_allocation():
    project = _project()
    project.scenes.append(MovieReviewScene("SCENE-0002", 4.5, 7.0, [2], ["Anh bỏ chạy."]))
    project.source_segments.append({"start": 4.5, "end": 7.0, "text": "Anh bỏ chạy."})
    provider = _FakeProvider(json.dumps({
        "continuous_narration": "Anh mở cửa rồi lập tức bỏ chạy.",
        "scene_reviews": [
            {"scene_id": "SCENE-0001", "review_text": "Anh mở cửa.", "confidence": .9, "source_alignment": .9},
            {"scene_id": "SCENE-0002", "review_text": "Ngay sau đó, anh bỏ chạy.", "confidence": .9, "source_alignment": .9},
        ],
    }))
    client = GeminiMovieReviewClient()
    with patch.object(client.orchestrator, "_resolve_ai_provider", return_value=("openai", provider)):
        payload = client.review_story_arc(project, 0, 2, context_clip_path="arc.mp4")

    assert len(payload["scene_reviews"]) == 2
    prompt = provider.calls[0]["messages"][0]["content"]
    assert "Viết continuous_narration" in prompt
    assert "Sau khi mạch kể đã hoàn chỉnh, mới chia câu kể" in prompt
    assert "SCENE-0001" in prompt and "SCENE-0002" in prompt
    assert provider.calls[0]["max_tokens"] >= 8192


def test_story_arc_reports_progress_while_waiting_for_the_model():
    project = _project()
    provider = _FakeProvider(json.dumps({
        "continuous_narration": "Anh mở cửa.",
        "scene_reviews": [
            {"scene_id": "SCENE-0001", "review_text": "Anh mở cửa.", "confidence": .9, "source_alignment": .9},
        ],
    }))
    messages = []
    client = GeminiMovieReviewClient()
    with patch.object(client.orchestrator, "_resolve_ai_provider", return_value=("openai", provider)):
        client.review_story_arc(
            project, 0, 1, context_clip_path="arc.mp4",
            progress_callback=messages.append,
        )

    assert messages
    assert any("đang viết" in item for item in messages)


def test_review_scene_accepts_fenced_json_and_extra_prose():
    provider = _FakeProvider(
        "Đây là kết quả:\n```json\n"
        '{"review_text": "Cảnh yên tĩnh.", "confidence": 0.7, "needs_more_context": true}\n'
        "```\n"
    )
    client = GeminiMovieReviewClient()
    with patch.object(client.orchestrator, "_resolve_ai_provider", return_value=("openai", provider)):
        payload = client.review_scene(_project(), 0)

    assert payload["review_text"] == "Cảnh yên tĩnh."
    assert payload["needs_more_context"] is True


def test_review_scene_rejects_unconfigured_provider_with_actionable_error():
    provider = _FakeProvider("{}", configured=False)
    provider.config_error = "API key/model missing"
    client = GeminiMovieReviewClient()
    with patch.object(client.orchestrator, "_resolve_ai_provider", return_value=("openai", provider)):
        try:
            client.review_scene(_project(), 0)
        except RuntimeError as exc:
            assert "Fake Provider" in str(exc)
            assert "API key/model missing" in str(exc)
        else:  # pragma: no cover - defensive
            raise AssertionError("an unconfigured provider must not be used silently")


def test_native_gemini_rotates_to_second_key_after_quota(tmp_path):
    clip = tmp_path / "scene.mp4"
    clip.write_bytes(b"video")
    pool_path = tmp_path / "gemini_keys.json"
    pool = GeminiKeyPool(str(pool_path))
    first = pool.upsert("Key 1", "quota-key")
    second = pool.upsert("Key 2", "working-key")
    scene = MovieReviewScene("SCENE-0001", 0, 2, [1], ["cue"], context_clip_path=str(clip))
    provider = _FakeProvider("{}")
    provider.model_name = "gemini-test"
    provider.api_key = ""

    class _Response:
        def __init__(self, key):
            self.key = key

        def raise_for_status(self):
            if self.key == "quota-key":
                from requests import HTTPError
                error = HTTPError("429 quota exhausted")
                error.response = SimpleNamespace(status_code=429)
                raise error

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": '{"review_text":"ok"}'}]}}]}

    used = []

    def fake_post(_url, *, headers, **_kwargs):
        used.append(headers["x-goog-api-key"])
        return _Response(headers["x-goog-api-key"])

    old_path = os.environ.get("GEMINI_KEY_POOL_FILE")
    os.environ["GEMINI_KEY_POOL_FILE"] = str(pool_path)
    try:
        client = GeminiMovieReviewClient()
        with patch.object(client.orchestrator, "_resolve_ai_provider", return_value=("google_ai_studio", provider)), \
             patch("requests.post", side_effect=fake_post):
            payload = client._request_native_gemini(provider, scene, "prompt")
    finally:
        if old_path is None:
            os.environ.pop("GEMINI_KEY_POOL_FILE", None)
        else:
            os.environ["GEMINI_KEY_POOL_FILE"] = old_path

    assert used == ["quota-key", "working-key"]
    assert payload["key_id"] == second.id
    entries = {item.id: item for item in pool.load()}
    assert entries[first.id].fail_count == 1
    assert entries[second.id].fail_count == 0


def test_native_gemini_reports_key_rotation_progress(tmp_path):
    clip = tmp_path / "scene.mp4"
    clip.write_bytes(b"video")
    pool_path = tmp_path / "gemini_keys.json"
    pool = GeminiKeyPool(str(pool_path))
    pool.upsert("Key 1", "quota-key")
    second = pool.upsert("Key 2", "working-key")
    scene = MovieReviewScene("SCENE-0001", 0, 2, [1], ["cue"], context_clip_path=str(clip))
    provider = _FakeProvider("{}")
    provider.model_name = "gemini-test"
    provider.api_key = ""

    class _Response:
        def __init__(self, key):
            self.key = key

        def raise_for_status(self):
            if self.key == "quota-key":
                from requests import HTTPError
                error = HTTPError("429 quota exhausted")
                error.response = SimpleNamespace(status_code=429)
                raise error

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": '{"review_text":"ok"}'}]}}]}

    def fake_post(_url, *, headers, **_kwargs):
        return _Response(headers["x-goog-api-key"])

    messages = []
    old_path = os.environ.get("GEMINI_KEY_POOL_FILE")
    os.environ["GEMINI_KEY_POOL_FILE"] = str(pool_path)
    try:
        client = GeminiMovieReviewClient()
        with patch.object(client.orchestrator, "_resolve_ai_provider", return_value=("google_ai_studio", provider)), \
             patch("requests.post", side_effect=fake_post):
            payload = client._request_native_gemini(
                provider, scene, "prompt", progress_callback=messages.append,
            )
    finally:
        if old_path is None:
            os.environ.pop("GEMINI_KEY_POOL_FILE", None)
        else:
            os.environ["GEMINI_KEY_POOL_FILE"] = old_path

    assert payload["key_id"] == second.id
    assert any("đóng gói" in item for item in messages)
    assert any("Key 1" in item or "quota" in item.lower() or "lỗi" in item for item in messages)


def test_gemini_heartbeat_keeps_emitting_while_a_request_is_blocked():
    import time as time_module

    messages = []
    previous = GeminiMovieReviewClient.REQUEST_HEARTBEAT_SEC
    GeminiMovieReviewClient.REQUEST_HEARTBEAT_SEC = 0.04
    try:
        result = GeminiMovieReviewClient._run_with_heartbeat(
            messages.append,
            "Gemini đang viết ARC-1",
            lambda: time_module.sleep(0.12) or "ok",
        )
    finally:
        GeminiMovieReviewClient.REQUEST_HEARTBEAT_SEC = previous

    assert result == "ok"
    assert messages[0] == "Gemini đang viết ARC-1"
    assert any("đã chờ" in item for item in messages)

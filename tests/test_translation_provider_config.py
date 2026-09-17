import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "app"), str(ROOT / "ui")]

from app.translation.providers.gemini_polisher import OpenAICompatiblePolisherProvider
from ui.features.voice_catalog import VoiceCatalogMixin


class _Combo:
    def __init__(self, data):
        self.data = data

    def currentData(self):
        return self.data


class _ModelCombo:
    def __init__(self, items=None):
        self.items = list(items or [])
        self.index = 0 if self.items else -1
        self.signals_blocked = False

    def currentData(self):
        return self.items[self.index][1] if 0 <= self.index < len(self.items) else ""

    def clear(self):
        self.items.clear()
        self.index = -1

    def addItem(self, label, data):
        self.items.append((label, data))
        if self.index < 0:
            self.index = 0

    def itemData(self, index):
        return self.items[index][1]

    def count(self):
        return len(self.items)

    def setCurrentIndex(self, index):
        self.index = index

    def blockSignals(self, blocked):
        previous = self.signals_blocked
        self.signals_blocked = bool(blocked)
        return previous


class _Widget:
    def setVisible(self, _visible):
        pass

    def setText(self, _text):
        pass


class _LineEdit:
    def __init__(self, value=""):
        self.value = value

    def text(self):
        return self.value


class _ProviderHarness(VoiceCatalogMixin):
    def __init__(self):
        self.translation_engine_combo = _Combo("llama_app")
        self.translation_config_panel = _Widget()
        self.llama_app_config_panel = _Widget()
        self.translation_test_status = _Widget()
        self.llama_model_combo = _Combo("")
        self.translation_api_key_edit = _LineEdit("")
        self.translation_model_edit = _LineEdit("")
        self.translation_base_url_edit = _LineEdit("")
        self.current_project_state = None
        self.project_service = None

    def log(self, _message):
        pass

    def _refresh_llama_models_list(self):
        pass


class _ModelSelectionHarness(VoiceCatalogMixin):
    def __init__(self, combo):
        self.llama_model_combo = combo
        self._llama_buttons_connected = True


class TranslationProviderConfigTests(unittest.TestCase):
    def test_recommended_model_download_visibility_uses_detected_files(self):
        availability = VoiceCatalogMixin._llama_recommended_model_availability([
            "D:/models/HY-MT1.5-1.8B-Q4_K_M.gguf",
            "D:/models/Qwen3-4B-Q4_K_M.gguf",
        ])

        self.assertTrue(availability["hy_mt_1_8b"])
        self.assertTrue(availability["qwen3_4b"])
        self.assertFalse(availability["qwen2_5_1_5b"])

    def test_scanned_model_replaces_old_visible_local_model(self):
        with tempfile.TemporaryDirectory() as root:
            model_dir = Path(root, "managed")
            model_dir.mkdir()
            hy_model = model_dir / "HY-MT1.5-1.8B-Q4_K_M.gguf"
            hy_model.touch()
            qwen_model = Path(root, "Qwen3-4B-Q4_K_M.gguf")
            qwen_model.touch()
            combo = _ModelCombo([("HY-MT (Ready)", str(hy_model))])
            harness = _ModelSelectionHarness(combo)
            manager = SimpleNamespace(models_dir=str(model_dir))

            with patch(
                "app.services.llama_local_manager.LlamaServerManager.get_instance",
                return_value=manager,
            ):
                harness._refresh_llama_models_list(
                    preferred_model_path=str(qwen_model)
                )

            self.assertEqual(
                os.path.normcase(os.path.abspath(combo.currentData())),
                os.path.normcase(os.path.abspath(qwen_model)),
            )
            self.assertIn("Qwen3-4B-Q4_K_M.gguf (Selected)", combo.items[combo.index][0])

    def test_llama_preflight_persists_provider_for_worker_process(self):
        previous_provider = os.environ.get("OPENAI_PROVIDER")
        previous_polisher = os.environ.get("AI_POLISHER_PROVIDER")
        try:
            with tempfile.TemporaryDirectory() as root:
                Path(root, ".env").write_text(
                    "OPENAI_PROVIDER=google_ai_studio\nAI_POLISHER_PROVIDER=google_ai_studio\n",
                    encoding="utf-8",
                )
                model_path = Path(root, "selected.gguf")
                model_path.touch()
                harness = _ProviderHarness()
                harness.llama_model_combo = _Combo(str(model_path))
                with patch("ui.features.voice_catalog.workspace_root", return_value=root):
                    configured, error = harness.prepare_translation_runtime()
                self.assertTrue(configured, error)
                content = Path(root, ".env").read_text(encoding="utf-8")
                self.assertIn("OPENAI_PROVIDER=llama_app", content)
                self.assertIn("AI_POLISHER_PROVIDER=llama_app", content)
        finally:
            if previous_provider is None:
                os.environ.pop("OPENAI_PROVIDER", None)
            else:
                os.environ["OPENAI_PROVIDER"] = previous_provider
            if previous_polisher is None:
                os.environ.pop("AI_POLISHER_PROVIDER", None)
            else:
                os.environ["AI_POLISHER_PROVIDER"] = previous_polisher

    def test_gemini_preflight_locks_visible_provider_and_credentials(self):
        old_values = {
            key: os.environ.get(key)
            for key in (
                "OPENAI_PROVIDER", "AI_POLISHER_PROVIDER", "GOOGLE_AI_STUDIO_API_KEY",
                "GOOGLE_AI_STUDIO_MODEL", "GOOGLE_AI_STUDIO_BASE_URL",
            )
        }
        try:
            with tempfile.TemporaryDirectory() as root:
                Path(root, ".env").write_text(
                    "OPENAI_PROVIDER=llama_app\nAI_POLISHER_PROVIDER=llama_app\n",
                    encoding="utf-8",
                )
                harness = _ProviderHarness()
                harness.translation_engine_combo = _Combo("google_ai_studio")
                harness.translation_api_key_edit = _LineEdit("gemini-test-key")
                harness.translation_model_edit = _LineEdit("gemini-3.6-flash")
                harness.translation_base_url_edit = _LineEdit(
                    "https://generativelanguage.googleapis.com/v1beta/openai/"
                )
                with patch("ui.features.voice_catalog.workspace_root", return_value=root):
                    configured, error = harness.prepare_translation_runtime()

                self.assertTrue(configured, error)
                self.assertEqual(os.environ["OPENAI_PROVIDER"], "google_ai_studio")
                content = Path(root, ".env").read_text(encoding="utf-8")
                self.assertIn("OPENAI_PROVIDER=google_ai_studio", content)
                self.assertIn("AI_POLISHER_PROVIDER=google_ai_studio", content)
                self.assertIn("GOOGLE_AI_STUDIO_API_KEY=gemini-test-key", content)
                self.assertIn("GOOGLE_AI_STUDIO_MODEL=gemini-3.6-flash", content)
        finally:
            for key, value in old_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_hy_mt_uses_native_one_segment_translation_prompt(self):
        os.environ["UNIT_LLAMA_MODEL"] = "HY-MT1.5-1.8B-Q4_K_M.gguf"
        os.environ["UNIT_LLAMA_BASE_URL"] = "http://127.0.0.1:1/v1"
        provider = OpenAICompatiblePolisherProvider(
            provider_id="llama_app",
            display_name="Local",
            env_prefix="UNIT_LLAMA",
            default_base_url="http://127.0.0.1:1/v1",
        )
        prompts = []

        def create(**kwargs):
            prompt = kwargs["messages"][0]["content"]
            prompts.append(prompt)
            answer = "Hóa ra hắn vẫn luôn lừa ta." if "原来" in prompt else "Sư huynh, cẩn thận Ma tộc."
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=answer))])

        provider._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        translated, warnings, used = provider.polish_batch(
            source_texts=[
                '<CUE id="1">原来他一直在骗我</CUE>',
                '<CUE id="2">师兄，小心魔族</CUE>',
            ],
            src_lang="zh-Hans",
            target_lang="vi",
            max_retries=1,
            context_before=["开场白"],
            context_after=["然后离开"],
        )

        self.assertEqual(used, "llama_app")
        self.assertEqual(warnings, [])
        self.assertEqual(len(translated), 2)
        self.assertTrue(all("Translate the following segment into Vietnamese" in value for value in prompts))
        self.assertTrue(all("<CUE" not in value for value in prompts))
        self.assertTrue(any("师兄=sư huynh" in value for value in prompts))
        first = next(value for value in prompts if value.endswith("：原来他一直在骗我"))
        second = next(value for value in prompts if "：师兄，小心魔族" in value)
        self.assertIn("Previous source (context only, do not translate): 开场白", first)
        self.assertIn("Upcoming source (context only, do not translate): 师兄，小心魔族", first)
        self.assertIn("Previous source (context only, do not translate): 原来他一直在骗我", second)
        self.assertIn("Upcoming source (context only, do not translate): 然后离开", second)

    def test_qwen_local_translation_disables_thinking_for_structured_subtitles(self):
        os.environ["UNIT_QWEN_MODEL"] = "Qwen3-4B-Q4_K_M.gguf"
        os.environ["UNIT_QWEN_BASE_URL"] = "http://127.0.0.1:1/v1"
        provider = OpenAICompatiblePolisherProvider(
            provider_id="llama_app",
            display_name="Local",
            env_prefix="UNIT_QWEN",
            default_base_url="http://127.0.0.1:1/v1",
        )
        captured = {}

        def create(**kwargs):
            captured.update(kwargs)
            answer = "1. Đạo hữu vừa liên tiếp giao chiến với hai vị Thiên Vương."
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=answer))])

        provider._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        translated, warnings, used = provider.polish_batch(
            source_texts=['<CUE id="1">道友刚才连战两位天王</CUE>'],
            src_lang="zh-Hans",
            target_lang="vi",
            max_retries=1,
        )

        self.assertEqual(translated, ["Đạo hữu vừa liên tiếp giao chiến với hai vị Thiên Vương."])
        self.assertEqual(warnings, [])
        self.assertEqual(used, "llama_app")
        self.assertEqual(
            captured["extra_body"],
            {"chat_template_kwargs": {"enable_thinking": False}},
        )

    def test_local_refinement_strips_echoed_cue_and_draft_scaffolding(self):
        os.environ["UNIT_CLEAN_MODEL"] = "Qwen3-4B-Q4_K_M.gguf"
        os.environ["UNIT_CLEAN_BASE_URL"] = "http://127.0.0.1:1/v1"
        provider = OpenAICompatiblePolisherProvider(
            provider_id="llama_app",
            display_name="Local",
            env_prefix="UNIT_CLEAN",
            default_base_url="http://127.0.0.1:1/v1",
        )

        def create(**_kwargs):
            answer = (
                '1. <CUE id="1">Đạo hữu vừa giao chiến</CUE> ||| '
                "Đạo hữu vừa liên tiếp giao chiến với hai vị Thiên Vương."
            )
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=answer))])

        provider._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        translated, _warnings, _used = provider.polish_batch(
            source_texts=['<CUE id="1">道友刚才连战两位天王</CUE>'],
            translated_texts=["Đạo hữu vừa giao chiến"],
            src_lang="zh-Hans",
            target_lang="vi",
            max_retries=1,
        )
        self.assertEqual(
            translated,
            ["Đạo hữu vừa liên tiếp giao chiến với hai vị Thiên Vương."],
        )

    def test_local_provider_requests_use_extended_timeout(self):
        os.environ["UNIT_TO_MODEL"] = "Qwen3-4B-Q4_K_M.gguf"
        os.environ["UNIT_TO_BASE_URL"] = "http://127.0.0.1:1/v1"
        local = OpenAICompatiblePolisherProvider(
            provider_id="llama_app",
            display_name="Local",
            env_prefix="UNIT_TO",
            default_base_url="http://127.0.0.1:1/v1",
        )
        cloud = OpenAICompatiblePolisherProvider(
            provider_id="google_ai_studio",
            display_name="Cloud",
            env_prefix="UNIT_TO",
            default_base_url="http://127.0.0.1:1/v1",
        )
        self.assertGreaterEqual(local._effective_timeout("llama_app", 120), 900)
        self.assertGreaterEqual(local._effective_timeout("ollama", 0), 900)
        self.assertEqual(cloud._effective_timeout("google_ai_studio", 120), 120)

        captured = {}

        def create(**kwargs):
            captured.update(kwargs)
            answer = "1. Sư huynh, cẩn thận Ma tộc!"
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=answer))])

        local._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        local.polish_batch(
            source_texts=['<CUE id="1">师兄小心魔族</CUE>'],
            src_lang="zh-Hans",
            target_lang="vi",
            timeout=120,
            max_retries=1,
        )
        self.assertGreaterEqual(captured["timeout"], 900)

    def test_zero_max_retries_still_performs_one_attempt(self):
        os.environ["UNIT_ZERO_MODEL"] = "Qwen3-4B-Q4_K_M.gguf"
        os.environ["UNIT_ZERO_BASE_URL"] = "http://127.0.0.1:1/v1"
        provider = OpenAICompatiblePolisherProvider(
            provider_id="llama_app",
            display_name="Local",
            env_prefix="UNIT_ZERO",
            default_base_url="http://127.0.0.1:1/v1",
        )
        calls = []

        def create(**kwargs):
            calls.append(kwargs)
            answer = "1. Sư huynh, cẩn thận Ma tộc!"
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=answer))])

        provider._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        translated, _warnings, _used = provider.polish_batch(
            source_texts=['<CUE id="1">师兄小心魔族</CUE>'],
            src_lang="zh-Hans",
            target_lang="vi",
            max_retries=0,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(translated), 1)


if __name__ == "__main__":
    unittest.main()

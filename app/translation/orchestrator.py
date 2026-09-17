import concurrent.futures
import math
import os
import re

from .errors import TranslationValidationError
from .models import TranslationResult
from .prompt_loader import render_prompt
from .providers import (
    GoogleWebTranslatorProvider,
    OpenAICompatiblePolisherProvider,
)
from .quality_guard import apply_translation_quality_guard
from .srt_utils import clone_with_texts, parse_srt, split_text_batches, to_srt, validate_texts


class AIBatchTranslationError(Exception):
    """The full-context recovery batches could not be completed."""


class TranslationOrchestrator:
    def __init__(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        env_path = os.path.join(base_dir, ".env")
        if os.path.exists(env_path):
            try:
                from dotenv import load_dotenv
                load_dotenv(env_path)
            except Exception:
                pass
        self.google_web = GoogleWebTranslatorProvider()

    @staticmethod
    def _segment_source_text(segment: dict | None) -> str:
        if not isinstance(segment, dict):
            return ""
        return str(
            segment.get("original_text")
            or segment.get("source_text")
            or segment.get("text")
            or ""
        ).strip()

    @staticmethod
    def _segment_translated_text(segment: dict | None) -> str:
        if not isinstance(segment, dict):
            return ""
        return str(
            segment.get("final_text")
            or segment.get("refined_translation")
            or segment.get("raw_translation")
            or segment.get("translated_text")
            or segment.get("text")
            or ""
        ).strip()

    @staticmethod
    def _segment_speaker(segment: dict | None) -> str:
        speaker = str((segment or {}).get("speaker") or "").strip()
        if speaker:
            return speaker
        metadata = (segment or {}).get("metadata") or {}
        if isinstance(metadata, dict):
            return str(metadata.get("speaker") or "").strip()
        return ""

    @staticmethod
    def _xml_attr(value: str) -> str:
        return (
            str(value or "")
            .replace("&", "&amp;")
            .replace('"', "&quot;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    @classmethod
    def _build_timed_ai_source(cls, segment: dict, index: int) -> str:
        """Attach non-translatable cue timing so AI can control readability."""
        try:
            start = max(0.0, float((segment or {}).get("start", 0.0) or 0.0))
            end = max(start, float((segment or {}).get("end", start) or start))
        except (TypeError, ValueError):
            start, end = 0.0, 0.0
        duration = max(0.1, end - start)
        text = " ".join(
            cls._segment_source_text(segment).replace("</CUE>", "").split()
        ).strip()
        speaker = cls._segment_speaker(segment)
        speaker_attr = f' speaker="{cls._xml_attr(speaker)}"' if speaker else ""
        return (
            f'<CUE id="{index + 1}" start="{start:.3f}" end="{end:.3f}" '
            f'duration="{duration:.3f}"{speaker_attr}>{text}</CUE>'
        )

    def translate_segments(
        self,
        *,
        segments: list[dict],
        src_lang: str = "zh-Hans",
        target_lang: str = "vi",
        enable_polish: bool = True,
        optimize_subtitles: bool = False,
        ms_batch_size: int = 50,
        polish_batch_size: int = 80,
        style_instruction: str = "",
        batch_callback=None,
        on_progress: callable = None,
        cancellation_check: callable = None,
    ) -> TranslationResult:
        if not segments:
            return TranslationResult(success=False, errors=["No segments to translate."], stage="input")

        if cancellation_check and cancellation_check():
            raise InterruptedError("Translation cancelled by user")

        source_texts = [self._segment_source_text(s) for s in segments]
        ai_source_texts = [self._build_timed_ai_source(seg, index) for index, seg in enumerate(segments)]
        normalized_src = self._normalize_source_language(src_lang)
        warnings = []

        if enable_polish:
            provider_type, polisher = self._resolve_ai_provider()
            if polisher.is_configured():
                try:
                    # Quality passes (review/repair) may use a separate model
                    # chosen by the user; the main model does the bulk
                    # translation above.
                    _, review_polisher = self._resolve_ai_provider(role="quality")
                    if not review_polisher.is_configured():
                        review_polisher = polisher
                    mode_label = self._describe_ai_provider(provider_type, polisher)
                    merged_style = str(style_instruction or "")
                    print(
                        f"[AI Translation] Starting translation (provider: {mode_label}, batch_size={polish_batch_size})..."
                    )
                    translated_texts, providers_used, batch_warnings = self._run_ai_batches(
                        polisher=polisher,
                        provider_type=provider_type,
                        source_texts=ai_source_texts,
                        translated_texts=None,
                        src_lang=normalized_src,
                        target_lang=target_lang,
                        style_instruction=merged_style,
                        polish_batch_size=polish_batch_size,
                        on_progress=on_progress,
                        cancellation_check=cancellation_check,
                    )
                    warnings.extend(batch_warnings)

                    if not validate_texts(translated_texts, len(segments)):
                        raise TranslationValidationError("AI translator returned an invalid number of segments.")

                    translated_texts, quality_warnings = apply_translation_quality_guard(
                        source_segments=segments,
                        translated_texts=translated_texts,
                        target_lang=target_lang,
                    )
                    translated_texts, review_warnings = self._review_local_translation_with_context(
                        polisher=review_polisher,
                        provider_type=provider_type,
                        source_segments=segments,
                        ai_source_texts=ai_source_texts,
                        translated_texts=translated_texts,
                        src_lang=normalized_src,
                        target_lang=target_lang,
                        style_instruction=merged_style,
                    )
                    warnings.extend(review_warnings)
                    translated_texts, quality_warnings = apply_translation_quality_guard(
                        source_segments=segments,
                        translated_texts=translated_texts,
                        target_lang=target_lang,
                    )
                    translated_texts, quality_warnings = self._repair_ai_quality_issues(
                        polisher=review_polisher,
                        source_segments=segments,
                        ai_source_texts=ai_source_texts,
                        translated_texts=translated_texts,
                        quality_warnings=quality_warnings,
                        src_lang=normalized_src,
                        target_lang=target_lang,
                        style_instruction=merged_style,
                    )
                    if provider_type != "llama_app":
                        translated_texts, quality_warnings = self._fallback_unresolved_quality_issues(
                            source_segments=segments,
                            translated_texts=translated_texts,
                            quality_warnings=quality_warnings,
                            src_lang=normalized_src,
                            target_lang=target_lang,
                        )
                    warnings.extend(quality_warnings)
                    print(f"[AI Translation] Success: completed via {', '.join(providers_used) or 'AI'}")
                    final_segments = clone_with_texts(segments, translated_texts, provider=provider_type, polished=True)
                    if on_progress:
                        try:
                            from app.core.models.progress import ProgressEvent
                            on_progress(ProgressEvent(
                                workflow="translate",
                                stage="translation",
                                substage="complete",
                                current=100.0,
                                total=100.0,
                                percent=100,
                                message="Translation completed successfully",
                            ))
                        except Exception:
                            on_progress("Translation completed successfully")
                    return TranslationResult(
                        success=True,
                        segments=final_segments,
                        warnings=warnings,
                        stage="ai_direct",
                        primary_provider=" -> ".join(providers_used) or provider_type,
                        # Readability/quality warnings are not provider
                        # fallback. Mark this only on the real Google path.
                        used_fallback=False,
                    )
                except Exception as exc:
                    if provider_type != "google":
                        # Respect the provider the user explicitly selected.
                        # Silent fallback changes both privacy expectations and
                        # translation quality; in practice a Gemini quota error
                        # used to replace the contextual translation with a much
                        # weaker Google Web result while Generate still looked
                        # successful. Surface the real provider error instead.
                        raise
                    if isinstance(exc, AIBatchTranslationError):
                        msg = "AI batch translation failed. Falling back to Google Translate."
                    else:
                        msg = "AI Provider is unavailable. Falling back to Google Translate..."
                    print(f"[AI Translation] WARNING: {msg} ({exc})")
                    warnings.append(msg)
            else:
                selected_provider = str(os.getenv("OPENAI_PROVIDER") or "google").strip().lower()
                if selected_provider != "google":
                    reason = str(getattr(polisher, "config_error", "") or "").strip()
                    msg = "AI Provider is unavailable. Falling back to Google Translate..."
                    if reason:
                        msg = f"{msg} ({reason})"
                    print(f"[AI Translation] WARNING: {msg}")
                    warnings.append(msg)
                else:
                    print("[AI Translation] Google Translate selected.")

        print(f"[Translation] Starting Google web translate fallback (batch_size={ms_batch_size})...")
        try:
            translated_texts = []
            offset = 0
            all_batches = list(split_text_batches(source_texts, ms_batch_size))
            total_b = max(1, len(all_batches))
            for b_idx, batch in enumerate(all_batches):
                if cancellation_check and cancellation_check():
                    raise InterruptedError("Translation cancelled by user")
                if on_progress:
                    pct = int(b_idx * 100 / total_b)
                    msg = f"Translating batch {b_idx + 1}/{total_b} (Google Web)..."
                    try:
                        from app.core.models.progress import ProgressEvent
                        on_progress(ProgressEvent(
                            workflow="translate",
                            stage="translation",
                            substage="batch",
                            current=float(b_idx + 1),
                            total=float(total_b),
                            percent=pct,
                            message=msg,
                        ))
                    except Exception:
                        on_progress(msg)
                translated_batch = self.google_web.translate_batch(
                    batch,
                    src_lang=normalized_src,
                    target_lang=target_lang,
                )
                translated_texts.extend(translated_batch)
                self._emit_batch_callback(
                    batch_callback=batch_callback,
                    base_segments=segments,
                    start_idx=offset,
                    translated_texts=translated_batch,
                    provider="google-web",
                    polished=False,
                )
                offset += len(batch)

            if not validate_texts(translated_texts, len(segments)):
                raise TranslationValidationError("Google web translate returned an invalid number of segments.")

            translated_texts, quality_warnings = apply_translation_quality_guard(
                source_segments=segments,
                translated_texts=translated_texts,
                target_lang=target_lang,
            )
            warnings.extend(quality_warnings)
            print("[Translation] Success: Google web translate completed.")
            final_segments = clone_with_texts(segments, translated_texts, provider="google-web", polished=False)
            if on_progress:
                try:
                    from app.core.models.progress import ProgressEvent
                    on_progress(ProgressEvent(
                        workflow="translate",
                        stage="translation",
                        substage="complete",
                        current=100.0,
                        total=100.0,
                        percent=100,
                        message="Translation completed successfully",
                    ))
                except Exception:
                    on_progress("Translation completed successfully")
            return TranslationResult(
                success=True,
                segments=final_segments,
                warnings=warnings,
                stage="translation",
                primary_provider="google-web",
                used_fallback=bool(warnings),
            )
        except Exception as exc:
            return TranslationResult(success=False, errors=[str(exc)], warnings=warnings, stage="translation")

    def rewrite_segments(
        self,
        source_segments: list[dict],
        translated_segments: list[dict],
        *,
        src_lang: str = "zh-Hans",
        target_lang: str = "vi",
        style_instruction: str = "",
    ) -> TranslationResult:
        if not source_segments:
            return TranslationResult(success=False, errors=["No source segments to rewrite."], stage="rewrite")
        if not translated_segments:
            return TranslationResult(success=False, errors=["No translated segments to rewrite."], stage="rewrite")
        if len(source_segments) != len(translated_segments):
            return TranslationResult(
                success=False,
                errors=["Source and translated subtitle counts do not match."],
                stage="rewrite",
            )

        provider_type, polisher = self._resolve_ai_provider()
        if not polisher.is_configured():
            reason = str(getattr(polisher, "config_error", "") or "").strip()
            message = f"AI provider '{provider_type}' is not configured."
            if reason:
                message = f"{message} {reason}"
            return TranslationResult(
                success=False,
                errors=[message],
                stage="rewrite",
            )

        source_texts = [self._segment_source_text(s) for s in source_segments]
        translated_texts = [self._segment_translated_text(s) for s in translated_segments]
        normalized_src = self._normalize_source_language(src_lang)

        try:
            # Rewriting is a sentence-polish role: prefer the dedicated
            # quality model when one is configured.
            _, quality_polisher = self._resolve_ai_provider(role="quality")
            if quality_polisher.is_configured():
                polisher = quality_polisher
            rewritten_texts, providers_used, warnings = self._run_ai_batches(
                polisher=polisher,
                provider_type=provider_type,
                source_texts=source_texts,
                translated_texts=translated_texts,
                src_lang=normalized_src,
                target_lang=target_lang,
                style_instruction=style_instruction,
                polish_batch_size=len(source_texts),
            )
            if not validate_texts(rewritten_texts, len(source_segments)):
                raise TranslationValidationError("AI rewrite returned an invalid number of segments.")

            final_segments = []
            for source_seg, rewritten_text in zip(source_segments, rewritten_texts):
                final_segments.append(
                    {
                        "start": source_seg["start"],
                        "end": source_seg["end"],
                        "text": (rewritten_text or "").strip(),
                        "source_text": source_seg.get("source_text") or source_seg.get("text", ""),
                        "provider": provider_type,
                        "polished": True,
                    }
                )
            return TranslationResult(
                success=True,
                segments=final_segments,
                warnings=warnings,
                stage="rewrite",
                primary_provider=" -> ".join(providers_used) or provider_type,
                used_fallback=bool(warnings),
            )
        except Exception as exc:
            return TranslationResult(success=False, errors=[str(exc)], stage="rewrite")

    def translate_srt(self, srt_content: str, **kwargs) -> TranslationResult:
        segments = parse_srt(srt_content)
        return self.translate_segments(segments=segments, **kwargs)

    def result_to_srt(self, result: TranslationResult) -> str:
        return to_srt(result.segments)

    def _normalize_source_language(self, src_lang: str) -> str:
        mapping = {
            "auto": "zh-Hans",
            "zh": "zh-Hans",
            "zh-cn": "zh-Hans",
            "zh-hans": "zh-Hans",
            "ja": "ja",
            "ko": "ko",
            "en": "en",
            "vi": "vi",
        }
        key = (src_lang or "zh").strip().lower()
        return mapping.get(key, src_lang)

    def _resolve_ai_provider(self, role: str = "translate"):
        # All selectable API providers use the same compatible client.
        configured_provider = (os.getenv("OPENAI_PROVIDER") or os.getenv("AI_POLISHER_PROVIDER") or "google_ai_studio").strip().lower()
        provider_type = configured_provider
        if provider_type in {"gemini", "google"}:  # backward compatibility
            provider_type = "google_ai_studio"
        definitions = {
            "google_ai_studio": ("Google AI Studio (Gemini)", "GOOGLE_AI_STUDIO", "https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-3.6-flash"),
            "deepseek": ("DeepSeek AI", "DEEPSEEK", "https://api.deepseek.com/v1", "deepseek-chat"),
            "openai": ("OpenAI", "OPENAI", "https://api.openai.com/v1/", "gpt-4o-mini"),
            "ollama": ("Ollama (Local)", "OLLAMA", "http://localhost:11434/v1", "qwen2.5:7b"),
            "custom": ("Custom OpenAI API", "CUSTOM_AI", "https://api.openai.com/v1/", "gpt-4o-mini"),
            "llama_app": ("Llama.cpp (Local App Engine)", "LLAMA_APP", "http://127.0.0.1:49683/v1", "local_model"),
        }
        if provider_type not in definitions:
            provider_type = "google_ai_studio"
        
        display_name, env_prefix, base_url, default_model = definitions[provider_type]
        config_error = ""
        
        if provider_type == "llama_app":
            from app.services.llama_local_manager import LlamaServerManager
            manager = LlamaServerManager.get_instance()
            model_path = os.getenv("LLAMA_APP_MODEL")
            if not os.path.isfile(manager.exe_path):
                config_error = f"llama-server.exe was not found at {manager.exe_path}"
            elif not model_path or not os.path.exists(model_path):
                config_error = "No local GGUF model is selected. Select or download a model in the Llama.cpp panel."
            else:
                try:
                    manager.start_server(model_path)
                    base_url = manager.get_base_url()
                    default_model = os.path.basename(model_path)
                except Exception as exc:
                    config_error = f"llama.cpp engine failed to start: {exc}"
            if config_error:
                # Fail soft: leave the provider unconfigured so every caller
                # falls back to Google Translate instead of raising a raw
                # FileNotFoundError/RuntimeError in worker processes when the
                # engine or model is missing (e.g. packaged app builds that
                # do not ship bin/llama_cpp).
                default_model = ""
                print(f"[AI Translation] WARNING: {config_error}")

        # Legacy fallback if user has OPENAI_API_KEY set for gemini
        if configured_provider == "gemini" and not os.getenv("GOOGLE_AI_STUDIO_API_KEY"):
            env_prefix = "OPENAI"
        # "quality" role: the same endpoint but a different model (per-provider
        # {PREFIX}_POLISH_MODEL env) used for fix/review passes. Without an
        # explicit quality model it falls back to the main model.
        model_env_key = f"{env_prefix}_MODEL"
        if role == "quality":
            model_env_key = f"{env_prefix}_POLISH_MODEL"
            if not os.getenv(model_env_key, "").strip():
                review_defaults = {"google_ai_studio": "gemini-3.6-flash"}
                default_model = review_defaults.get(provider_type) or default_model
        polisher = OpenAICompatiblePolisherProvider(
            provider_id=provider_type,
            display_name=display_name,
            env_prefix=env_prefix,
            default_base_url=base_url,
            default_model=default_model,
            model_env=model_env_key,
        )
        if (
            provider_type == "google_ai_studio"
            and str(polisher.model_name or "").strip().lower().removeprefix("models/") == "gemini-2.5-pro"
        ):
            # Google no longer grants this model to new API users. Keep stale
            # .env/OS settings from failing Movie Review with a 404.
            polisher.model_name = "gemini-3.6-flash"
        polisher.config_error = config_error
        return provider_type, polisher

    def _describe_ai_provider(self, provider_type: str, polisher=None) -> str:
        names = {
            "google_ai_studio": "Google Gemini",
            "deepseek": "DeepSeek AI",
            "openai": "OpenAI",
            "ollama": "Ollama",
            "custom": "Custom AI",
            "llama_app": "Llama App Engine",
        }
        if polisher is None:
            polisher = self._resolve_ai_provider()[1]
        return f"{names.get(provider_type, 'AI')} ({getattr(polisher, 'model_name', '')})"

    def _run_ai_batches(
        self,
        *,
        polisher,
        provider_type: str,
        source_texts: list[str],
        translated_texts: list[str] | None,
        src_lang: str,
        target_lang: str,
        style_instruction: str,
        polish_batch_size: int,
        on_progress: callable = None,
        cancellation_check: callable = None,
    ) -> tuple[list[str], list[str], list[str]]:
        # Modern cloud models benefit from enough neighbouring subtitle cues
        # to keep terminology, names, and tone consistent.  Do not rely only
        # on a cue count though: long subtitle files can still exceed a
        # provider's practical context/output budget.  The same boundaries
        # are used for source and draft text, preventing misaligned rewrites.
        #
        # Local CPU models are much slower than cloud APIs (llama.cpp on a
        # typical machine generates ~10 tokens/s). A 24-cue batch routinely
        # needs more than the generic 120s request timeout and then fails the
        # whole translation pass, so local batches are kept deliberately
        # small. VIUSTUDIO_AI_TRANSLATION_LOCAL_MAX_SEGMENTS is an escape
        # hatch for fast GPUs.
        local_provider = provider_type in {"llama_app", "ollama"}
        try:
            local_max_segments = max(4, min(24, int(os.getenv("VIUSTUDIO_AI_TRANSLATION_LOCAL_MAX_SEGMENTS", "12"))))
        except ValueError:
            local_max_segments = 12
        try:
            cloud_max_segments = max(8, min(40, int(os.getenv("VIUSTUDIO_AI_TRANSLATION_CLOUD_MAX_SEGMENTS", "24"))))
        except ValueError:
            cloud_max_segments = 24
        scene_max_segments = local_max_segments if local_provider else cloud_max_segments
        batches, full_context_request = self._build_ai_batches(
            source_texts=source_texts,
            translated_texts=translated_texts,
            requested_max_segments=min(polish_batch_size, scene_max_segments),
            # Scene-sized ordered batches keep pronouns, names, and addressee
            # consistent. A single huge request makes Flash/local models
            # translate each numbered line in isolation.
            force_ordered=True,
            max_chars_limit=6000 if local_provider else None,
            response_token_limit=1800 if local_provider else None,
        )
        if not full_context_request:
            print(
                "[AI Translation] Batching: "
                f"segments={len(source_texts)}, requests={len(batches)}, "
                f"max_segments={max((len(source) for source, _draft, _tokens in batches), default=0)}"
            )
        try:
            return self._run_ai_batch_requests(
                polisher=polisher,
                batches=batches,
                src_lang=src_lang,
                target_lang=target_lang,
                style_instruction=style_instruction,
                max_workers=1,
                on_progress=on_progress,
                cancellation_check=cancellation_check,
            )
        except TranslationValidationError as exc:
            if not full_context_request:
                raise
            print("[AI Translation] Full-context response incomplete. Retrying with ordered batches.")
            fallback_batches, _unused_full_context = self._build_ai_batches(
                source_texts=source_texts,
                translated_texts=translated_texts,
                requested_max_segments=polish_batch_size,
                force_ordered=True,
            )
            print(
                "[AI Translation] Ordered batch retry: "
                f"requests={len(fallback_batches)}, "
                f"max_segments={max((len(source) for source, _draft, _tokens in fallback_batches), default=0)}"
            )
            try:
                recovered = self._run_ai_batch_requests(
                    polisher=polisher,
                    batches=fallback_batches,
                    src_lang=src_lang,
                    target_lang=target_lang,
                    style_instruction=style_instruction,
                    max_workers=1,
                    on_progress=on_progress,
                    cancellation_check=cancellation_check,
                )
                print("[AI Translation] Batch translation completed successfully.")
                return recovered
            except Exception as batch_exc:
                print(f"[AI Translation] AI batch translation failed. Falling back to Google Translate. ({batch_exc})")
                raise AIBatchTranslationError(str(batch_exc)) from exc
        except Exception as exc:
            # A slow local model that overran the request timeout would
            # otherwise fail the entire translation pass. Retry once with
            # half-size ordered batches before surfacing the provider error.
            if not local_provider or full_context_request:
                raise
            shrink_segments = max(4, local_max_segments // 2)
            print(
                "[AI Translation] Local provider failure "
                f"({type(exc).__name__}: {exc}). Retrying with smaller batches "
                f"(max {shrink_segments} cues)..."
            )
            shrink_batches, _unused_full_context = self._build_ai_batches(
                source_texts=source_texts,
                translated_texts=translated_texts,
                requested_max_segments=shrink_segments,
                force_ordered=True,
                max_chars_limit=6000 if local_provider else None,
                response_token_limit=1800 if local_provider else None,
            )
            try:
                recovered = self._run_ai_batch_requests(
                    polisher=polisher,
                    batches=shrink_batches,
                    src_lang=src_lang,
                    target_lang=target_lang,
                    style_instruction=style_instruction,
                    max_workers=1,
                    on_progress=on_progress,
                    cancellation_check=cancellation_check,
                )
                print("[AI Translation] Smaller-batch retry completed successfully.")
                return recovered
            except Exception as shrink_exc:
                raise AIBatchTranslationError(str(shrink_exc)) from exc

    def _repair_ai_quality_issues(
        self,
        *,
        polisher,
        source_segments,
        ai_source_texts,
        translated_texts,
        quality_warnings,
        src_lang,
        target_lang,
        style_instruction,
    ):
        """Retry only objectively broken cues, with a 2-cue context window."""
        severe_indices = set()
        for warning in quality_warnings:
            if not any(
                marker in warning
                for marker in (
                    "chữ viết nguồn",
                    "thiếu số",
                    "bản dịch trống",
                    "cụm tiếng Anh trong bản dịch tiếng Việt",
                    "semantic mismatch",
                )
            ):
                continue
            match = re.match(r"Cue\s+(\d+):", str(warning))
            if match:
                severe_indices.add(int(match.group(1)) - 1)
        if not severe_indices:
            return list(translated_texts), list(quality_warnings)

        repaired = list(translated_texts)
        valid_indices = [
            index for index in sorted(severe_indices)
            if 0 <= index < len(repaired)
        ]
        if not valid_indices:
            return list(translated_texts), list(quality_warnings)

        def repair_one(index):
            context_start = max(0, index - 2)
            context_end = min(len(ai_source_texts), index + 3)
            nearby_before = [
                ai_source_texts[pos]
                for pos in range(context_start, index)
            ]
            nearby_after = [
                ai_source_texts[pos]
                for pos in range(index + 1, context_end)
            ]
            repair_instruction = (
                f"{style_instruction}\n\n[mode=translation_quality_repair] "
                "Repair only the current numbered cue. Its previous draft failed an objective "
                "check because it retained text in the wrong language, lost a source number, or "
                "was empty. Output only the requested target language. Preserve "
                "the exact source meaning, names, numbers, negation and speaker register. Use the "
                "nearby source only for context; never output nearby cues.\n"
                "The following automatic checks describe the exact defect; satisfy them rather than merely "
                "rephrasing the draft:\n"
                + "\n".join(
                    f"- {warning}" for warning in quality_warnings
                    if re.match(rf"Cue\s+{index + 1}:", str(warning))
                )
            )
            try:
                result, _warnings, _provider = polisher.polish_batch(
                    source_texts=[ai_source_texts[index]],
                    translated_texts=[repaired[index]],
                    src_lang=src_lang,
                    target_lang=target_lang,
                    style_instruction=repair_instruction,
                    context_before=nearby_before,
                    context_after=nearby_after,
                    max_tokens=1024,
                )
                if result and str(result[0]).strip():
                    repaired[index] = str(result[0]).strip()
            except Exception as exc:
                print(f"[Translation QA] Cue {index + 1} repair skipped: {exc}")

        # Local models are request-free for the user, so keep one request per
        # cue there. API providers (Gemini/OpenAI/...) pay per request, so
        # group flagged cues into a single numbered repair request per 8 cues
        # instead of burning one request per cue; any failed group falls back
        # to the old cue-by-cue path.
        if getattr(polisher, "provider_id", "") in {"llama_app", "ollama"}:
            for index in valid_indices:
                repair_one(index)
        else:
            group_size = 8
            for group_start in range(0, len(valid_indices), group_size):
                group = valid_indices[group_start:group_start + group_size]
                first, last = group[0], group[-1]
                context_before = [
                    ai_source_texts[pos] for pos in range(max(0, first - 2), first)
                ]
                context_after = [
                    ai_source_texts[pos]
                    for pos in range(last + 1, min(len(ai_source_texts), last + 3))
                ]
                entries = []
                for batch_number, index in enumerate(group, start=1):
                    defects = "; ".join(
                        str(warning) for warning in quality_warnings
                        if re.match(rf"Cue\s+{index + 1}:", str(warning))
                    )
                    entries.append(
                        f"{batch_number}. source: {ai_source_texts[index]}\n"
                        f"   draft: {repaired[index]}\n"
                        f"   defects: {defects}"
                    )
                group_instruction = (
                    f"{style_instruction}\n\n[mode=translation_quality_repair] "
                    "Repair ONLY the numbered cues listed below; each shows its source, current "
                    "draft and the exact automatic defects. Output exactly N. lines numbered 1..k, "
                    "one repaired target-language line per cue, in the same order. Preserve the exact "
                    "source meaning, names, numbers, negation and speaker register. Use the nearby "
                    "source only for context; never output nearby cues. Satisfy the listed checks "
                    "rather than merely rephrasing the draft.\n\n"
                    + "\n\n".join(entries)
                )
                print(
                    "[Translation QA] Repairing "
                    f"{len(group)} of {len(valid_indices)} flagged cue(s) in one request."
                )
                try:
                    results, _warnings, _provider = polisher.polish_batch(
                        source_texts=[ai_source_texts[index] for index in group],
                        translated_texts=[repaired[index] for index in group],
                        src_lang=src_lang,
                        target_lang=target_lang,
                        style_instruction=group_instruction,
                        context_before=context_before,
                        context_after=context_after,
                        max_tokens=max(2048, 600 * len(group)),
                    )
                    if len(results) == len(group):
                        for batch_number, index in enumerate(group):
                            if str(results[batch_number] or "").strip():
                                repaired[index] = str(results[batch_number]).strip()
                        continue
                except Exception as exc:
                    print(f"[Translation QA] Group repair failed ({exc}); retrying cue-by-cue.")
                for index in group:
                    repair_one(index)

        repaired, final_warnings = apply_translation_quality_guard(
            source_segments=list(source_segments),
            translated_texts=repaired,
            target_lang=target_lang,
        )
        return repaired, final_warnings

    def _fallback_unresolved_quality_issues(
        self,
        *,
        source_segments,
        translated_texts,
        quality_warnings,
        src_lang,
        target_lang,
    ):
        """Re-translate only cues that remain objectively invalid after AI repair."""
        retry_indices: set[int] = set()
        severe_markers = (
            "chữ viết nguồn",
            "thiếu số",
            "bản dịch trống",
            "cụm tiếng Anh trong bản dịch tiếng Việt",
        )
        for warning in quality_warnings or []:
            if not any(marker in str(warning) for marker in severe_markers):
                continue
            match = re.match(r"Cue\s+(\d+):", str(warning))
            if match:
                retry_indices.add(int(match.group(1)) - 1)
        valid_indices = [
            index for index in sorted(retry_indices)
            if 0 <= index < len(source_segments) and index < len(translated_texts)
        ]
        if not valid_indices:
            return list(translated_texts), list(quality_warnings)

        repaired = list(translated_texts)
        try:
            fallback = self.google_web.translate_batch(
                [self._segment_source_text(source_segments[index]) for index in valid_indices],
                src_lang=src_lang,
                target_lang=target_lang,
            )
            if validate_texts(fallback, len(valid_indices)):
                for index, value in zip(valid_indices, fallback):
                    if str(value or "").strip():
                        repaired[index] = str(value).strip()
                print(
                    "[Translation QA] Re-translated "
                    f"{len(valid_indices)} unresolved cue(s) with the fallback engine."
                )
        except Exception as exc:
            print(f"[Translation QA] Final fallback unavailable: {exc}")

        return apply_translation_quality_guard(
            source_segments=list(source_segments),
            translated_texts=repaired,
            target_lang=target_lang,
        )

    @staticmethod
    def _is_dedicated_sentence_mt(polisher) -> bool:
        """Return True for local models that cannot follow review instructions."""
        model_name = os.path.basename(str(getattr(polisher, "model_name", "") or ""))
        return bool(re.match(r"(?i)^hy[-_]?mt", model_name))

    def _review_local_translation_with_context(
        self,
        *,
        polisher,
        provider_type: str,
        source_segments: list[dict],
        ai_source_texts: list[str],
        translated_texts: list[str],
        src_lang: str,
        target_lang: str,
        style_instruction: str,
    ) -> tuple[list[str], list[str]]:
        """Audit local-chat-model drafts against source in ordered scene batches.

        A grammatical target-language line can still reverse the speaker and
        listener, translate an idiom literally, or hallucinate a name. Surface
        checks cannot detect those errors. General local chat models therefore
        get one source-versus-draft review pass with neighbouring cues. Dedicated
        sentence MT models are excluded because their native prompt does not
        support scene context or draft refinement.
        """
        if provider_type not in {"llama_app", "ollama"}:
            return list(translated_texts), []
        if self._is_dedicated_sentence_mt(polisher):
            return list(translated_texts), [
                "Contextual semantic review skipped: the selected dedicated MT model only supports isolated cues."
            ]
        enabled = str(os.getenv("VIUSTUDIO_LOCAL_TRANSLATION_REVIEW", "1")).strip().lower()
        if enabled in {"0", "false", "no", "off"}:
            return list(translated_texts), []

        review_instruction = (
            f"{style_instruction}\n\n[mode=semantic_translation_review] "
            "Audit every draft against its own source before returning the complete numbered batch. "
            "Correct meaning errors even when the draft is fluent. Check grammatical subject and object, "
            "speaker versus addressee, negation, time/aspect, names, titles, fixed idioms and recurring terms. "
            "A vocative such as Chinese 道友 addresses the listener; it does not make a following action "
            "first-person. Translate idioms by their intended meaning: 五体投地 expresses utmost admiration, "
            "not a literal fall. In constructions such as 我 + character name + predicate, keep the name as "
            "the speaker identity and do not merge it into the verb. Use nearby cues only to disambiguate. "
            "Never add a person, name, pronoun, action or fact unsupported by the current source. Keep an "
            "already-correct draft unchanged. Output every requested cue exactly once."
        )
        try:
            reviewed, providers, batch_warnings = self._run_ai_batches(
                polisher=polisher,
                provider_type=provider_type,
                source_texts=ai_source_texts,
                translated_texts=list(translated_texts),
                src_lang=src_lang,
                target_lang=target_lang,
                style_instruction=review_instruction,
                # Smaller review scenes reduce attention drift on 4B-class
                # local models while retaining enough dialogue context.
                polish_batch_size=16,
            )
            if not validate_texts(reviewed, len(source_segments)):
                raise TranslationValidationError("semantic review returned an invalid cue count")
            guarded, _review_quality_warnings = apply_translation_quality_guard(
                source_segments=source_segments,
                translated_texts=reviewed,
                target_lang=target_lang,
            )
            print(
                "[Translation QA] Contextual semantic review completed via "
                f"{', '.join(providers) or provider_type}."
            )
            # The caller runs the quality guard once after review and owns
            # targeted repair. Returning its warnings here would duplicate
            # every readability warning in the final project report.
            return guarded, list(batch_warnings)
        except Exception as exc:
            print(f"[Translation QA] Contextual semantic review skipped: {exc}")
            return list(translated_texts), [
                f"Contextual semantic review failed; the first-pass translation was kept. ({exc})"
            ]

    @staticmethod
    def _run_ai_batch_requests(*, polisher, batches, src_lang, target_lang, style_instruction, max_workers, on_progress=None, cancellation_check=None):
        """Submit validated ordered batches and merge their results by index."""
        warnings = []
        providers_used = set()
        translated_texts_map = {}
        total_batches = max(1, len(batches))
        if max_workers == 1:
            recent_pairs: list[tuple[str, str]] = []

            def submit_batch(source_batch, translated_batch, max_tokens, *, context_before=None, context_after=None):
                """Run one ordered batch, splitting a malformed numbered reply.

                A provider occasionally stops after a few numbered lines of a
                large batch (e.g. IDs 1..6 of 1..24). Retrying the identical
                oversized request cannot restore the truncated reply, but
                failing the whole translation pass is worse. Split the batch
                in half and retry each half so only genuinely broken
                single-cue replies surface.
                """
                if cancellation_check and cancellation_check():
                    raise InterruptedError("Translation cancelled by user")
                total = len(source_batch)
                try:
                    batch_result, batch_warnings, provider_name = polisher.polish_batch(
                        source_texts=list(source_batch),
                        translated_texts=list(translated_batch) if translated_batch is not None else None,
                        src_lang=src_lang,
                        target_lang=target_lang,
                        style_instruction=style_instruction,
                        context_before=context_before,
                        context_after=context_after,
                        max_tokens=max_tokens,
                    )
                    return list(batch_result), list(batch_warnings), provider_name
                except TranslationValidationError as exc:
                    # A single-cue reply that is still malformed is genuinely
                    # broken; anything larger can be split for another try.
                    if total < 2:
                        raise
                    split_at = total // 2
                    left_src = source_batch[:split_at]
                    right_src = source_batch[split_at:]
                    left_draft = translated_batch[:split_at] if translated_batch is not None else None
                    right_draft = translated_batch[split_at:] if translated_batch is not None else None
                    left_tokens = max(1024, int(max_tokens or 1024) * len(left_src) // total + 256)
                    right_tokens = max(1024, int(max_tokens or 1024) * len(right_src) // total + 256)
                    print(
                        "[AI Translation] Malformed numbered reply for a "
                        f"{total}-cue batch ({exc}). Retrying as two smaller batches "
                        f"({len(left_src)} + {len(right_src)} cues)..."
                    )
                    left_result, left_warnings, left_provider = submit_batch(
                        left_src,
                        left_draft,
                        left_tokens,
                        context_before=context_before,
                        context_after=right_src[:3],
                    )
                    right_context_before = [
                        f"{src} => {trans}"
                        for src, trans in zip(left_src[-5:], left_result[-5:])
                    ]
                    right_result, right_warnings, right_provider = submit_batch(
                        right_src,
                        right_draft,
                        right_tokens,
                        context_before=right_context_before,
                        context_after=context_after,
                    )
                    return (
                        left_result + right_result,
                        left_warnings + right_warnings,
                        left_provider or right_provider,
                    )

            for idx, (source_batch, translated_batch, max_tokens) in enumerate(batches):
                if cancellation_check and cancellation_check():
                    raise InterruptedError("Translation cancelled by user")
                if on_progress:
                    pct = int(idx * 100 / total_batches)
                    msg = f"Translating batch {idx + 1}/{total_batches} (AI)..."
                    try:
                        from app.core.models.progress import ProgressEvent
                        on_progress(ProgressEvent(
                            workflow="translate",
                            stage="translation",
                            substage="batch",
                            current=float(idx + 1),
                            total=float(total_batches),
                            percent=pct,
                            message=msg,
                        ))
                    except Exception:
                        on_progress(msg)
                context_before = [
                    f"{source} => {translation}"
                    for source, translation in recent_pairs[-5:]
                ]
                context_after = list(batches[idx + 1][0][:3]) if idx + 1 < len(batches) else []
                batch_result, batch_warnings, provider_name = submit_batch(
                    source_batch,
                    translated_batch,
                    max_tokens,
                    context_before=context_before,
                    context_after=context_after,
                )
                translated_texts_map[idx] = batch_result
                warnings.extend(batch_warnings)
                if provider_name:
                    providers_used.add(provider_name)
                recent_pairs.extend(zip(source_batch, batch_result))
            merged = []
            for idx in range(len(batches)):
                merged.extend(translated_texts_map[idx])
            return merged, sorted(providers_used), warnings

        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, max_workers)) as executor:
            future_to_idx = {}
            for idx, (source_batch, translated_batch, max_tokens) in enumerate(batches):
                context_before = list(batches[idx - 1][0][-5:]) if idx > 0 else []
                context_after = list(batches[idx + 1][0][:3]) if idx + 1 < len(batches) else []
                future = executor.submit(
                    polisher.polish_batch,
                    source_texts=source_batch,
                    translated_texts=translated_batch,
                    src_lang=src_lang,
                    target_lang=target_lang,
                    style_instruction=style_instruction,
                    context_before=context_before,
                    context_after=context_after,
                    max_tokens=max_tokens,
                )
                future_to_idx[future] = idx

            completed_count = 0
            for future in concurrent.futures.as_completed(future_to_idx):
                if cancellation_check and cancellation_check():
                    for f in future_to_idx:
                        f.cancel()
                    raise InterruptedError("Translation cancelled by user")
                idx = future_to_idx[future]
                try:
                    batch_result, batch_warnings, provider_name = future.result()
                    translated_texts_map[idx] = batch_result
                    warnings.extend(batch_warnings)
                    if provider_name:
                        providers_used.add(provider_name)
                    completed_count += 1
                    if on_progress:
                        pct = int(completed_count * 100 / total_batches)
                        msg = f"Translating batch {completed_count}/{total_batches} (AI)..."
                        try:
                            from app.core.models.progress import ProgressEvent
                            on_progress(ProgressEvent(
                                workflow="translate",
                                stage="translation",
                                substage="batch",
                                current=float(completed_count),
                                total=float(total_batches),
                                percent=pct,
                                message=msg,
                            ))
                        except Exception:
                            on_progress(msg)
                except Exception as exc:
                    if isinstance(exc, TranslationValidationError):
                        raise
                    raise Exception(f"Batch {idx + 1} failed: {exc}") from exc

        merged = []
        for idx in range(len(batches)):
            merged.extend(translated_texts_map[idx])
        return merged, sorted(providers_used), warnings

    @staticmethod
    def _build_ai_batches(
        *,
        source_texts: list[str],
        translated_texts: list[str] | None,
        requested_max_segments: int,
        force_ordered: bool = False,
        max_chars_limit: int | None = None,
        response_token_limit: int | None = None,
    ) -> tuple[list[tuple[list[str], list[str] | None, int]], bool]:
        """Create ordered AI batches with both cue and prompt-size limits.

        Prefer one request for the full video whenever its estimated input and
        numbered response fit a conservative provider-independent budget.
        This gives the model full narrative context.  Longer videos fall back
        to ordered context-sized batches.  Environment values are optional
        escape hatches for self-hosted providers with smaller limits.
        """
        if translated_texts is not None and len(source_texts) != len(translated_texts):
            raise TranslationValidationError("Source and draft subtitle counts do not match.")

        def _env_int(name: str, default: int) -> int:
            try:
                return int(os.getenv(name, str(default)))
            except ValueError:
                return default

        def _estimate_tokens(text: str) -> int:
            # CJK glyphs commonly consume approximately one token each;
            # Latin-script text is generally less dense.  Using the larger
            # estimate keeps the automatic fallback conservative.
            text = str(text or "")
            cjk = sum(
                1 for char in text
                if "\u3400" <= char <= "\u9fff" or "\uf900" <= char <= "\ufaff"
            )
            return cjk + math.ceil((len(text) - cjk) / 3.5)

        source_token_estimate = sum(_estimate_tokens(text) for text in source_texts)
        draft_token_estimate = (
            sum(_estimate_tokens(text) for text in translated_texts)
            if translated_texts is not None else 0
        )
        input_tokens = source_token_estimate + draft_token_estimate + (12 * len(source_texts)) + 220
        # Translation can expand compact CJK dialogue considerably.  This
        # leaves response room without assuming a specific destination language.
        response_tokens = max(512, math.ceil(max(source_token_estimate, draft_token_estimate) * 1.8) + (10 * len(source_texts)))
        context_limit = max(4096, _env_int("VIUSTUDIO_AI_TRANSLATION_CONTEXT_TOKENS", 24000))
        output_limit = max(1024, _env_int("VIUSTUDIO_AI_TRANSLATION_MAX_OUTPUT_TOKENS", 8192))
        if not force_ordered and input_tokens + response_tokens <= context_limit and response_tokens <= output_limit:
            print(
                "[AI Translation] Full-context request: "
                f"input~{input_tokens} tokens, output~{response_tokens} tokens."
            )
            return ([(list(source_texts), list(translated_texts) if translated_texts is not None else None,
                     min(output_limit, max(1024, response_tokens)))], True)

        try:
            configured_max = int(os.getenv("VIUSTUDIO_AI_TRANSLATION_MAX_SEGMENTS", "80"))
        except ValueError:
            configured_max = 80
        max_segments = max(1, min(int(requested_max_segments or 80), max(1, configured_max)))
        max_chars = int(max_chars_limit or _env_int("VIUSTUDIO_AI_TRANSLATION_MAX_CHARS", 18000))
        # Draft rewriting sends both source and translated text in the prompt.
        max_chars = max(2000, max_chars // (2 if translated_texts is not None else 1))

        per_batch_response_limit = int(response_token_limit or 3600)
        batches: list[tuple[list[str], list[str] | None, int]] = []
        current_source: list[str] = []
        current_drafts: list[str] | None = [] if translated_texts is not None else None
        current_chars = 0
        current_response_tokens = 0
        for index, source in enumerate(source_texts):
            source = str(source or "")
            draft = str(translated_texts[index] or "") if translated_texts is not None else ""
            item_chars = len(source) + len(draft) + 16
            item_response_tokens = math.ceil(max(_estimate_tokens(source), _estimate_tokens(draft)) * 1.8) + 10
            if current_source and (
                len(current_source) >= max_segments
                or current_chars + item_chars > max_chars
                or current_response_tokens + item_response_tokens > per_batch_response_limit
            ):
                batches.append((current_source, current_drafts, max(1024, min(per_batch_response_limit + 256, current_response_tokens + 128))))
                current_source = []
                current_drafts = [] if translated_texts is not None else None
                current_chars = 0
                current_response_tokens = 0
            current_source.append(source)
            if current_drafts is not None:
                current_drafts.append(draft)
            current_chars += item_chars
            current_response_tokens += item_response_tokens
        if current_source:
            batches.append((current_source, current_drafts, max(1024, min(per_batch_response_limit + 256, current_response_tokens + 128))))
        return batches, False

    def _emit_batch_callback(
        self,
        *,
        batch_callback,
        base_segments: list[dict],
        start_idx: int,
        translated_texts: list[str],
        provider: str,
        polished: bool,
    ) -> None:
        if batch_callback is None or not translated_texts:
            return
        try:
            batch_segments = clone_with_texts(
                list(base_segments[start_idx:start_idx + len(translated_texts)]),
                list(translated_texts),
                provider=provider,
                polished=polished,
            )
            batch_callback(start_idx, batch_segments)
        except Exception as exc:
            print(f"[Translation] Batch callback skipped: {exc}")
    def _maybe_optimize_subtitle_segments(
        self,
        *,
        polisher,
        provider_type: str,
        source_segments: list[dict],
        translated_segments: list[dict],
        src_lang: str,
        target_lang: str,
        warnings: list[str],
        style_instruction: str = "",
    ) -> list[dict]:
        if not translated_segments:
            return translated_segments
        try:
            print('[AI Subtitle Optimization] Starting subtitle optimization...')
            single_line = self._style_prefers_single_line(style_instruction)
            cleaned_style_instruction = self._strip_layout_markers(style_instruction)
            source_texts = [
                self._build_subtitle_optimization_source_text(seg, single_line=False)
                for seg in source_segments
            ]
            translated_texts = [seg.get('text') or '' for seg in translated_segments]
            style_clause = (
                f' Extra style instruction: {cleaned_style_instruction}'
                if cleaned_style_instruction else ''
            )
            optimization_instruction = render_prompt(
                'subtitle_optimization.instruction.md',
                style_clause=style_clause,
            )
            optimized_texts, providers_used, batch_warnings = self._run_ai_batches(
                polisher=polisher,
                provider_type=provider_type,
                source_texts=source_texts,
                translated_texts=translated_texts,
                src_lang=src_lang,
                target_lang=target_lang,
                style_instruction=optimization_instruction,
                polish_batch_size=len(source_texts),
            )
            warnings.extend(batch_warnings)
            normalized_texts = [
                self._normalize_optimized_subtitle_text(
                    text,
                    source_seg,
                    draft_text=(translated_seg.get('text') or ''),
                    single_line=False,
                )
                for text, source_seg, translated_seg in zip(optimized_texts, source_segments, translated_segments)
            ]
            if not validate_texts(normalized_texts, len(translated_segments)):
                raise TranslationValidationError('Subtitle optimization returned invalid text count.')
            print(f"[AI Subtitle Optimization] Success: completed via {' -> '.join(providers_used) or provider_type}")
            optimized_segments = clone_with_texts(translated_segments, normalized_texts, provider=provider_type, polished=True)
            if single_line:
                before_count = len(optimized_segments)
                optimized_segments = self._split_segments_for_single_line(
                    optimized_segments,
                    polisher=polisher,
                    provider_type=provider_type,
                    target_lang=target_lang,
                )
                print(f'[AI Subtitle Optimization] Single-line cue split: {before_count} -> {len(optimized_segments)} cues')
            return optimized_segments
        except Exception as exc:
            msg = f'Subtitle optimization skipped: {exc}'
            print(f'[AI Subtitle Optimization] WARNING: {msg}')
            warnings.append(msg)
            return translated_segments

    def _build_subtitle_optimization_source_text(self, seg: dict, *, single_line: bool = False) -> str:
        start = float(seg.get('start', 0.0) or 0.0)
        end = float(seg.get('end', 0.0) or 0.0)
        duration = max(0.6, end - start)
        max_cps = self._target_max_cps(duration, single_line=single_line)
        max_chars = self._target_max_chars(duration, single_line=single_line)
        max_lines = 1 if single_line else 2
        return (
            f"[duration={duration:.2f}s][max_cps={max_cps}][max_chars={max_chars}]"
            f"[max_lines={max_lines}] {seg.get('text') or ''}"
        )

    def _normalize_optimized_subtitle_text(self, text: str, seg: dict, *, draft_text: str = '', single_line: bool = False) -> str:
        cleaned = str(text or '').replace('<br/>', '\n').replace('<br />', '\n').replace('<br>', '\n')
        cleaned = '\n'.join(' '.join(part.split()) for part in cleaned.splitlines() if part.strip())
        draft = str(draft_text or '').replace('<br/>', '\n').replace('<br />', '\n').replace('<br>', '\n')
        draft = '\n'.join(' '.join(part.split()) for part in draft.splitlines() if part.strip())
        if not cleaned:
            cleaned = draft or str(seg.get('text') or '').strip()
        duration = max(0.6, float(seg.get('end', 0.0) or 0.0) - float(seg.get('start', 0.0) or 0.0))
        wrapped_cleaned = self._wrap_subtitle_text(cleaned, duration, single_line=single_line)
        wrapped_draft = self._wrap_subtitle_text(draft, duration, single_line=single_line) if draft else ''
        if wrapped_draft and self._should_keep_original_translation(wrapped_draft, wrapped_cleaned, duration, single_line=single_line):
            return wrapped_draft
        return wrapped_cleaned

    def _should_keep_original_translation(self, original_text: str, optimized_text: str, duration: float, *, single_line: bool = False) -> bool:
        original = str(original_text or '').strip()
        optimized = str(optimized_text or '').strip()
        if not original or not optimized or original == optimized:
            return False
        if not self._is_subtitle_readable(original, duration, single_line=single_line):
            return False
        overlap = self._token_overlap_ratio(original, optimized)
        length_delta = abs(len(original.replace('\n', ' ')) - len(optimized.replace('\n', ' ')))
        return overlap < 0.58 and length_delta >= 8

    def _is_subtitle_readable(self, text: str, duration: float, *, single_line: bool = False) -> bool:
        normalized = str(text or '').strip()
        if not normalized:
            return False
        lines = [line.strip() for line in normalized.splitlines() if line.strip()]
        if not lines:
            return False
        max_lines = 1 if single_line else 2
        if len(lines) > max_lines:
            return False
        max_chars = self._target_max_chars(duration, single_line=single_line)
        if any(len(line) > max_chars + 6 for line in lines):
            return False
        cps = len(' '.join(lines).replace(' ', '')) / max(duration, 0.6)
        return cps <= (self._target_max_cps(duration, single_line=single_line) + 1.5)

    def _token_overlap_ratio(self, left_text: str, right_text: str) -> float:
        left_tokens = re.findall(r'\w+', str(left_text or '').lower())
        right_tokens = re.findall(r'\w+', str(right_text or '').lower())
        if not left_tokens or not right_tokens:
            return 1.0
        left_set = set(left_tokens)
        right_set = set(right_tokens)
        common = len(left_set & right_set)
        return common / max(1, len(left_set | right_set))

    def _wrap_subtitle_text(self, text: str, duration: float, *, single_line: bool = False) -> str:
        normalized = ' '.join(str(text or '').replace('\n', ' \n ').split())
        normalized = normalized.replace(' \n ', '\n').strip()
        if not normalized:
            return ''
        existing_lines = [line.strip() for line in normalized.splitlines() if line.strip()]
        if single_line:
            compact = ' '.join(existing_lines).strip()
            return self._shorten_single_line_text(compact, duration)
        max_line_chars = self._target_max_chars(duration, single_line=False)
        # Hard cap: max 2 lines, each at most max_line_chars
        single = ' '.join(existing_lines).strip()
        if len(single) <= max_line_chars:
            return single
        # Split into at most 2 lines, strictly capping each at max_line_chars
        words = single.split()
        best_index = max(1, len(words) // 2)
        best_score = float('inf')
        for idx in range(1, len(words)):
            left = ' '.join(words[:idx]).strip()
            right = ' '.join(words[idx:]).strip()
            if not left or not right:
                continue
            # Heavy penalty for exceeding hard cap
            penalty = (max(0, len(left) - max_line_chars) + max(0, len(right) - max_line_chars)) * 100
            balance_score = abs(len(left) - len(right))
            score = balance_score + penalty
            if score < best_score:
                best_score = score
                best_index = idx
        left = ' '.join(words[:best_index]).strip()
        right = ' '.join(words[best_index:]).strip()
        if not left or not right:
            return single[:max_line_chars]
        # Enforce hard cap on both sides by trimming at word boundary
        def _trim_to_limit(s: str, limit: int) -> str:
            if len(s) <= limit:
                return s
            toks = s.split()
            kept = []
            for w in toks:
                cand = ' '.join(kept + [w])
                if len(cand) <= limit:
                    kept.append(w)
                else:
                    break
            return ' '.join(kept).strip() if kept else toks[0][:limit]
        left = _trim_to_limit(left, max_line_chars)
        right = _trim_to_limit(right, max_line_chars)
        if not right:
            return left
        return f'{left}\n{right}'

    def _shorten_single_line_text(self, text: str, duration: float) -> str:
        compact = ' '.join(str(text or '').split()).strip()
        if not compact:
            return ''
        max_chars = self._target_max_chars(duration, single_line=True)
        if len(compact) <= max_chars:
            return compact

        filler_words = {
            'thì', 'là', 'mà', 'đó', 'này', 'ấy', 'vậy', 'nha', 'nhé', 'đi', 'liền', 'ngay', 'rồi', 'đang', 'cũng'
        }
        filler_phrases = [
            'một cách', 'kiểu như', 'có thể nói là', 'thật sự là', 'về cơ bản', 'nói chung là'
        ]

        candidate = compact
        lowered = candidate.lower()
        for phrase in filler_phrases:
            if phrase in lowered:
                candidate = self._remove_phrase_case_insensitive(candidate, phrase)
                lowered = candidate.lower()
        filtered_words = [word for word in candidate.split() if word.lower() not in filler_words]
        candidate = ' '.join(filtered_words).strip() or candidate
        candidate = re.sub(r'\s+([,.;:!?])', r'\1', candidate)
        candidate = re.sub(r'([,.;:!?]){2,}', r'\1', candidate).strip(' ,;:')

        # Keep the full subtitle meaning in single-line mode.
        # We prefer a slightly longer one-line subtitle over trimming away content.
        return candidate or compact

    def _target_max_chars(self, duration: float, *, single_line: bool) -> int:
        # User requirement: max 20 chars per line, max 2 lines
        if single_line:
            if duration <= 1.2:
                return 10
            if duration <= 1.8:
                return 13
            if duration <= 2.6:
                return 16
            if duration <= 3.4:
                return 18
            return 20
        # dual-line mode: same 20 char hard cap per line
        if duration <= 1.4:
            return 15
        if duration <= 2.6:
            return 18
        if duration <= 4.0:
            return 20
        return 20

    def _target_max_cps(self, duration: float, *, single_line: bool) -> int:
        if single_line:
            if duration <= 1.2:
                return 10
            if duration <= 2.0:
                return 11
            if duration <= 3.2:
                return 12
            return 13
        return max(10, min(16, int(round(13 + min(duration, 4.0) * 0.75))))

    def _strip_layout_markers(self, style_instruction: str) -> str:
        text = str(style_instruction or '')
        text = text.replace('[subtitle_layout=single_line]', ' ')
        text = text.replace('|  |', '|')
        text = text.replace('||', '|')
        parts = [part.strip() for part in text.split('|') if part.strip()]
        return ' | '.join(parts)

    def _style_prefers_single_line(self, style_instruction: str) -> bool:
        normalized = str(style_instruction or '').strip().lower()
        return (
            '[subtitle_layout=single_line]' in normalized
            or 'single-line' in normalized
            or 'one line only' in normalized
            or 'netflix-style' in normalized
        )

    def _remove_phrase_case_insensitive(self, text: str, phrase: str) -> str:
        return re.sub(re.escape(phrase), '', text, flags=re.IGNORECASE).replace('  ', ' ').strip()

    def _split_segments_for_single_line(
        self,
        segments: list[dict],
        *,
        polisher=None,
        provider_type: str = "",
        target_lang: str = "vi",
        words_per_segment: int | None = None,
    ) -> list[dict]:
        split_segments: list[dict] = []
        for seg in segments or []:
            text = ' '.join(str(seg.get('text') or '').replace('\n', ' ').split()).strip()
            if not text:
                split_segments.append(dict(seg))
                continue
            start = float(seg.get('start', 0.0) or 0.0)
            end = float(seg.get('end', 0.0) or 0.0)
            duration = max(0.6, end - start)
            group_id = f"tts-{seg.get('id', len(split_segments) + 1)}-{int(round(start * 1000))}"
            chunks = self._split_text_into_single_line_chunks(
                text,
                duration,
                polisher=polisher,
                provider_type=provider_type,
                target_lang=target_lang,
                words_per_segment=words_per_segment,
            )
            if len(chunks) <= 1:
                updated = dict(seg)
                visible_text = chunks[0] if chunks else text
                updated['text'] = visible_text
                # ``translation_final`` dictionaries may still carry the
                # unsplit sentence in these model fields.  Segment.from_dict
                # prefers them over ``text`` when an SRT is rendered, which
                # used to repeat the complete sentence in every visual chunk.
                # A split changes display text only; ``tts_text`` intentionally
                # remains the complete grouped utterance for voice synthesis.
                for key in ('final_text', 'refined_translation', 'raw_translation'):
                    if key in updated:
                        updated[key] = visible_text
                updated['tts_group_id'] = group_id
                updated['tts_group_start'] = round(start, 3)
                updated['tts_group_end'] = round(end, 3)
                updated.pop('_audio_end', None)
                split_segments.append(updated)
                continue

            total_weight = sum(max(1, len(chunk.replace(' ', ''))) for chunk in chunks)
            cursor = start
            for idx, chunk in enumerate(chunks):
                updated = dict(seg)
                updated.pop('_audio_end', None)
                updated['text'] = chunk
                for key in ('final_text', 'refined_translation', 'raw_translation'):
                    if key in updated:
                        updated[key] = chunk
                updated['tts_group_id'] = group_id
                updated['tts_group_start'] = round(start, 3)
                updated['tts_group_end'] = round(end, 3)
                if idx == len(chunks) - 1:
                    chunk_end = end
                else:
                    weight = max(1, len(chunk.replace(' ', '')))
                    share = duration * (weight / total_weight)
                    min_slice = 0.45
                    remaining_needed = min_slice * (len(chunks) - idx - 1)
                    max_end = end - remaining_needed
                    chunk_end = min(max_end, cursor + max(min_slice, share))
                updated['start'] = round(cursor, 3)
                updated['end'] = round(max(cursor + 0.2, chunk_end), 3)
                cursor = updated['end']
                split_segments.append(updated)
        return split_segments

    def _try_ai_split_single_line_chunks(
        self,
        text: str,
        duration: float,
        *,
        polisher=None,
        provider_type: str = "",
        target_lang: str = "vi",
        max_chars: int = 24,
    ) -> list[str] | None:
        if polisher is None or not hasattr(polisher, 'split_single_line_text'):
            return None
        if len(text.split()) <= 5:
            return None
        max_chunks = 2 if duration <= 1.6 else 3 if duration <= 3.4 else 4
        try:
            chunks = polisher.split_single_line_text(
                text=text,
                target_lang=target_lang,
                max_chars=max_chars,
                max_chunks=max_chunks,
            )
        except Exception:
            return None
        normalized = [self._normalize_ai_split_chunk(part) for part in chunks if self._normalize_ai_split_chunk(part)]
        if len(normalized) <= 1:
            return None
        original_key = self._normalized_chunk_key(text)
        candidate_key = self._normalized_chunk_key(' '.join(normalized))
        if original_key != candidate_key:
            return None
        if any(len(chunk.split()) <= 1 for chunk in normalized):
            return None
        return normalized

    def _normalize_ai_split_chunk(self, text: str) -> str:
        return ' '.join(str(text or '').replace('\n', ' ').split()).strip(' |,;')

    def _normalized_chunk_key(self, text: str) -> str:
        return re.sub(r'\W+', '', str(text or '').lower(), flags=re.UNICODE)

    def _split_text_into_single_line_chunks(
        self,
        text: str,
        duration: float,
        *,
        polisher=None,
        provider_type: str = "",
        target_lang: str = "vi",
        words_per_segment: int | None = None,
    ) -> list[str]:
        compact = ' '.join(str(text or '').replace('\n', ' ').split()).strip()
        if not compact:
            return []

        if words_per_segment is not None:
            limit = max(1, int(words_per_segment))
            words = compact.split()
            return [" ".join(words[index:index + limit]) for index in range(0, len(words), limit)]

        max_chars = max(18, self._target_max_chars(duration, single_line=True))
        if len(compact) <= max_chars or len(compact.split()) <= 4:
            return [compact]

        sentence_parts = [part.strip(' ,') for part in re.split(r'(?<=[,.;:!?])\s+', compact) if part.strip(' ,')]
        if len(sentence_parts) > 1:
            chunks: list[str] = []
            per_part_duration = max(0.6, duration / max(1, len(sentence_parts)))
            for part in sentence_parts:
                chunks.extend(self._split_text_into_single_line_chunks(part, per_part_duration))
            return chunks

        words = compact.split()
        if len(words) <= 5:
            return [compact]

        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        soft_limit = max(18, max_chars)
        for word in words:
            addition = len(word) if not current else len(word) + 1
            if current and current_len + addition > soft_limit and len(current) >= 3:
                chunks.append(' '.join(current).strip())
                current = [word]
                current_len = len(word)
            else:
                current.append(word)
                current_len += addition
        if current:
            chunks.append(' '.join(current).strip())

        return [chunk for chunk in chunks if chunk] or [compact]

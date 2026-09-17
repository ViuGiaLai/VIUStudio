from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class GeminiKeyEntry:
    id: str
    label: str
    api_key: str
    enabled: bool = True
    fail_count: int = 0
    last_error: str = ""
    last_used_at: float = 0.0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GeminiKeyEntry":
        return cls(
            id=str(payload.get("id") or uuid.uuid4().hex),
            label=str(payload.get("label") or "Gemini key"),
            api_key=str(payload.get("api_key") or "").strip(),
            enabled=bool(payload.get("enabled", True)),
            fail_count=max(0, int(payload.get("fail_count", 0) or 0)),
            last_error=str(payload.get("last_error") or ""),
            last_used_at=float(payload.get("last_used_at", 0.0) or 0.0),
        )


class GeminiKeyPool:
    """Ordered local key list used by Movie Review Gemini requests."""

    def __init__(self, path: str | None = None):
        self.path = os.path.abspath(path or os.getenv("GEMINI_KEY_POOL_FILE", "gemini_keys.json"))

    def load(self) -> list[GeminiKeyEntry]:
        try:
            payload = json.loads(Path(self.path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        raw = payload.get("keys", []) if isinstance(payload, dict) else []
        return [GeminiKeyEntry.from_dict(item) for item in raw if isinstance(item, dict) and str(item.get("api_key", "")).strip()]

    def save(self, entries: list[GeminiKeyEntry]) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        temporary = f"{self.path}.tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "keys": [asdict(item) for item in entries]}, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, self.path)

    def upsert(self, label: str, api_key: str, *, entry_id: str = "", enabled: bool = True) -> GeminiKeyEntry:
        entries = self.load()
        selected = next((item for item in entries if item.id == entry_id), None)
        if selected is None:
            selected = GeminiKeyEntry(uuid.uuid4().hex, label.strip() or f"Key {len(entries) + 1}", api_key.strip(), enabled)
            entries.append(selected)
        else:
            selected.label = label.strip() or selected.label
            selected.api_key = api_key.strip()
            selected.enabled = enabled
            selected.fail_count = 0
            selected.last_error = ""
        self.save(entries)
        return selected

    def delete(self, entry_id: str) -> None:
        self.save([item for item in self.load() if item.id != entry_id])

    def enabled_keys(self, fallback_key: str = "") -> list[tuple[str, str]]:
        result = [(item.id, item.api_key) for item in self.load() if item.enabled and item.api_key]
        fallback = str(fallback_key or "").strip()
        if fallback and fallback not in {key for _entry_id, key in result}:
            result.append(("environment", fallback))
        return result

    def mark_result(self, entry_id: str, *, error: str = "") -> None:
        if not entry_id or entry_id == "environment":
            return
        entries = self.load()
        for item in entries:
            if item.id != entry_id:
                continue
            item.last_used_at = time.time()
            if error:
                item.fail_count += 1
                item.last_error = error[:500]
            else:
                item.fail_count = 0
                item.last_error = ""
            break
        self.save(entries)

    @staticmethod
    def mask(api_key: str) -> str:
        value = str(api_key or "")
        if len(value) <= 8:
            return "•" * len(value)
        return f"{value[:4]}{'•' * 8}{value[-4:]}"

    @staticmethod
    def should_rotate(error: Exception) -> bool:
        status = getattr(getattr(error, "response", None), "status_code", None)
        message = str(error).casefold()
        return status in {401, 403, 429} or any(
            marker in message for marker in (
                "quota", "rate limit", "resource_exhausted", "too many requests",
                "api key not valid", "permission denied", "unauthorized",
            )
        )

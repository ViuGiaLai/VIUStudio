import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "app"), str(ROOT)]

from app.services.gemini_key_pool import GeminiKeyPool


def test_key_pool_crud_preserves_failover_order(tmp_path):
    pool = GeminiKeyPool(str(tmp_path / "keys.json"))
    first = pool.upsert("Key 1", "abc-111")
    second = pool.upsert("Key 2", "abc-222")

    assert pool.enabled_keys() == [(first.id, "abc-111"), (second.id, "abc-222")]
    pool.upsert("Key 1 sửa", "abc-111-new", entry_id=first.id, enabled=False)
    assert pool.enabled_keys() == [(second.id, "abc-222")]
    assert pool.load()[0].label == "Key 1 sửa"

    pool.delete(first.id)
    assert [item.id for item in pool.load()] == [second.id]


def test_key_pool_records_failures_and_masks_secrets(tmp_path):
    pool = GeminiKeyPool(str(tmp_path / "keys.json"))
    entry = pool.upsert("Primary", "abcdefghijklmnop")
    pool.mark_result(entry.id, error="429 quota exhausted")

    loaded = pool.load()[0]
    assert loaded.fail_count == 1
    assert "quota" in loaded.last_error
    assert pool.mask(loaded.api_key) == "abcd••••••••mnop"
    assert pool.should_rotate(RuntimeError("RESOURCE_EXHAUSTED quota"))
    assert not pool.should_rotate(TimeoutError("network timeout"))

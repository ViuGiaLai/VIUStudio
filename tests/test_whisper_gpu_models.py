from __future__ import annotations

import os
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "app"), str(ROOT / "ui")]

from services.resource_download_service import ResourceDownloadService
from whisper_processor import KNOWN_FASTER_WHISPER_MODELS, _cached_model_snapshot


def test_known_faster_whisper_models_includes_turbo_and_large_v3():
    assert "large-v3" in KNOWN_FASTER_WHISPER_MODELS
    assert "large-v3-turbo" in KNOWN_FASTER_WHISPER_MODELS
    assert "turbo" in KNOWN_FASTER_WHISPER_MODELS
    assert "medium" in KNOWN_FASTER_WHISPER_MODELS


def test_list_resources_includes_whisper_large_v3_and_turbo(tmp_path):
    service = ResourceDownloadService(str(tmp_path))
    resources = {r["id"]: r for r in service.list_resources()}

    # Check whisper:large-v3
    assert "whisper:large-v3" in resources
    lv3 = resources["whisper:large-v3"]
    assert lv3["kind"] == "whisper"
    assert "Large-v3" in lv3["name"]
    assert lv3["auto_download_supported"] is True
    assert "Systran/faster-whisper-large-v3" in lv3["download_url"]

    # Check whisper:large-v3-turbo
    assert "whisper:large-v3-turbo" in resources
    turbo = resources["whisper:large-v3-turbo"]
    assert turbo["kind"] == "whisper"
    assert "Large-v3-Turbo" in turbo["name"]
    assert turbo["auto_download_supported"] is True
    assert "mobiuslabsgmbh/faster-whisper-large-v3-turbo" in turbo["download_url"]

    # Check whisper:medium
    assert "whisper:medium" in resources
    med = resources["whisper:medium"]
    assert med["kind"] == "whisper"
    assert med["auto_download_supported"] is True

    # Check cuda pack
    assert "cuda:whisper" in resources


def test_matches_whisper_model_name_distinguishes_large_v3_from_turbo():
    # Target: large-v3
    assert ResourceDownloadService._matches_whisper_model_name("models--Systran--faster-whisper-large-v3", "large-v3") is True
    assert ResourceDownloadService._matches_whisper_model_name("large-v3", "large-v3") is True
    # MUST NOT match turbo!
    assert ResourceDownloadService._matches_whisper_model_name("models--mobiuslabsgmbh--faster-whisper-large-v3-turbo", "large-v3") is False
    assert ResourceDownloadService._matches_whisper_model_name("large-v3-turbo", "large-v3") is False

    # Target: large-v3-turbo
    assert ResourceDownloadService._matches_whisper_model_name("models--mobiuslabsgmbh--faster-whisper-large-v3-turbo", "large-v3-turbo") is True
    assert ResourceDownloadService._matches_whisper_model_name("models--Systran--faster-whisper-large-v3-turbo", "large-v3-turbo") is True
    assert ResourceDownloadService._matches_whisper_model_name("large-v3-turbo", "large-v3-turbo") is True
    assert ResourceDownloadService._matches_whisper_model_name("turbo", "large-v3-turbo") is True
    assert ResourceDownloadService._matches_whisper_model_name("models--Systran--faster-whisper-large-v3", "large-v3-turbo") is False

    # Target: medium
    assert ResourceDownloadService._matches_whisper_model_name("models--Systran--faster-whisper-medium", "medium") is True
    assert ResourceDownloadService._matches_whisper_model_name("medium", "medium") is True
    assert ResourceDownloadService._matches_whisper_model_name("models--Systran--faster-whisper-small", "medium") is False


def test_is_resource_installed_with_model_files(tmp_path, monkeypatch):
    import services.resource_download_service as rds
    models_root = tmp_path / "models" / "faster_whisper"
    models_root.mkdir(parents=True)

    monkeypatch.setattr(rds, "models_path", lambda *parts: str(tmp_path.joinpath("models", *parts)))
    service = ResourceDownloadService(str(tmp_path))

    # Before installing
    assert service.is_resource_installed("whisper:large-v3") is False
    assert service.is_resource_installed("whisper:large-v3-turbo") is False

    # Create dummy large-v3 folder with model.bin
    lv3_dir = models_root / "models--Systran--faster-whisper-large-v3"
    lv3_dir.mkdir()
    (lv3_dir / "model.bin").write_bytes(b"dummy model bytes")

    assert service.is_resource_installed("whisper:large-v3") is True
    # large-v3-turbo must still be False!
    assert service.is_resource_installed("whisper:large-v3-turbo") is False

    # Now create snapshot for large-v3-turbo
    turbo_dir = models_root / "models--mobiuslabsgmbh--faster-whisper-large-v3-turbo" / "snapshots" / "abc123"
    turbo_dir.mkdir(parents=True)
    (turbo_dir / "model.bin").write_bytes(b"dummy turbo bytes")

    assert service.is_resource_installed("whisper:large-v3-turbo") is True


def test_is_whisper_installed_from_zip(tmp_path, monkeypatch):
    import zipfile
    import io
    import services.resource_download_service as rds
    models_root = tmp_path / "models" / "faster_whisper"
    models_root.mkdir(parents=True)

    monkeypatch.setattr(rds, "models_path", lambda *parts: str(tmp_path.joinpath("models", *parts)))
    service = ResourceDownloadService(str(tmp_path))

    # Create a zip containing models--Systran--faster-whisper-large-v3/model.bin
    zip_path = models_root / "models--Systran--faster-whisper-large-v3.zip"
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as zf:
        zf.writestr("models--Systran--faster-whisper-large-v3/model.bin", b"X" * (1024 * 1024 + 100))
    zip_path.write_bytes(payload.getvalue())

    # is_resource_installed should detect the zip, auto-extract it, and return True!
    assert service.is_resource_installed("whisper:large-v3") is True
    assert (models_root / "models--Systran--faster-whisper-large-v3" / "model.bin").is_file()

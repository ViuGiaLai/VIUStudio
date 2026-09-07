from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "app"), str(ROOT)]

import services.resource_download_service as resource_download_module
from services.resource_download_service import ResourceDownloadService


def _archive(*entries: tuple[str, bytes]) -> zipfile.ZipFile:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    payload.seek(0)
    return zipfile.ZipFile(payload, "r")


def test_safe_extract_zip_rejects_parent_traversal(tmp_path):
    destination = tmp_path / "models"
    outside = tmp_path / "outside.txt"
    with _archive(("../outside.txt", b"must not be written")) as archive:
        with pytest.raises(ValueError, match="traversal"):
            ResourceDownloadService._safe_extract_zip(archive, str(destination))
    assert not outside.exists()


def test_safe_extract_zip_rejects_absolute_paths(tmp_path):
    with _archive(("C:/outside.txt", b"must not be written")) as archive:
        with pytest.raises(ValueError, match="absolute path"):
            ResourceDownloadService._safe_extract_zip(archive, str(tmp_path / "models"))


def test_safe_extract_zip_writes_only_valid_members(tmp_path):
    destination = tmp_path / "models"
    with _archive(("nested/model.bin", b"model"), ("nested/config.json", b"{}")) as archive:
        ResourceDownloadService._safe_extract_zip(archive, str(destination))
    assert (destination / "nested" / "model.bin").read_bytes() == b"model"
    assert (destination / "nested" / "config.json").read_text(encoding="utf-8") == "{}"


def test_english_voice_pack_accepts_archive_wrapper_directory(tmp_path, monkeypatch):
    models_root = tmp_path / "models"
    nested_root = models_root / "piper-en" / "piper-en"
    nested_root.mkdir(parents=True)
    model_path = nested_root / "en_US-amy-medium.onnx"
    model_path.write_bytes(b"onnx")
    (nested_root / "en_US-amy-medium.onnx.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        resource_download_module,
        "models_path",
        lambda *parts: str(models_root.joinpath(*parts)),
    )
    monkeypatch.setattr(resource_download_module, "bundle_root", lambda: str(tmp_path / "bundle"))
    service = ResourceDownloadService(str(tmp_path))
    voice = {
        "id": "en_US-amy-medium",
        "provider": "piper",
        "provider_voice": "models/piper-en/en_US-amy-medium.onnx",
        "language": "en",
    }
    monkeypatch.setattr(service, "_read_catalog", lambda: {"voices": [voice]})

    resolved_model, resolved_config = service._voice_local_paths(voice)
    assert Path(resolved_model) == model_path
    assert Path(resolved_config) == Path(f"{model_path}.json")
    assert service._usable_piper_voice_count("en") == 1
    assert service.is_resource_installed("voice:pack-en")


def test_locally_discovered_voice_is_valid_even_when_not_in_download_catalog(tmp_path, monkeypatch):
    models_root = tmp_path / "models"
    models_root.mkdir()
    model_path = models_root / "piper-en" / "en_US-lessac-medium.onnx"
    model_path.parent.mkdir()
    model_path.write_bytes(b"onnx")
    Path(f"{model_path}.json").write_text("{}", encoding="utf-8")
    preview_catalog = tmp_path / "voice_preview_catalog.json"
    preview_catalog.write_text(
        '{"voices":[{"id":"en_US-lessac-medium","provider":"piper",'
        '"provider_voice":"models/piper-en/en_US-lessac-medium.onnx","language":"en"}]}',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        resource_download_module,
        "models_path",
        lambda *parts: str(models_root.joinpath(*parts)),
    )
    monkeypatch.setattr(
        resource_download_module,
        "app_path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )
    service = ResourceDownloadService(str(tmp_path))
    monkeypatch.setattr(service, "_read_catalog", lambda: {"voices": []})
    monkeypatch.setattr(service, "_catalog_path", lambda: str(tmp_path / "voice_download_catalog.json"))

    assert service.is_resource_installed("voice:en_US-lessac-medium")
    assert service.validate_piper_voice_runtime("en_US-lessac-medium") == []

import os
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "ui"), str(ROOT / "app"), str(ROOT)]

from PySide6.QtWidgets import QApplication

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_resource_manager_renders_separation_and_all_categories(qapp, tmp_path, monkeypatch):
    from views.resource_manager import open_resource_manager
    import services.resource_download_service as rds

    workspace = str(tmp_path)
    orig_is_installed = rds.ResourceDownloadService.is_resource_installed
    def fake_is_installed(self, rid):
        if rid == "separation:uvr_mdx":
            return False
        return orig_is_installed(self, rid)

    monkeypatch.setattr(rds.ResourceDownloadService, "is_resource_installed", fake_is_installed)

    dialog = open_resource_manager(
        workspace_root=workspace,
        parent=None,
        focus_resource_id="separation:uvr_mdx",
        auto_start=False,
        show=False,
    )

    try:
        assert hasattr(dialog, "_resource_rows")
        assert "separation:uvr_mdx" in dialog._resource_rows

        uvr_row = dialog._resource_rows["separation:uvr_mdx"]
        assert uvr_row["card"] is not None
        assert uvr_row["card"].objectName() == "resourceCardFocused"
        assert uvr_row["install_btn"] is not None
        assert uvr_row["install_btn"].text() == "Install"
        assert uvr_row["install_btn"].isEnabled() is True

        # Check Diarization models are also populated
        assert "diarization:segmentation" in dialog._resource_rows
        assert "diarization:embedding" in dialog._resource_rows

        # Check Llama engine is populated
        assert "llama:engine" in dialog._resource_rows

        # Check CPU models are populated
        assert "sensevoice:model" in dialog._resource_rows

    finally:
        dialog.close()
        dialog.deleteLater()


def test_resource_manager_installed_state(qapp, tmp_path, monkeypatch):
    from views.resource_manager import open_resource_manager
    import services.resource_download_service as rds

    workspace = str(tmp_path)
    # Mock is_resource_installed to return True for separation:uvr_mdx
    orig_is_installed = rds.ResourceDownloadService.is_resource_installed
    def fake_is_installed(self, rid):
        if rid == "separation:uvr_mdx":
            return True
        return orig_is_installed(self, rid)

    monkeypatch.setattr(rds.ResourceDownloadService, "is_resource_installed", fake_is_installed)

    dialog = open_resource_manager(
        workspace_root=workspace,
        parent=None,
        show=False,
    )

    try:
        uvr_row = dialog._resource_rows["separation:uvr_mdx"]
        assert uvr_row["card"] is not None
        # When installed, status is "installed" and install_btn is None (per _add_card logic when auto_download_supported and status == installed)
        assert uvr_row["item"]["status"] == "installed"
        assert uvr_row["status_pill"].text() == "Ready"
    finally:
        dialog.close()
        dialog.deleteLater()



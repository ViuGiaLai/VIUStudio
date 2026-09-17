import importlib.metadata
import unittest
from unittest.mock import patch
from packaging.version import parse as parse_version

from app.services.resource_download_service import ResourceDownloadService


class ZeroTTSRuntimeTests(unittest.TestCase):
    def test_zerotts_installed_version_is_at_least_0_1_5(self):
        try:
            ver = importlib.metadata.version("zerotts")
        except Exception:
            self.fail("zerotts package is not installed.")
        self.assertGreaterEqual(
            parse_version(ver),
            parse_version("0.1.5"),
            f"zerotts version {ver} is below required 0.1.5"
        )

    def test_resource_installed_rejects_old_zerotts(self):
        service = ResourceDownloadService(".")
        with patch.object(service, "_zerotts_model_ready", return_value=True), \
             patch("importlib.util.find_spec", return_value=True):
            with patch("importlib.metadata.version", return_value="0.1.1"):
                self.assertFalse(service.is_resource_installed("tts:zerotts"))
            with patch("importlib.metadata.version", return_value="0.1.5"):
                self.assertTrue(service.is_resource_installed("tts:zerotts"))


if __name__ == "__main__":
    unittest.main()

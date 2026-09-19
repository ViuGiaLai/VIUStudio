"""Windows console-window regression tests for ``app/console_guard.py``.

The GUI and the local worker both run without a console.  Any console-mode
child process spawned without ``CREATE_NO_WINDOW`` therefore paints a new
window on screen, which is what users reported when a lazily imported library
touched ``platform`` (``cmd /c ver``) while the second subtitle was previewed.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "app"))

from console_guard import apply_console_guard, hidden_creationflags, is_console_guard_applied

windows_only = pytest.mark.skipif(os.name != "nt", reason="Windows console semantics only")


def test_hidden_creationflags_preserves_existing_flags():
    flags = hidden_creationflags(0)
    assert isinstance(flags, int)
    if os.name != "nt":
        assert flags == 0
        return
    assert flags & subprocess.CREATE_NO_WINDOW
    combined = hidden_creationflags(subprocess.CREATE_NEW_PROCESS_GROUP)
    assert combined & subprocess.CREATE_NO_WINDOW
    assert combined & subprocess.CREATE_NEW_PROCESS_GROUP


@windows_only
def test_apply_console_guard_patches_popen_once():
    apply_console_guard()
    patched = subprocess.Popen
    assert is_console_guard_applied()
    assert getattr(patched, "_viustudio_hidden", False) is True

    apply_console_guard()
    assert subprocess.Popen is patched, "second call must not stack patch subclasses"


@windows_only
def test_patched_popen_still_runs_child_processes():
    """The guard must change window visibility only, never process handling."""
    apply_console_guard()
    result = subprocess.run(
        [sys.executable, "-c", "print('guard-ok')"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0
    assert "guard-ok" in result.stdout


@windows_only
def test_platform_version_probe_never_spawns_after_guard():
    """``platform.win32_ver()`` used to run ``cmd /c ver`` on every call."""
    import platform

    apply_console_guard()
    first = platform.win32_ver()
    assert platform._viustudio_ver_cached is True

    original_popen = subprocess.Popen
    spawned = []

    class _NoSpawn(original_popen):  # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):
            spawned.append(args)
            raise AssertionError("platform must not spawn a process after the console guard")

    subprocess.Popen = _NoSpawn
    try:
        assert platform.win32_ver() == first
        assert platform.uname() == platform.uname()
        assert platform.system()
    finally:
        subprocess.Popen = original_popen

    assert spawned == []


def test_entrypoints_apply_guard_before_heavy_imports():
    """Qt (and the worker import chain) must never see the unguarded ``Popen``."""
    gui_source = (REPO_ROOT / "ui" / "gui.py").read_text(encoding="utf-8")
    guard_at = gui_source.index("apply_console_guard()")
    assert guard_at < gui_source.index("from PySide6"), "guard must run before Qt is imported"
    assert guard_at < gui_source.index("from main_window import"), "guard must run before the GUI import"

    worker_source = (REPO_ROOT / "app" / "remote_api_server.py").read_text(encoding="utf-8")
    assert worker_source.index("apply_console_guard()") < worker_source.index("from remote_api import")

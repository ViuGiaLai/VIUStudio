"""Keep child processes from flashing a console window while VIUStudio runs.

A windowed VIUStudio (``pythonw.exe`` in development, ``VIUStudio.exe`` in a
packaged build) owns no console.  Windows therefore creates a brand new console
window for every console-mode child process that does not ask for
``CREATE_NO_WINDOW``; the user sees a brief window titled ``python.exe`` /
``pyt...`` or ``cmd.exe`` appear in the middle of normal work.

Two sources keep producing those windows:

* third-party code (``pip``, ``huggingface_hub``, ``onnxruntime``, ...) that
  calls ``subprocess`` itself and never sees the project's
  ``subprocess_hidden_kwargs()`` helper, and
* ``platform._syscmd_ver()``, which literally starts ``cmd /c ver``.
  ``platform.uname()`` routes through it once per process, but
  ``platform.win32_ver()`` does *not* cache, so a single lazily imported library
  can start ``cmd.exe`` more than once at an unpredictable moment -- for
  example while the second subtitle is being previewed, which is why the window
  appeared only from the second subtitle onwards.

:func:`apply_console_guard` closes both: it patches ``subprocess.Popen``
process-wide and answers the ``platform`` version probe from a cache after the
first (already hidden) call.  Call it as early as possible, before importing Qt
or any other heavy package, so nothing can capture the original ``Popen`` or
warm ``platform`` first.
"""

import os

__all__ = [
    "apply_console_guard",
    "hidden_creationflags",
    "is_console_guard_applied",
]

# ``subprocess.CREATE_NO_WINDOW`` with a hard-coded fallback because the
# constant only exists on Windows.
_CREATE_NO_WINDOW = 0x08000000


def hidden_creationflags(creationflags: int = 0) -> int:
    """Return ``creationflags`` with ``CREATE_NO_WINDOW`` forced on.

    Existing flags (``CREATE_NEW_PROCESS_GROUP``, ``DETACHED_PROCESS``, ...) are
    preserved; only the no-window bit is added.
    """
    import subprocess

    flags = int(creationflags or 0)
    if os.name != "nt":
        return flags
    return flags | getattr(subprocess, "CREATE_NO_WINDOW", _CREATE_NO_WINDOW)


def is_console_guard_applied() -> bool:
    """Return ``True`` when ``subprocess.Popen`` is already guarded."""
    import subprocess

    return bool(getattr(subprocess.Popen, "_viustudio_hidden", False))


def _patch_subprocess_popen() -> None:
    """Force ``CREATE_NO_WINDOW`` onto every ``subprocess.Popen`` on Windows."""
    import subprocess

    if is_console_guard_applied():
        return

    original_popen = subprocess.Popen

    class _HiddenPopen(original_popen):  # type: ignore[misc, valid-type]
        """``subprocess.Popen`` that never opens a console window.

        Subclassing keeps ``isinstance(proc, subprocess.Popen)`` and
        ``subprocess.run``/``check_output`` working, because they look up
        ``Popen`` in the ``subprocess`` module namespace on every call.
        """

        _viustudio_hidden = True

        def __init__(self, args, *positional, **kwargs):
            kwargs["creationflags"] = hidden_creationflags(kwargs.get("creationflags"))
            super().__init__(args, *positional, **kwargs)

    subprocess.Popen = _HiddenPopen


def _cache_platform_version_probe() -> None:
    """Answer ``platform``'s Windows version probe without a second ``ver`` run.

    ``platform.win32_ver()`` calls ``platform._syscmd_ver()`` on *every*
    invocation and that helper shells out to ``cmd /c ver``.  Wrap it in a cache
    keyed by its arguments, then warm the callers that hold their own caches
    (``platform.uname()`` and ``platform.platform()``) so no later lazy import
    pays for another probe.
    """
    try:
        import platform
    except Exception:
        return

    if getattr(platform, "_viustudio_ver_cached", False):
        return

    original_syscmd_ver = getattr(platform, "_syscmd_ver", None)
    if not callable(original_syscmd_ver):
        return

    cache: dict = {}

    def _cached_syscmd_ver(system="", release="", version="", supported_platforms=("win32", "win16", "dos")):
        # The real helper is deterministic, so caching by (normalized)
        # arguments keeps every caller's result identical.
        key = (system, release, version, tuple(supported_platforms))
        if key not in cache:
            cache[key] = original_syscmd_ver(system, release, version, supported_platforms)
        return cache[key]

    platform._syscmd_ver = _cached_syscmd_ver  # type: ignore[attr-defined]
    platform._viustudio_ver_cached = True  # type: ignore[attr-defined]

    for probe in (platform.win32_ver, platform.uname):
        try:
            probe()
        except Exception:
            pass


def apply_console_guard() -> None:
    """Make it impossible for this process to paint a child console window.

    Idempotent and a no-op outside Windows, so it is safe to call from every
    entry point (the GUI, the local worker server, tests).
    """
    if os.name != "nt":
        return
    _patch_subprocess_popen()
    _cache_platform_version_probe()

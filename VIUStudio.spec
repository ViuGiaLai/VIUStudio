# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import os
import glob as _glob
import faster_whisper
import rapidocr
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

project_root = Path(SPECPATH).resolve() if "SPECPATH" in dir() else Path(__file__).resolve().parent
ui_root = project_root / "ui"
app_root = project_root / "app"

def _safe_data(src, dest):
    p = Path(src)
    return [(str(p), dest)] if p.exists() else []

datas = []
datas += _safe_data(project_root / "assets", "assets")
datas += _safe_data(project_root / "bin" / "ffmpeg", "bin/ffmpeg")
datas += _safe_data(project_root / "bin" / "mpv", "bin/mpv")
datas += _safe_data(project_root / "bin" / "UVR-MDX-NET-Inst_HQ_3.onnx", "bin")
datas += _safe_data(project_root / "bin" / "silero_vad.onnx", "bin")
datas += _safe_data(project_root / "app" / "voice_preview_catalog.json", "app")
datas += _safe_data(project_root / "app" / "voice_download_catalog.json", "app")
datas += _safe_data(project_root / "app" / "voice_preview_catalog.release.json", "app")
datas += _safe_data(project_root / "app" / "translation" / "prompts", "app/translation/prompts")
datas += _safe_data(project_root / "models" / "piper", "models/piper")
datas += _safe_data(project_root / "models" / "pyannote", "models/pyannote")
datas += _safe_data(project_root / "models" / "sensevoice" / "model.int8.onnx", "models/sensevoice")
datas += _safe_data(project_root / "models" / "sensevoice" / "tokens.txt", "models/sensevoice")
datas += _safe_data(project_root / "bin" / "cuda12_fw" / "README.txt", "bin/cuda12_fw")
datas += _safe_data(project_root / "models" / "faster_whisper" / "README.txt", "models/faster_whisper")
datas += _safe_data(project_root / "app" / "utils" / "voice_preview_utils.py", "utils")
datas += _safe_data(project_root / ".env_example", ".")
datas += _safe_data(os.path.join(os.path.dirname(faster_whisper.__file__), "assets"), "faster_whisper/assets")
datas += _safe_data(os.path.join(os.path.dirname(rapidocr.__file__), "models"), "rapidocr/models")
datas += _safe_data(os.path.join(os.path.dirname(rapidocr.__file__), "config.yaml"), "rapidocr")
datas += _safe_data(os.path.join(os.path.dirname(rapidocr.__file__), "default_models.yaml"), "rapidocr")
datas += _safe_data(project_root / "ui" / "views" / "editor", "views/editor")
datas += collect_data_files("piper")

# RapidOCR selects its ONNX implementation through runtime configuration.
# Listing only ``rapidocr`` misses these dynamically imported modules in a
# frozen worker and can make a bundled OCR install look intermittently
# unavailable. Collect the package's submodules, while leaving the unused
# Torch backend excluded by the existing package exclusions below.
rapidocr_hiddenimports = collect_submodules("rapidocr")

# Exclude heavy packages we don't use
excludes = [
    "torch",
    "torchaudio",
    "torchvision",
    "demucs",
    # Local AI/llama.cpp was removed from the application. Keep it out of
    # packaged builds even if an installed dependency exposes it indirectly.
    "llama_cpp",
    "llama_cpp.*",
    "matplotlib",

    "comtypes",
    "phonenumbers",
    "uvicorn",
    "msgpack",
    "orjson",
    "safetensors",
    "xxhash",
    "brotli",
    "contourpy",
    "kiwisolver",
    "packaging",
    "cryptography",
    "psutil",
    "websockets",
]


a = Analysis(
    [str(ui_root / "gui.py")],
    pathex=[str(project_root), str(ui_root), str(app_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "gui",
        "main_window",
        "PySide6.QtSvg",
        "PySide6.QtSvgWidgets",
        "mpv",
        "remote_api",
        "remote_api_server",
        "services",
        "services.project_service",
        "services.gui_project_bridge",
        "services.voice_catalog_service",
        "services.resource_download_service",
        "services.engine_runtime",
        "services.gpu_stage_scheduler",
        "services.workflow_runtime",
        "services.segment_service",
        "services.chunking_service",
        "services.asr_merge_service",
        # PrepareWorkflow imports this through services.__getattr__. Because
        # that import is dynamic, PyInstaller cannot discover the concrete
        # module unless it is listed explicitly. Missing it makes the frozen
        # /v1/prepare worker fail at runtime with ModuleNotFoundError.
        "services.asr_ocr_reconciliation_service",
        "services.asr_vocalization_filter_service",
        "services.segment_regroup_service",
        # SpeakerDiarizationService is resolved lazily through services.__getattr__.
        # Include its concrete module so the frozen worker can import it.
        "services.speaker_diarization_service",
        "services.subtitle_exchange_service",
        # Dynamically loaded adapters (EngineRuntime uses importlib)
        "engines.ffmpeg_adapter",
        "engines.preview_adapter",
        "engines.subtitle_adapter",
        "engines.audio_mix_adapter",
        "engines.whisper_adapter",
        "engines.sensevoice_adapter",
        "engines.translator_adapter",
        "engines.tts_adapter",
        "engines.demucs_adapter",
        "engines.ocr_adapter",
        # Lazy-loaded translation providers
        "translation.providers.gemini_polisher",
        "translation.providers.google_web_translator",
        # Lazy-loaded workflows
        "workflows.prepare_workflow",
        "workflows.voice_workflow",
        "workflows.export_workflow",
        # Required for timeline + audio
        "numpy",
        "pydub",
        "scipy",
        "librosa",
        "soundfile",
        "onnxruntime",
        "openai",
        "audio_mixer",
        "vocal_processor",
        "whisper_processor",
        "faster_whisper",
        "ctranslate2",
        "edge_tts",
        "dotenv",
        "huggingface_hub",
        "tts_processor",
        "preview_processor",
        "video_processor",
        "subtitle_builder",
        "runtime_paths",
        # Explicitly include the namespace-package module imported by the
        # timeline at runtime.  PyInstaller does not reliably discover
        # modules beneath the project-level ``app`` namespace automatically.
        "app.runtime_paths",
        "runtime_profile",
        # OCR engine
        "rapidocr",
        "sherpa_onnx",
        "shapely",
        "cv2",
        "omegaconf",
        "pyclipper",
    ] + rapidocr_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

# Force-exclude heavy packages from final bundle
_EXCLUDE_PREFIXES = ("torch", "torchaudio", "torchvision", "demucs")
a.pure = [m for m in a.pure if not str(m[0]).replace("\\", "/").split("/")[0].split(".")[0] in _EXCLUDE_PREFIXES]
a.binaries = [m for m in a.binaries if not str(m[0]).replace("\\", "/").split("/")[0].split(".")[0] in _EXCLUDE_PREFIXES]
# PyInstaller can collect the same ONNX Runtime CUDA provider under a nested
# invalid destination as well as the normal capi directory. Keep only the
# normal provider copy; CUDA runtime DLLs are installed on demand by the
# Resource Manager, not bundled into the application.
a.binaries = [m for m in a.binaries if str(m[0]).replace("\\", "/") != "onnxruntime/capi/onnxruntime/capi/onnxruntime_providers_cuda.dll"]

# Do not silently turn the installer into a CUDA runtime installer. Native
# dependency analysis of CTranslate2 can discover these DLLs from the CUDA
# Toolkit installed on the build machine and place duplicate copies in
# ``_internal``. GPU mode intentionally resolves them from the separately
# downloadable ``bin/cuda12_fw`` resource directory instead. Keeping this
# exclusion explicit makes CPU-only installs small and keeps the Resource
# Manager as the single source for the GPU runtime.
_CUDA_RUNTIME_DLL_NAMES = {
    "cublas64_12.dll",
    "cublaslt64_12.dll",
    "cudart64_12.dll",
    "cufft64_11.dll",
}
a.binaries = [
    m for m in a.binaries
    if Path(str(m[0])).name.lower() not in _CUDA_RUNTIME_DLL_NAMES
]

# Qt 6 on Windows links against the system ``icuuc.dll`` API.  When the
# build runs from the Codex desktop environment, PyInstaller can accidentally
# collect Poppler's private ICU 78 DLLs from PATH.  Those DLLs export only
# version-suffixed symbols (for example ``ucnv_open_78``), while Qt imports the
# normal Windows symbols (``ucnv_open``), causing QtCore to fail at startup
# with WinError 127.  Never ship that unrelated private ICU beside the app.
_FOREIGN_ICU_DLL_NAMES = {"icuuc.dll", "icudt78.dll"}
a.binaries = [
    m for m in a.binaries
    if Path(str(m[0])).name.lower() not in _FOREIGN_ICU_DLL_NAMES
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VIUStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_dir=str(project_root / "upx"),
    # Keep the console build as the debugging/default configuration.  The
    # windowed production spec sets VIUSTUDIO_WINDOWED_BUILD=1 before executing
    # this file.
    console=os.environ.get("VIUSTUDIO_WINDOWED_BUILD", "0").strip() != "1",
    icon=str(project_root / "assets" / "viustudio.ico"),
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_dir=str(project_root / "upx"),
    upx_exclude=["onnxruntime*", "ffmpeg*", "ffprobe*", "mpv*", "cudnn*", "cublas*", "cudart*", "libomp*"],
    name="VIUStudio",
)

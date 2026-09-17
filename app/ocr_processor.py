import os
import re
import subprocess
import time
import unicodedata
from difflib import SequenceMatcher

import cv2
import numpy as np

from runtime_paths import bin_path, subprocess_text_kwargs

_OCR_ENGINE = None
_OCR_ENGINE_LOCK = None


class _ReusableDetectorPreProcess:
    """RapidOCR detector preprocessing with reusable numeric work buffers.

    The arithmetic intentionally mirrors RapidOCR's DetPreProcess: the input
    is converted/scaled in float32, then mean/std operations occur in float64
    because RapidOCR's mean/std arrays are float64, and the final NCHW tensor
    is float32.  Only temporary allocations are changed; tensor shape, dtype,
    channel order, and numerical values remain equivalent.
    """

    def __init__(self, target, shared_buffers):
        self._target = target
        self._shared_buffers = shared_buffers

    def __getattr__(self, name):
        return getattr(self._target, name)

    def __call__(self, image):
        resized = self._target.resize(image)
        if resized is None:
            return None

        shape = tuple(resized.shape)
        buffers = self._shared_buffers.get(shape)
        if buffers is None:
            height, width, channels = shape
            buffers = {
                "float32": np.empty(shape, dtype=np.float32),
                "float64": np.empty(shape, dtype=np.float64),
                "output": np.empty((1, channels, height, width), dtype=np.float32),
            }
            self._shared_buffers[shape] = buffers

        float32_buffer = buffers["float32"]
        float64_buffer = buffers["float64"]
        output = buffers["output"]

        np.copyto(float32_buffer, resized, casting="unsafe")
        float32_buffer *= self._target.scale
        np.copyto(float64_buffer, float32_buffer, casting="unsafe")
        float64_buffer -= self._target.mean
        float64_buffer /= self._target.std
        np.copyto(output[0], float64_buffer.transpose((2, 0, 1)), casting="unsafe")
        return output


def _enable_reusable_detector_preprocess(engine):
    """Install the validated detector-only optimization on one OCR engine."""
    detector = getattr(engine, "text_det", None)
    if detector is None or getattr(detector, "_viustudio_reusable_preprocess", False):
        return engine
    original_get_preprocess = detector.get_preprocess
    shared_buffers = {}

    def get_preprocess(max_side):
        target = original_get_preprocess(max_side)
        return _ReusableDetectorPreProcess(target, shared_buffers)

    detector.get_preprocess = get_preprocess
    detector._viustudio_reusable_preprocess = True
    return engine

MAX_CROP_WIDTH = 720
EMPTY_TOLERANCE = 2
EXACT_HASH_THRESHOLD = 5.0
_OCR_HANDLE_RE = re.compile(r"@\s*[A-Za-z0-9_\-\u3400-\u9fff]{1,24}")
_OCR_WATERMARK_PATTERNS = [
    re.compile(r"[\u3400-\u9fff]{1,6}漫(?:剧|居|刷)"),
    re.compile(r"专店"),
]


def _onnx_cuda_provider_ready() -> tuple[bool, str]:
    """Return whether ONNX Runtime's CUDA provider can actually load.

    ``get_available_providers`` only reports that the provider was compiled
    into the installed package.  It does not verify dependent CUDA DLLs.
    RapidOCR otherwise tries every model with CUDA, emits repeated loader
    errors, then silently runs each one on CPU.
    """
    try:
        import onnxruntime
        if "CUDAExecutionProvider" not in onnxruntime.get_available_providers():
            return False, "CUDAExecutionProvider is not installed"
        if os.name == "nt":
            import ctypes
            provider_dll = os.path.join(
                os.path.dirname(onnxruntime.__file__), "capi", "onnxruntime_providers_cuda.dll"
            )
            if not os.path.isfile(provider_dll):
                return False, "onnxruntime CUDA provider DLL is not installed"
            try:
                ctypes.WinDLL(provider_dll)
            except OSError as exc:
                return False, str(exc)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def _get_lock():
    global _OCR_ENGINE_LOCK
    if _OCR_ENGINE_LOCK is None:
        import threading
        _OCR_ENGINE_LOCK = threading.Lock()
    return _OCR_ENGINE_LOCK


def _ffmpeg_path():
    return os.path.join(bin_path("ffmpeg"), "ffmpeg.exe")


# RapidOCR (pip ``rapidocr``) resolves each component model from the files it
# finds in ``model_root_dir``, so accuracy is decided by which ONNX files are
# bundled next to the package. Every entry below is a supported preset in the
# same installed rapidocr version: dropping the two files into the models
# directory is enough - no YAML edits and no network download at runtime.
# ``best`` = PP-OCRv6 medium is the highest tier in the v6 family and reads
# stylized/faded burned-in subtitles noticeably better than the default small.
_OCR_MODEL_CATALOG = {
    # profile: (det file, rec file, ocr_version, model_type, display label)
    "fast": (
        "PP-OCRv6_det_tiny.onnx",
        "PP-OCRv6_rec_tiny.onnx",
        "PP-OCRv6",
        "tiny",
        "PP-OCRv6 tiny",
    ),
    "balanced": (
        "PP-OCRv6_det_small.onnx",
        "PP-OCRv6_rec_small.onnx",
        "PP-OCRv6",
        "small",
        "PP-OCRv6 small",
    ),
    "best": (
        "PP-OCRv6_det_medium.onnx",
        "PP-OCRv6_rec_medium.onnx",
        "PP-OCRv6",
        "medium",
        "PP-OCRv6 medium",
    ),
    "v4": (
        "ch_PP-OCRv4_det_mobile.onnx",
        "ch_PP-OCRv4_rec_mobile.onnx",
        "PP-OCRv4",
        "mobile",
        "PP-OCRv4 mobile",
    ),
}
_OCR_PROFILE_FALLBACKS = {
    "fast": ("fast", "balanced", "v4"),
    "balanced": ("balanced", "v4"),
    "best": ("best", "balanced", "v4"),
    "v4": ("v4",),
}


def _requested_ocr_quality() -> str:
    quality = str(os.getenv("VIUSTUDIO_OCR_QUALITY") or "balanced").strip().lower()
    if quality not in _OCR_PROFILE_FALLBACKS:
        print(
            "[OCR] Unknown VIUSTUDIO_OCR_QUALITY "
            f"{quality!r}; using 'balanced' (PP-OCRv6 small)."
        )
        quality = "balanced"
    return quality


def _resolve_ocr_profile(models_dir: str):
    """Pick the best model set present for the requested quality level.

    Returns ``(requested, selected_profile_key, det_file, rec_file,
    ocr_version, model_type, label)``. ``selected_profile_key`` is None when
    no supported pair exists on disk; the caller must then fail with a clear
    message instead of letting rapidocr attempt a silent network download.
    """
    requested = _requested_ocr_quality()
    if not models_dir or not os.path.isdir(models_dir):
        return requested, None, None, None, None, None, ""
    for key in _OCR_PROFILE_FALLBACKS[requested]:
        det_file, rec_file, ocr_version, model_type, label = _OCR_MODEL_CATALOG[key]
        if os.path.isfile(os.path.join(models_dir, det_file)) and os.path.isfile(
            os.path.join(models_dir, rec_file)
        ):
            return requested, key, det_file, rec_file, ocr_version, model_type, label
    return requested, None, None, None, None, None, ""


def _find_ocr_models_dir() -> str:
    """Locate the rapidocr models directory across source and PyInstaller layouts."""
    try:
        import rapidocr
        primary = os.path.join(os.path.dirname(rapidocr.__file__), "models")
    except Exception:
        primary = ""
    # PyInstaller one-dir builds place collected data below _internal,
    # while source installs keep it beside rapidocr.__file__. Resolve both.
    import sys
    candidates = [primary]
    meipass = getattr(sys, "_MEIPASS", "") or ""
    if meipass:
        candidates.append(os.path.join(meipass, "rapidocr", "models"))
    try:
        from runtime_paths import bundle_root
        candidates.append(os.path.join(bundle_root(), "rapidocr", "models"))
    except Exception:
        pass
    return next((path for path in candidates if path and os.path.isdir(path)), "")


def ocr_quality_signature() -> str:
    """Stable key of the active OCR quality profile for cache invalidation.

    Changing ``VIUSTUDIO_OCR_QUALITY`` (or installing/removing model files)
    changes the returned key, so transcript and OCR-reference caches are
    invalidated and the new profile is actually used on the next run.
    """
    requested = _requested_ocr_quality()
    _, selected_key, *_rest = _resolve_ocr_profile(_find_ocr_models_dir())
    return f"{requested}:{selected_key or 'none'}"


def _load_ocr_engine():
    global _OCR_ENGINE
    with _get_lock():
        if _OCR_ENGINE is not None:
            return _OCR_ENGINE

        from runtime_paths import join_root
        cuda_bin = join_root("bin", "cuda12_fw")
        if os.path.isdir(cuda_bin):
            if hasattr(os, "add_dll_directory"):
                try:
                    os.add_dll_directory(cuda_bin)
                except Exception:
                    pass
            os.environ["PATH"] = cuda_bin + os.pathsep + os.environ.get("PATH", "")

        models_dir = _find_ocr_models_dir()
        print(f"[OCR] Model directory: {models_dir or '<not found>'}")

        requested, selected_key, det_file, rec_file, ocr_version, model_type, label = (
            _resolve_ocr_profile(models_dir)
        )
        classifier = "ch_ppocr_mobile_v2.0_cls_mobile.onnx"
        classifier_ready = bool(models_dir and os.path.isfile(os.path.join(models_dir, classifier)))
        if selected_key is None or not classifier_ready:
            expected = " or ".join(
                " + ".join((entry[0], entry[1])) for entry in _OCR_MODEL_CATALOG.values()
            )
            raise RuntimeError(
                "OCR models not found inside the rapidocr package. "
                "Reinstall the rapidocr package or open Settings → Manage Resources for hints.\n\n"
                f"Expected detector/recognizer: {expected}; classifier: {classifier}\n"
                f"Looked in: {models_dir or 'rapidocr package directory'}"
            )
        if selected_key != requested:
            print(
                "[OCR] Quality profile '"
                f"{requested}' requested but its model files are absent; using {label} "
                f"({', '.join(_OCR_PROFILE_FALLBACKS[requested])})."
            )
        else:
            print(f"[OCR] Quality profile: {requested} -> {label}.")

        from rapidocr import RapidOCR
        # Always pass the resolved directory explicitly.  RapidOCR otherwise
        # derives it from its installed-package path, which is unreliable in
        # a PyInstaller bundle and can surface as a generic "No such file or
        # directory" error in the OCR Translator worker.
        base_params = {
            "Global.log_level": "error",
            "Global.model_root_dir": models_dir,
        }
        # rapidocr's config.yaml defaults to PP-OCRv6/small, which matches the
        # ``balanced`` profile. Only override the resolver keys when another
        # tier (tiny/medium/PP-OCRv4) was actually selected, and always pass
        # files that were verified present so init never downloads.
        model_params = dict(base_params)
        if (ocr_version, model_type) != ("PP-OCRv6", "small"):
            from rapidocr.utils.typings import ModelType, OCRVersion

            model_params["Det.ocr_version"] = OCRVersion(ocr_version)
            model_params["Det.model_type"] = ModelType(model_type)
            model_params["Rec.ocr_version"] = OCRVersion(ocr_version)
            model_params["Rec.model_type"] = ModelType(model_type)
        cuda_ready, cuda_reason = _onnx_cuda_provider_ready()
        if cuda_ready:
            try:
                _OCR_ENGINE = RapidOCR(params={
                    **model_params,
                    "EngineConfig.onnxruntime.use_cuda": True,
                })
                print(f"[OCR] RapidOCR engine loaded ({det_file}, CUDA GPU)")
            except Exception as exc:
                # This covers a genuine RapidOCR initialization failure after
                # the provider itself loaded successfully.
                _OCR_ENGINE = RapidOCR(params=model_params)
                print(f"[OCR] CUDA initialization failed; using CPU: {exc}")
        else:
            _OCR_ENGINE = RapidOCR(params=model_params)
            detail = f" ({cuda_reason})" if cuda_reason else ""
            print(f"[OCR] CUDA unavailable; using CPU OCR{detail}")
        _enable_reusable_detector_preprocess(_OCR_ENGINE)
        return _OCR_ENGINE


def _open_video(video_path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"[OCR] Cannot open video: {video_path}")
    return cap


def crop_subtitle_region(image, region="bottom"):
    h, w = image.shape[:2]
    rect_str = os.getenv("OCR_SUBTITLE_RECT", "")
    if rect_str:
        try:
            parts = [float(x) for x in rect_str.split(",")]
            if len(parts) == 4:
                rx, ry, rw_val, rh = parts
                x1 = int(rx * w)
                y1 = int(ry * h)
                x2 = int((rx + rw_val) * w)
                y2 = int((ry + rh) * h)
                return image[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
        except Exception:
            pass
    effective_region = (os.getenv("OCR_SUBTITLE_REGION") or region or "bottom").strip().lower()
    if effective_region == "bottom":
        ratio = float(os.getenv("OCR_CROP_RATIO", "0.28"))
        top = int(h * (1.0 - ratio))
        return image[top:h, 0:w]
    elif effective_region == "top":
        ratio = float(os.getenv("OCR_CROP_RATIO", "0.28"))
        return image[0:int(h * ratio), 0:w]
    else:
        return image


def preprocess_for_ocr(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
    return cv2.cvtColor(clahe.apply(gray), cv2.COLOR_GRAY2BGR)


def _crop_hash(image):
    small = cv2.resize(image, (64, 64), interpolation=cv2.INTER_NEAREST)
    return small.astype(np.float32).mean(axis=(0, 1))


def _hamming_distance(h1, h2):
    return float(np.sum(np.abs(h1.astype(np.float32) - h2.astype(np.float32))))


def _sanitize_ocr_line(text: str) -> str:
    cleaned = " ".join(str(text or "").replace("\n", " ").split()).strip()
    if not cleaned:
        return ""
    cleaned = _OCR_HANDLE_RE.sub(" ", cleaned)
    for pattern in _OCR_WATERMARK_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    cleaned = " ".join(cleaned.split()).strip(" -_.,;:!?|/\\[]{}()<>'\"`~")
    if not cleaned:
        return ""

    # Preserve short and ASCII text. "OK", names, numbers, single-word
    # captions and one-character interjections can all be valid on-screen
    # subtitles. Watermark/handle patterns above remain the only explicit
    # OCR text suppression.
    return cleaned


def _is_blank_region(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    if float(lap.var()) < 30.0:
        return True
    bright_ratio = float(np.sum(gray > 180)) / gray.size
    # Small, single-character white subtitles can occupy only about 0.1% of a
    # bottom crop.  The previous 0.2% cutoff labelled those valid subtitle
    # frames as blank before RapidOCR was allowed to inspect them.
    if bright_ratio > 0.0005:
        return False
    return True


def _subtitle_lines_from_result(result, image_shape) -> list[str]:
    """Score and rank OCR candidate boxes based on subtitle geometry.

    A bottom crop can contain vertical title cards, corner channel logos, or
    watermarks. Score candidates based on:
    1. Aspect ratio: horizontal text (width >= height) gets strong preference;
       tall vertical boxes (height > width * 1.2) are rejected.
    2. Vertical position: lower region of the crop gets higher score.
    3. Horizontal placement: centered subtitles get bonus score, but valid
       subtitles shifted slightly left/right are still accepted if horizontal.
    4. Text structure: complete dialogue lines vs tiny artifacts.
    """
    raw_texts = list(getattr(result, "txts", None) or [])
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) != len(raw_texts):
        return [
            cleaned for cleaned in (_sanitize_ocr_line(value) for value in raw_texts)
            if cleaned
        ]

    height, width = image_shape[:2]
    candidates = []
    for index, (raw_text, raw_box) in enumerate(zip(raw_texts, boxes)):
        cleaned = _sanitize_ocr_line(raw_text)
        if not cleaned:
            continue
        points = np.asarray(raw_box, dtype=np.float32).reshape(-1, 2)
        if points.size == 0:
            continue
        left, right = float(points[:, 0].min()), float(points[:, 0].max())
        top, bottom = float(points[:, 1].min()), float(points[:, 1].max())
        box_width = max(1.0, right - left)
        box_height = max(1.0, bottom - top)
        center_x = (left + right) * 0.5
        center_y = (top + bottom) * 0.5

        # Aspect ratio filter: dialogue subtitles are horizontal
        aspect_ratio = box_width / box_height
        if aspect_ratio < 0.85:
            # Explicitly vertical text box (e.g. vertical title card / column)
            continue

        # Vertical position filter: discard upper noise outside subtitle zone.
        # Threshold of 0.08 preserves the upper line of 2-line burned subtitles.
        norm_y = center_y / max(1.0, float(height))
        if norm_y < 0.08:
            continue

        # Horizontal edge filter: dialogue subtitles are horizontally centered.
        # Discard small corner marks (watermarks, logos, channel IDs, episode markers)
        normalized_center_x = center_x / max(1.0, float(width))
        if (normalized_center_x < 0.10 or normalized_center_x > 0.90) and (box_width / float(width)) < 0.35:
            continue

        # Geometric score calculation
        score = 0.0
        # Horizontal aspect ratio bonus
        score += min(3.0, aspect_ratio) * 1.5
        # Vertical placement bonus (lower in the subtitle band is better)
        score += norm_y * 2.0
        # Centering bonus (subtitles tend to be near center x=0.5, but allow spread)
        norm_x_offset = abs(center_x / max(1.0, float(width)) - 0.5)
        score += max(0.0, 1.0 - norm_x_offset * 2.0)
        # Length bonus (complete dialogue line vs tiny noise)
        key_len = len(_ocr_consensus_key(cleaned))
        if key_len <= 1 and not 0.20 <= normalized_center_x <= 0.80:
            # A lone glyph in a far corner is almost always a watermark/title
            # marker, not the horizontally centred dialogue subtitle.
            continue
        score += min(5.0, float(key_len)) * 0.5

        candidates.append((score, top, left, index, cleaned))

    if not candidates:
        return []
    valid_candidates = [c for c in candidates if c[0] >= 2.0]
    if not valid_candidates:
        valid_candidates = candidates
    valid_candidates.sort(key=lambda value: (value[1], value[2], value[3]))
    return [value[-1] for value in valid_candidates]


def _locate_bright_subtitle_line(image):
    """Locate a likely bright, horizontally centred subtitle without OCR detection.

    Most burned-in dialogue subtitles use bright glyphs with a dark outline.
    Locating that line with OpenCV lets RapidOCR run its recognizer directly
    (milliseconds) instead of its expensive detector on every checkpoint.
    Non-bright or unusual styles return ``None`` and use the full detector.
    """
    if image is None or image.size == 0:
        return None
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mask = cv2.inRange(gray, 205, 255)
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (17, 3)),
    )
    contours, _hierarchy = cv2.findContours(
        mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    boxes = []
    for contour in contours:
        x, y, box_width, box_height = cv2.boundingRect(contour)
        center_y = y + box_height * 0.5
        if (
            cv2.contourArea(contour) > 8
            and center_y >= height * 0.45
            and x + box_width >= width * 0.15
            and x <= width * 0.85
            and box_height <= box_width * 1.5
        ):
            boxes.append((x, y, box_width, box_height))
    if not boxes:
        return None

    seed = max(
        boxes,
        key=lambda box: box[2] * 2.0 - abs((box[0] + box[2] * 0.5) - width * 0.5),
    )
    seed_center_y = seed[1] + seed[3] * 0.5
    same_line = [
        box for box in boxes
        if abs((box[1] + box[3] * 0.5) - seed_center_y)
        <= max(seed[3], box[3]) * 0.45
    ]
    left = max(0, min(box[0] for box in same_line) - 12)
    top = max(0, min(box[1] for box in same_line) - 8)
    right = min(width, max(box[0] + box[2] for box in same_line) + 12)
    bottom = min(height, max(box[1] + box[3] for box in same_line) + 8)
    if right - left < 12 or bottom - top < 10:
        return None
    return image[top:bottom, left:right]


def _confident_recognition_texts(result, minimum_score: float = 0.72) -> list[str]:
    raw_texts = list(getattr(result, "txts", None) or [])
    raw_scores = list(getattr(result, "scores", None) or [])
    texts = []
    for index, raw_text in enumerate(raw_texts):
        score = float(raw_scores[index]) if index < len(raw_scores) else 0.0
        cleaned = _sanitize_ocr_line(raw_text)
        if cleaned and score >= minimum_score:
            texts.append(cleaned)
    return texts


def ocr_frame(engine, image, profiling=None):
    """OCR one frame and optionally accumulate lightweight aggregate timings."""
    preprocess_started = time.perf_counter()
    h, w = image.shape[:2]
    if w > MAX_CROP_WIDTH:
        scale = MAX_CROP_WIDTH / w
        new_w = MAX_CROP_WIDTH
        new_h = int(h * scale)
        image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    if profiling is not None:
        profiling["crop_preprocess"] += time.perf_counter() - preprocess_started

    inference_started = time.perf_counter()
    texts = []
    fast_region = _locate_bright_subtitle_line(image)
    if fast_region is not None:
        fast_result = engine(
            fast_region,
            use_det=False,
            use_cls=False,
            use_rec=True,
            text_score=0.6,
        )
        texts = _confident_recognition_texts(fast_result)
    if not texts:
        result = engine(image, use_cls=False, text_score=0.6, box_thresh=0.5)
        texts = _subtitle_lines_from_result(result, image.shape)
    inference_elapsed = time.perf_counter() - inference_started
    if profiling is not None:
        profiling["ocr_inference"] += inference_elapsed
        profiling["ocr_inference_samples"].append(inference_elapsed)

    postprocess_started = time.perf_counter()
    if profiling is not None:
        profiling["postprocess"] += time.perf_counter() - postprocess_started
    return texts


def extract_ocr_text_from_video_region(video_path, position_seconds, normalized_rect):
    """Read text from one explicitly requested video-frame region.

    This is intentionally separate from ``transcribe_video_ocr``: it never
    creates subtitle segments, reads no OCR environment settings, and only
    performs work when the caller explicitly requests a capture.
    """
    if not video_path or not os.path.isfile(video_path):
        raise RuntimeError("Please load a video before capturing text.")
    try:
        rx, ry, rw, rh = [float(value) for value in normalized_rect]
    except (TypeError, ValueError):
        raise RuntimeError("The OCR Translator selection is invalid.")
    rx, ry = max(0.0, min(1.0, rx)), max(0.0, min(1.0, ry))
    rw, rh = max(0.001, min(1.0 - rx, rw)), max(0.001, min(1.0 - ry, rh))

    cap = _open_video(video_path)
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, float(position_seconds)) * 1000.0)
        ok, frame = cap.read()
    finally:
        cap.release()
    if not ok or frame is None:
        raise RuntimeError("Could not capture the current video frame.")

    height, width = frame.shape[:2]
    left, top = int(rx * width), int(ry * height)
    right, bottom = int((rx + rw) * width), int((ry + rh) * height)
    crop = frame[max(0, top):min(height, bottom), max(0, left):min(width, right)]
    if crop.size == 0:
        raise RuntimeError("The OCR Translator selection is outside the video frame.")
    if crop.shape[1] > MAX_CROP_WIDTH:
        scale = MAX_CROP_WIDTH / float(crop.shape[1])
        crop = cv2.resize(crop, (MAX_CROP_WIDTH, max(1, int(crop.shape[0] * scale))), interpolation=cv2.INTER_LINEAR)

    engine = _load_ocr_engine()
    result = engine(crop, use_cls=False, text_score=0.45, box_thresh=0.35)
    # Unlike subtitle OCR, retain short labels and UI text: this utility is
    # meant for any visible text rather than only spoken subtitles.
    lines = [" ".join(str(value or "").split()) for value in (result.txts or [])]
    return "\n".join(line for line in lines if line).strip()


def _representative_ocr_times(start_seconds: float, end_seconds: float) -> list[float]:
    """Return two nearby frames where the cue's first subtitle is expected.

    SenseVoice has no word timestamps. A VAD region can remain open for
    several seconds after a short utterance, so midpoint sampling can land
    after its burned-in subtitle has disappeared. For long VAD cues sample
    just after speech onset; short cues continue to use their midpoint.
    """
    start = max(0.0, float(start_seconds or 0.0))
    end = max(start, float(end_seconds or start))
    midpoint = (start + end) * 0.5
    duration = end - start
    if duration <= 0.04:
        return [midpoint]
    if duration > 2.0:
        first = min(end, start + min(0.50, max(0.24, duration * 0.10)))
        second = min(end, first + 0.24)
        if second - first >= 0.02:
            return [first, second]
    offset = min(0.12, max(0.04, duration * 0.12))
    first = max(start, midpoint - offset)
    second = min(end, midpoint + offset)
    if second - first < 0.02:
        return [midpoint]
    return [first, second]


def _representative_ocr_pairs(
    start_seconds: float,
    end_seconds: float,
    *,
    scan_mode: str = "single",
) -> list[list[float]]:
    """Return one verifier pair or adaptive checkpoints across a long cue.

    Four fixed checkpoints can miss a short speaker turn inside a five-second
    VAD region. Sequence mode therefore keeps adjacent checkpoints at most
    0.70 seconds apart, which is short enough to observe normal burned-in
    subtitle changes before TTS cue generation.
    """
    start = max(0.0, float(start_seconds or 0.0))
    end = max(start, float(end_seconds or start))
    if scan_mode != "sequence" or end - start < 1.0:
        return [_representative_ocr_times(start, end)]
    duration = end - start
    max_checkpoint_gap = 0.55
    checkpoint_count = max(4, int(np.ceil(duration / max_checkpoint_gap)) + 1)
    # VAD/SenseVoice cues are normally capped at five seconds. Keep a hard
    # ceiling for malformed input so one cue cannot monopolize CPU OCR.
    checkpoint_count = min(10, checkpoint_count)
    first_center = min(end, start + 0.08)
    last_center = max(first_center, end - 0.20)
    centers = np.linspace(first_center, last_center, checkpoint_count).tolist()
    pairs = []
    for center in centers:
        offset = 0.035
        first = max(start, center - offset)
        second = min(end, center + offset)
        pairs.append([first, second] if second - first >= 0.02 else [center])
    return pairs


def _ocr_consensus_key(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or "")).casefold()
    return "".join(char for char in normalized if char.isalpha() or char.isdigit())


def _two_frame_ocr_consensus(frame_texts: list[str], expected_frames: int = 2) -> str:
    """Accept OCR only when every requested representative frame agrees."""
    values = [_sanitize_ocr_line(value) for value in (frame_texts or [])]
    values = [value for value in values if value]
    if len(values) < max(1, int(expected_frames or 1)):
        return ""
    keys = [_ocr_consensus_key(value) for value in values]
    if not keys[0] or any(key != keys[0] for key in keys[1:]):
        return ""
    return max(values, key=len)


def _is_potential_ocr_correction(asr_text: str, ocr_text: str) -> bool:
    """Return whether frame 1 is plausible dialogue to confirm with frame 2."""
    ocr_key = _ocr_consensus_key(ocr_text)
    if not ocr_key or len(ocr_key) < 2 or len(ocr_key) > 60:
        return False
    asr_key = _ocr_consensus_key(asr_text)
    if not asr_key:
        return True
    if asr_key in ocr_key or ocr_key in asr_key:
        return True
    # Allow multi-character homophone and dialogue verification as long as lengths are comparable
    ratio = len(ocr_key) / max(1, len(asr_key))
    if 0.35 <= ratio <= 2.5:
        return True
    return SequenceMatcher(None, asr_key, ocr_key).ratio() >= 0.2


def detect_hardsub_presence(
    video_path: str,
    speech_segments: list[dict] | None = None,
    *,
    region: str = "bottom",
    ocr_engine=None,
    min_detections: int = 2,
    max_samples: int = 12,
) -> bool:
    """Strategically sample dialogue timestamps to detect burned-in subtitles.

    Instead of blind random frames, samples across active dialogue cues where
    subtitles are most expected to be visible. Returns True if consistent
    burned-in text is confirmed in at least `min_detections` distinct cues.
    """
    if not video_path or not os.path.isfile(video_path):
        return False
    cap = _open_video(video_path)
    try:
        engine = ocr_engine or _load_ocr_engine()
        video_fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        video_duration = total_frames / video_fps if video_fps > 0 else 0.0

        sample_times: list[float] = []
        if speech_segments and len(speech_segments) > 0:
            valid_cues = [
                (float(s.get("start", 0.0) or 0.0), float(s.get("end", 0.0) or 0.0))
                for s in speech_segments
                if float(s.get("end", 0.0) or 0.0) > float(s.get("start", 0.0) or 0.0)
            ]
            if valid_cues:
                step = max(1, len(valid_cues) // max_samples)
                selected = valid_cues[::step][:max_samples]
                for start, end in selected:
                    sample_times.append((start + end) * 0.5)

        if not sample_times:
            if video_duration > 2.0:
                sample_times = list(np.linspace(video_duration * 0.1, video_duration * 0.9, min(max_samples, 10)))
            else:
                sample_times = [video_duration * 0.5] if video_duration > 0 else []

        confirmed_detections = 0
        for pos in sample_times:
            frame_idx = max(0, min(total_frames - 1, int(round(pos * video_fps))))
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            cropped = crop_subtitle_region(frame, region=region)
            if cropped.size == 0 or _is_blank_region(cropped):
                continue
            lines = ocr_frame(engine, cropped)
            sanitized = _sanitize_ocr_line(" ".join(lines))
            key = _ocr_consensus_key(sanitized)
            if len(key) >= 2:
                confirmed_detections += 1
                if confirmed_detections >= min_detections:
                    return True
        return confirmed_detections >= min_detections
    except Exception as exc:
        print(f"[OCR] Hardsub detection error: {exc}")
        return False
    finally:
        cap.release()


def transcribe_video_ocr_ranges(
    video_path: str,
    time_ranges: list[tuple[float, float]],
    *,
    region: str = "bottom",
    ocr_engine=None,
    expected_texts: list[str] | None = None,
    scan_modes: list[str] | None = None,
    progress_callback=None,
) -> list[dict]:
    """OCR two representative frames per cue using one engine/video handle.

    This is the fast, conservative verifier used after audio ASR. It is not
    a replacement for full subtitle OCR: a cue is returned only when both
    representative frames produce the same normalized text.
    """
    ranges = [
        (max(0.0, float(start or 0.0)), max(0.0, float(end or 0.0)))
        for start, end in (time_ranges or [])
        if float(end or 0.0) > float(start or 0.0)
    ]
    if not ranges:
        return []
    cap = _open_video(video_path)
    try:
        engine = ocr_engine or _load_ocr_engine()
        video_fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
        results = []
        total = len(ranges)
        for index, (start, end) in enumerate(ranges):
            scan_mode = (
                str(scan_modes[index] or "single")
                if scan_modes is not None and index < len(scan_modes)
                else "single"
            )
            position_groups = _representative_ocr_pairs(start, end, scan_mode=scan_mode)
            expected_text = (
                str(expected_texts[index] or "")
                if expected_texts is not None and index < len(expected_texts)
                else ""
            )
            group_results = []

            def _read_position(position: float) -> str:
                frame_index = max(0, int(round(position * video_fps)))
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ok, frame = cap.read()
                if not ok or frame is None:
                    return ""
                cropped = crop_subtitle_region(frame, region=region)
                if cropped.size == 0 or _is_blank_region(cropped):
                    return ""
                return " ".join(ocr_frame(engine, cropped))

            if scan_mode == "sequence":
                # First inspect one frame at each checkpoint. Repeated text at
                # two checkpoints is already temporal consensus. A state seen
                # only once receives one nearby confirmation frame. This keeps
                # merge detection accurate without blindly running 8 OCR calls
                # for every long cue.
                first_pass = []
                checkpoint_times = [positions[0] for positions in position_groups]
                for positions in position_groups:
                    value = _sanitize_ocr_line(_read_position(positions[0]))
                    key = _ocr_consensus_key(value)
                    if not key:
                        continue
                    if first_pass and first_pass[-1][2] == key:
                        first_pass[-1][1] = positions[-1]
                        first_pass[-1][4] += 1
                    else:
                        first_pass.append([positions[0], positions[-1], key, value, 1, positions])
                for group in first_pass:
                    if group[4] >= 2:
                        group_results.append(([group[0], group[1]], group[3]))
                        continue
                    confirmation = _read_position(group[5][-1])
                    consensus = _two_frame_ocr_consensus([group[3], confirmation])
                    if consensus:
                        group_results.append(([group[0], group[1]], consensus))
            else:
                for positions in position_groups:
                    frame_texts = []
                    for frame_number, position in enumerate(positions):
                        frame_texts.append(_read_position(position))
                        # Legacy truncated-cue mode avoids frame 2 for an
                        # unrelated result. General verification deliberately
                        # confirms arbitrary ASR/OCR disagreement: stable source
                        # subtitles are the authority for text, while VAD remains
                        # the authority for whether speech exists.
                        if (
                            frame_number == 0
                            and scan_mode == "single"
                            and expected_texts is not None
                            and not _is_potential_ocr_correction(expected_text, frame_texts[0])
                        ):
                            break
                    consensus = _two_frame_ocr_consensus(
                        frame_texts,
                        expected_frames=len(positions),
                    )
                    if consensus:
                        group_results.append((positions, consensus))

            # Convert the confirmed samples into ordered OCR states.  Exact
            # adjacent states are collapsed; different states remain separate
            # so reconciliation can split one merged ASR cue.
            compact_groups = []
            for positions, consensus in group_results:
                key = _ocr_consensus_key(consensus)
                if compact_groups and compact_groups[-1][2] == key:
                    compact_groups[-1][1] = positions[-1]
                else:
                    compact_groups.append([positions[0], positions[-1], key, consensus])
            if compact_groups:
                centers = [(group[0] + group[1]) * 0.5 for group in compact_groups]
                outer_start = start
                outer_end = end
                if scan_mode == "sequence":
                    # Blank checkpoints are useful timing evidence too. If a
                    # subtitle first appears well after the VAD window opens,
                    # do not assign it to the entire speech window. Bound the
                    # state transition halfway between the last blank sample
                    # and the first confirmed text sample (and likewise at
                    # the end). This is what keeps visible subtitles aligned
                    # when ASR starts on music, breath, or preceding dialogue.
                    previous_checkpoints = [
                        value for value in checkpoint_times
                        if value < compact_groups[0][0] - 0.01
                    ]
                    following_checkpoints = [
                        value for value in checkpoint_times
                        if value > compact_groups[-1][1] + 0.01
                    ]
                    if previous_checkpoints:
                        outer_start = (previous_checkpoints[-1] + compact_groups[0][0]) * 0.5
                    if following_checkpoints:
                        outer_end = (compact_groups[-1][1] + following_checkpoints[0]) * 0.5
                boundaries = [max(start, outer_start)]
                boundaries.extend(
                    (centers[i - 1] + centers[i]) * 0.5
                    for i in range(1, len(centers))
                )
                boundaries.append(min(end, max(boundaries[-1], outer_end)))
                for group_index, group in enumerate(compact_groups):
                    results.append({
                        "start": round(boundaries[group_index], 3),
                        "end": round(boundaries[group_index + 1], 3),
                        "text": group[3],
                        "words": [],
                        "ocr_consensus_frames": 2,
                        "ocr_scan_mode": scan_mode,
                    })
            if progress_callback is not None:
                progress_callback(index + 1, total)
        return results
    finally:
        cap.release()


def _texts_equal(current_texts, prev_texts):
    if len(current_texts) != len(prev_texts):
        return False
    return all(a == b for a, b in zip(current_texts, prev_texts))


def transcribe_video_ocr(video_path, *, region="bottom", fps=None, ocr_engine=None, start_seconds=0.0, end_seconds=None):
    workflow_started = time.perf_counter()
    profiling = {
        "engine_init": 0.0,
        "seek_decode": 0.0,
        "crop_preprocess": 0.0,
        "change_detection": 0.0,
        "blank_detection": 0.0,
        "ocr_inference": 0.0,
        "ocr_inference_samples": [],
        "postprocess": 0.0,
        "temporal": 0.0,
    }
    duration = 0
    if fps is None:
        try:
            result = subprocess.run(
                [_ffmpeg_path(), "-i", video_path, "-f", "null", "-"],
                capture_output=True, **subprocess_text_kwargs(),
            )
            for line in (result.stderr or "").splitlines():
                if "Duration:" in line:
                    parts = line.split("Duration:")[1].strip().split(",")[0].strip().split(":")
                    duration = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                    break
            else:
                duration = 60
        except Exception:
            duration = 60
        configured_fps = str(os.getenv("OCR_SAMPLING_FPS", "auto") or "auto").strip().lower()
        if configured_fps not in {"", "auto", "default"}:
            try:
                requested_fps = float(configured_fps)
            except ValueError:
                requested_fps = 0.0
            if 0.25 <= requested_fps <= 10.0:
                fps = requested_fps
                print(f"[OCR] Video duration: {duration:.0f}s, configured fps: {fps}")
            else:
                print(f"[OCR] Ignoring invalid OCR_SAMPLING_FPS={configured_fps!r}; using auto.")

        if fps is None:
            # Very short clips often contain title cards or subtitle flashes that
            # last well below one second.  At 1.5 FPS a two-second clip is sampled
            # only at 0.00, 0.67, and 1.33 seconds, which can miss all of them.
            # Four FPS adds only a few frames for these clips while giving a
            # 250 ms sampling interval.
            sampling_duration = duration
            if end_seconds is not None:
                sampling_duration = max(0.0, float(end_seconds) - max(0.0, float(start_seconds or 0.0)))
            if sampling_duration <= 15:
                fps = 4.0
            elif sampling_duration <= 180:
                fps = 1.5
            elif sampling_duration <= 360:
                fps = 1.0
            elif sampling_duration <= 600:
                fps = 0.75
            else:
                fps = 0.5
            range_label = f", selected range: {sampling_duration:.0f}s" if end_seconds is not None else ""
            print(f"[OCR] Video duration: {duration:.0f}s{range_label}, auto fps: {fps}")

    start_seconds = max(0.0, float(start_seconds or 0.0))
    end_seconds = min(float(duration or 0.0), float(end_seconds)) if end_seconds is not None and duration else end_seconds
    frame_interval = 1.0 / fps
    cap = _open_video(video_path)
    video_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_step = max(1, round(video_fps / fps))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    # Include the initial frame at 0 and the final partial sampling interval.
    total_steps = (total_frames + frame_step - 1) // frame_step if total_frames else 0
    if end_seconds is not None:
        total_steps = max(1, int(max(0.0, end_seconds - start_seconds) * fps) + 1)
    if total_steps <= 0:
        total_steps = int(duration * fps) if duration > 0 else 300
    print(f"[OCR] Seeking {total_steps} frames at {fps} fps from video directly...")
    try:
        if ocr_engine is None:
            engine_started = time.perf_counter()
            ocr_engine = _load_ocr_engine()
            profiling["engine_init"] = time.perf_counter() - engine_started

        segments = []
        prev_texts = None
        prev_hash = None
        seg_start = None
        seg_text_lines = []
        empty_streak = 0
        ocr_count = 0
        skip_count = 0
        unchanged_skip_count = 0
        blank_skip_count = 0
        # ``fps`` is the requested sampling rate, not the video's frame rate.
        # Multiplying a sampling index by a rounded ``frame_step`` drifts far
        # enough to skip a requested time range (30 FPS sampled at 4 FPS used
        # to seek 80.5s as 85.9s). Anchor every range at its exact source frame.
        start_frame = max(0, int(round(start_seconds * video_fps)))
        sample_index = 0
        sampled_count = 0

        while True:
            frame_idx = start_frame + sample_index * frame_step
            decode_started = time.perf_counter()
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, img = cap.read()
            profiling["seek_decode"] += time.perf_counter() - decode_started
            if not ret or img is None:
                break
            timestamp = frame_idx / video_fps
            if end_seconds is not None and timestamp > float(end_seconds):
                break
            sampled_count += 1
            crop_started = time.perf_counter()
            cropped = crop_subtitle_region(img, region=region)
            profiling["crop_preprocess"] += time.perf_counter() - crop_started
            change_started = time.perf_counter()
            cur_hash = _crop_hash(cropped)
            unchanged = prev_hash is not None and _hamming_distance(cur_hash, prev_hash) < EXACT_HASH_THRESHOLD
            profiling["change_detection"] += time.perf_counter() - change_started

            if unchanged:
                skip_count += 1
                unchanged_skip_count += 1
                texts = list(prev_texts) if prev_texts else []
            else:
                blank_started = time.perf_counter()
                is_blank = _is_blank_region(cropped)
                profiling["blank_detection"] += time.perf_counter() - blank_started
                if is_blank:
                    skip_count += 1
                    blank_skip_count += 1
                    texts = []
                else:
                    texts = ocr_frame(ocr_engine, cropped, profiling=profiling)
                    ocr_count += 1
                    prev_hash = cur_hash

            sample_index += 1

            if sampled_count % 30 == 0:
                pct = sampled_count * 100 // total_steps if total_steps > 0 else 0
                print(f"[OCR] Frame {sampled_count}/{total_steps} ({pct}%, OCR: {ocr_count}, skip: {skip_count})")

            temporal_started = time.perf_counter()
            if not texts:
                empty_streak += 1
                if empty_streak >= EMPTY_TOLERANCE and seg_start is not None:
                    end_ts = max(seg_start + frame_interval, timestamp - frame_interval * 0.5)
                    combined = " ".join(seg_text_lines).strip()
                    if combined:
                        segments.append({"start": seg_start, "end": end_ts, "text": combined, "words": []})
                    seg_start = None
                    seg_text_lines = []
                    prev_texts = None
                profiling["temporal"] += time.perf_counter() - temporal_started
                continue

            empty_streak = 0
            if prev_texts is not None and _texts_equal(texts, prev_texts):
                profiling["temporal"] += time.perf_counter() - temporal_started
                continue
            if seg_start is not None and seg_text_lines:
                end_ts = max(seg_start + frame_interval, timestamp - frame_interval * 0.5)
                combined = " ".join(seg_text_lines).strip()
                if combined:
                    segments.append({"start": seg_start, "end": end_ts, "text": combined, "words": []})
            seg_start = start_seconds if sample_index == 1 else max(start_seconds, timestamp - frame_interval * 0.5)
            seg_text_lines = texts
            prev_texts = texts
            profiling["temporal"] += time.perf_counter() - temporal_started
    finally:
        cap.release()

    final_temporal_started = time.perf_counter()
    if seg_start is not None and seg_text_lines:
        combined = " ".join(seg_text_lines).strip()
        if combined:
            video_duration = total_frames / video_fps if total_frames and video_fps else (total_steps * frame_interval)
            if end_seconds is not None:
                video_duration = min(video_duration, float(end_seconds))
            end_ts = max(seg_start + frame_interval, video_duration)
            # A range transcription must never extend its final cue beyond
            # the range merely to satisfy the normal minimum-duration rule.
            if end_seconds is not None:
                end_ts = min(end_ts, float(end_seconds))
            segments.append({
                "start": seg_start,
                "end": end_ts,
                "text": combined,
                "words": [],
            })

    # The temporal loop already keeps identical sampled frames in one cue.
    # Only exact consecutive OCR output is extended below; do not perform a
    # second fuzzy/short-text deduplication pass that can hide valid lines.
    merged = _merge_adjacent(segments)
    profiling["temporal"] += time.perf_counter() - final_temporal_started
    print(f"[OCR] Extracted {len(merged)} subtitle segments from {total_steps} frames (OCR: {ocr_count}, skip: {skip_count})")
    inference_samples = profiling["ocr_inference_samples"]
    inference_avg_ms = (sum(inference_samples) / len(inference_samples) * 1000.0) if inference_samples else 0.0
    inference_p95_ms = float(np.percentile(inference_samples, 95) * 1000.0) if inference_samples else 0.0
    sampled_frames = sampled_count
    decode_preprocess_avg_ms = (
        (profiling["seek_decode"] + profiling["crop_preprocess"]) / sampled_frames * 1000.0
        if sampled_frames else 0.0
    )
    print("[OCR Profiling]")
    print(f"Engine initialization: {profiling['engine_init']:.2f}s")
    print(f"Seek/decode: {profiling['seek_decode']:.2f}s")
    print(f"Crop/preprocess: {profiling['crop_preprocess']:.2f}s")
    print(f"Change detection: {profiling['change_detection']:.2f}s")
    print(f"Blank detection: {profiling['blank_detection']:.2f}s")
    print(f"RapidOCR inference: {profiling['ocr_inference']:.2f}s")
    print(f"Post-processing: {profiling['postprocess']:.2f}s")
    print(f"Temporal segments/merge: {profiling['temporal']:.2f}s")
    print(f"Total: {time.perf_counter() - workflow_started:.2f}s")
    print(
        "Frames: "
        f"sampled={sampled_frames}, OCR={ocr_count}, unchanged_skip={unchanged_skip_count}, blank_skip={blank_skip_count}"
    )
    print(f"OCR inference: avg={inference_avg_ms:.0f}ms, p95={inference_p95_ms:.0f}ms")
    print(f"Frame decode/preprocess: avg={decode_preprocess_avg_ms:.0f}ms")
    return merged


def _merge_adjacent(segments, max_gap=0.5):
    if not segments:
        return []
    merged = []
    current = dict(segments[0])
    current["text"] = _sanitize_ocr_line(current.get("text", ""))
    for seg in segments[1:]:
        seg = dict(seg)
        seg["text"] = _sanitize_ocr_line(seg.get("text", ""))
        if not seg["text"]:
            continue
        gap = seg["start"] - current["end"]
        # A fuzzy OCR match may represent a genuinely new subtitle line.
        # Extend only the exact same text displayed on successive frames.
        if gap <= max_gap and seg["text"] == current["text"]:
            current["end"] = seg["end"]
        else:
            if current.get("text"):
                merged.append(current)
            current = dict(seg)
    if current.get("text"):
        merged.append(current)
    return merged


def unload_ocr_engine():
    global _OCR_ENGINE
    with _get_lock():
        _OCR_ENGINE = None
        print("[OCR] Engine unloaded")

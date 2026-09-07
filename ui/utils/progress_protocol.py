import os
import re
import sys
from typing import Optional, Any

APP_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "app"))
if APP_PATH not in sys.path:
    sys.path.insert(0, APP_PATH)

try:
    from app.core.models.progress import ProgressEvent
except ImportError:
    from core.models.progress import ProgressEvent


def format_duration_clock(seconds: Optional[float]) -> str:
    """Format seconds into MM:SS or HH:MM:SS."""
    if seconds is None or seconds < 0:
        return "—"
    total_secs = int(round(seconds))
    mins = total_secs // 60
    secs = total_secs % 60
    hours, mins = divmod(mins, 60)
    if hours > 0:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def parse_progress_update(raw_data: Any, default_workflow: str = "general", default_stage: str = "") -> ProgressEvent:
    """Convert any progress callback payload (dict, tuple, int, string, or ProgressEvent)
    into a standardized ProgressEvent."""
    if isinstance(raw_data, ProgressEvent):
        return raw_data
    if isinstance(raw_data, dict):
        return ProgressEvent.from_dict(raw_data)
    
    if isinstance(raw_data, (tuple, list)):
        # Common pattern: (percent, message) or (step_id, message) or (current, total, message)
        if len(raw_data) == 2:
            first, second = raw_data
            if isinstance(first, (int, float)) and isinstance(second, str):
                pct = max(0, min(100, int(first)))
                return ProgressEvent(
                    workflow=default_workflow,
                    stage=default_stage,
                    percent=pct,
                    message=str(second or "").strip(),
                )
            if isinstance(first, str) and isinstance(second, str):
                return ProgressEvent(
                    workflow=default_workflow,
                    stage=first,
                    message=str(second or "").strip(),
                )
        elif len(raw_data) >= 3:
            curr, tot, msg = raw_data[0], raw_data[1], raw_data[2]
            if isinstance(curr, (int, float)) and isinstance(tot, (int, float)):
                pct = int(curr * 100 / max(1.0, float(tot)))
                return ProgressEvent(
                    workflow=default_workflow,
                    stage=default_stage,
                    current=float(curr),
                    total=float(tot),
                    percent=max(0, min(100, pct)),
                    message=str(msg or "").strip(),
                )

    text = str(raw_data or "").strip()
    match_ratio = re.search(r"(\d+)\s*/\s*(\d+)", text)
    match_pct = re.search(r"(?:\(|\b)(\d{1,3})%(?:\)|\b)", text)
    percent = 0
    curr = 0.0
    tot = 0.0
    if match_ratio and int(match_ratio.group(2)) > 0:
        curr = float(match_ratio.group(1))
        tot = float(match_ratio.group(2))
        percent = int(curr * 100 / tot)
    elif match_pct:
        percent = int(match_pct.group(1))

    return ProgressEvent(
        workflow=default_workflow,
        stage=default_stage,
        current=curr,
        total=tot,
        percent=max(0, min(100, percent)),
        message=text,
    )

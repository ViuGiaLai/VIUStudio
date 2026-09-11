from __future__ import annotations

APP_VERSION = "1.3.1"
APP_NAME = "VIUStudio Video & Auto Edit Recap"
AUTO_RECAP_VERSION = "1.1.1"

RELEASE_NOTES = """✨ VIUStudio v1.3.1 - Edge TTS Support, SRT-TTS Studio Enhancement & Launcher UI Release

Hạng mục tính năng mới:
• 🎙️ Edge TTS Integration: Bổ sung hỗ trợ Edge TTS đa dạng giọng đọc truyền cảm, tự động quản lý kết nối và fallback thông minh.
• 🎛️ SRT-TTS Studio Window Nâng Cấp: Giao diện tạo giọng nói từ phụ đề hoàn chỉnh, chỉnh sửa tốc độ/pitch từng câu, nghe thử giọng tức thì và xuất âm thanh chất lượng cao.
• 🖥️ Launcher Layout & Responsive Reflow: Bố cục khởi động được tinh chỉnh hiện đại, thẻ dự án tự động co giãn theo kích thước cửa sổ mà không bị lỗi thanh cuộn ngang.
• ⏱️ Voice Timing & Export Synchronization: Chuẩn hóa thuật toán căn chỉnh thời gian âm thanh, giữ khoảng lặng nguyên bản và đồng bộ timeline video.
• 🛡️ Test Suite Hardening: Bổ sung bộ kiểm thử Edge TTS và Launcher Layout, đạt 328 tests tự động pass 100%.
"""


def get_app_version_string() -> str:
    return f"{APP_NAME} v{APP_VERSION} (Recap Engine v{AUTO_RECAP_VERSION})"

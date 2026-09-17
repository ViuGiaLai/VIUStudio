from __future__ import annotations

APP_VERSION = "1.4.0"
APP_NAME = "VIUStudio Video & Auto Edit Recap"
AUTO_RECAP_VERSION = "1.2.0"

RELEASE_NOTES = """✨ VIUStudio v1.4.0 - Movie Review AI Studio, Background Exports, Subtitle Sync & Multi-Key Pool

Hạng mục tính năng mới:
• 🎬 Movie Review AI Studio: Môi trường biên tập tóm tắt phim chuyên nghiệp, phân cảnh thông minh, tự động viết kịch bản review đa phong cách qua Gemini / OpenAI và lập Story Arc mượt mà.
• 🔑 Gemini Key Pool Manager: Quản lý kho khóa API Gemini xoay vòng tự động, tự động chuyển đổi khóa dự phòng khi gặp lỗi hạn mức (Quota / 429) an toàn tuyệt đối.
• ⚡ Background Export Manager: Xuất video chạy ngầm đa nhiệm, giám sát tiến độ trực quan từ Launcher và MainWindow, không làm gián đoạn công việc biên tập.
• ⏱️ Subtitle Sync & Timing Tool: Hộp thoại nắn chỉnh thời gian phụ đề chuyên sâu với các chế độ dời mốc thời gian (Shift), bắt dính âm thanh (Snap) và đồng bộ gợn sóng (Ripple).
• 🎵 Smart Music Library Service: Hệ thống quản lý nhạc nền BGM phân loại theo tâm trạng, nhịp điệu và tự động ducking theo giọng thuyết minh.
• 🛡️ Continuity QA & Character Glossary: Kiểm soát tính nhất quán kịch bản, phát hiện lỗi mạch truyện trước khi xuất và chuẩn hóa tên nhân vật / thuật ngữ xuyên suốt.
• 🧪 Automated Test Suite: Đạt hơn 510 bài kiểm thử tự động với tỷ lệ vượt qua 100%.
"""


def get_app_version_string() -> str:
    return f"{APP_NAME} v{APP_VERSION} (Recap Engine v{AUTO_RECAP_VERSION})"

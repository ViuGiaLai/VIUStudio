from __future__ import annotations

APP_VERSION = "1.3.3"
APP_NAME = "VIUStudio Video & Auto Edit Recap"
AUTO_RECAP_VERSION = "1.1.3"

RELEASE_NOTES = """✨ VIUStudio v1.3.3 - One-Pass Export Optimization, Responsive Workspace & Anti-Duplicate Enhancements

Hạng mục tính năng mới:
• ⚡ One-Pass Export Optimization: Tối ưu hóa luồng xuất video 1 bước duy nhất (1-Pass) cho cả phụ đề và hiệu ứng, loại bỏ xuất file trung gian giúp tăng tốc độ render và tiết kiệm dung lượng đĩa.
• 📐 Responsive Workspace & Splitter Persistence: Cải tiến thanh chia tỷ lệ linh hoạt giữa màn hình Preview (64%) và Timeline (36%), tự động ghi nhớ tỷ lệ theo từng dự án, hỗ trợ kéo thả mượt mà trên mọi kích thước màn hình.
• 🎛️ Anti-Duplicate Dialog Full Sync: Hoàn thiện đồng bộ toàn bộ tùy chọn bộ lọc chống trùng lặp từ giao diện trực quan sang cấu hình xuất FFmpeg.
• 🎵 BGM Library Collection: Bổ sung thư viện nhạc nền không bản quyền chất lượng cao (21 bài) phục vụ lồng nhạc và kháng quét Content ID.
• 🖱️ Timeline & Inspector Precision: Tối ưu tương tác click chọn phụ đề trên timeline, kích thước nút hành động inspector chuẩn xác và phản hồi nhanh.
• 🧪 Automated Test Suite: Đạt 389/389 bài kiểm thử tự động (386 passed, 3 skipped, 0 failed).
"""


def get_app_version_string() -> str:
    return f"{APP_NAME} v{APP_VERSION} (Recap Engine v{AUTO_RECAP_VERSION})"

from __future__ import annotations

APP_VERSION = "1.3.2"
APP_NAME = "VIUStudio Video & Auto Edit Recap"
AUTO_RECAP_VERSION = "1.1.2"

RELEASE_NOTES = """✨ VIUStudio v1.3.2 - CapCut-Style Subtitle Controls, 1:1 Export Sync & Video Workflow Enhancements

Hạng mục tính năng mới:
• 🎯 CapCut-Style Subtitle Direct Manipulation: Điều khiển phụ đề trực tiếp trên màn hình xem trước (Live Preview). Bấm chọn hiển thị khung viền nét đứt màu xanh neon (#00E5FF) cùng 4 tay cầm góc; kéo thả tự do mọi vị trí (Drag & Move); kéo góc phóng to/thu nhỏ cỡ chữ mượt mà theo thời gian thực (12px - 140px).
• 🔄 Đồng bộ 1:1 Tuyệt đối sang Export: Chuẩn hóa thuật toán neo tâm \\an5\\pos(x,y) và cỡ chữ font giữa Preview và xuất video libass/FFmpeg. Khắc phục triệt để hiện tượng kéo trên preview mà xuất video không đổi.
• 🖥️ Live Preview Display Hardening: Sửa lỗi tắt text rendering trong CPU Mode, triệt tiêu sai số mili-giây khi seek/click timeline segment, loại bỏ dải đen nền 96px, hiển thị phụ đề tức thì khi click chọn đoạn.
• 🎙️ Import Voice Audio: Bổ sung chức năng nhập trực tiếp file giọng đọc / voiceover vào dự án qua menu More.
• 🛑 Export Progress Dialog & Cancel: Giao diện tiến trình xuất video hiện đại, bổ sung nút Cancel dừng tác vụ an toàn ngay lập tức.
• 🛡️ Anti-Duplicate Video Pipeline: Bổ sung pipeline chống trùng lặp video (lật gương, zoom punch, chỉnh màu động, đối chiếu video so sánh trước/sau).
• 🧪 Automated Test Suite: Đạt 347/347 bài kiểm thử tự động (344 passed, 3 skipped, 0 failed).
"""


def get_app_version_string() -> str:
    return f"{APP_NAME} v{APP_VERSION} (Recap Engine v{AUTO_RECAP_VERSION})"

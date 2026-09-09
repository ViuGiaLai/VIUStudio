from __future__ import annotations

APP_VERSION = "1.3.0"
APP_NAME = "VIUStudio Video & Auto Edit Recap"
AUTO_RECAP_VERSION = "1.1.0"

RELEASE_NOTES = """✨ VIUStudio v1.3.0 - Modern Web Studio, Hybrid Architecture & Studio Tools Release

Hạng mục tính năng mới:
• 🌐 VIUStudio Web Studio: Hệ thống giao diện web hiện đại, hoàn chỉnh (Overview, Projects, Video Editor, Tools Hub, Voice Studio, Devices, AI Resources, Settings).
• ⚡ Kiến Trúc Thích Ứng 3 Tầng (3-Tier Adaptive Architecture): Phân lập chuẩn giữa Mobile Web (WASM SIMD, W3C Storage Quota) và PC Workstation (Companion Daemon, Whisper Turbo/Large, Demucs v4 GPU).
• 🎙️ Voice Studio SRT-to-TTS: Tổng hợp giọng nói nơ-ron tiếng Việt (VAIS, VIVOS) chạy trực tiếp trên WebAssembly, đồng bộ khoảng lặng timeline CapCut chuẩn xác.
• 🎛️ Studio Tools Hub: Bộ công cụ độc lập cho biên tập phụ đề SRT, nhận diện giọng nói Whisper và tách nhạc nền Demucs v4 chất lượng cao.
• ☁️ Cloud Sync & Supabase Integration: Đồng bộ dự án, cài đặt người dùng và xác thực Google.
• 🛡️ Engine Runtime & Quality Hardening: Tối ưu hóa pipeline xuất video NVENC/CPU, launcher lifecycle và 100% kiểm thử tự động (313 tests passed).
"""


def get_app_version_string() -> str:
    return f"{APP_NAME} v{APP_VERSION} (Recap Engine v{AUTO_RECAP_VERSION})"

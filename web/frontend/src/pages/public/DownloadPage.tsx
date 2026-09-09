import React from 'react';
import { Link } from 'react-router-dom';
import { Monitor, ArrowUpRight, AudioLines, Download, Check, Sparkles, Laptop, ShieldCheck } from 'lucide-react';
import { PublicLayout } from '../../components/layout/PublicLayout';

export const DownloadPage: React.FC = () => {
  return (
    <PublicLayout>
      <div className="page-intro">
        <div className="studio-eyebrow">
          <span /> VIUSTUDIO COMPANION
        </div>
        <h1>Mở Rộng Sức Mạnh Máy Tính Cá Nhân</h1>
        <p>
          VIUStudio kết hợp giữa giao diện Web hiện đại và ứng dụng máy tính Companion để tận dụng tối đa
          sức mạnh GPU NVIDIA CUDA, giữ trọn vẹn quyền riêng tư cho các file video nặng.
        </p>
      </div>

      <div className="tool-launch-grid">
        {/* Card 1: Web Workspace */}
        <section className="launch-card featured">
          <AudioLines size={32} className="text-brand mb-1" />
          <span className="tool-status">Sử dụng ngay · Trình duyệt</span>
          <h2>VIUStudio Web Workspace</h2>
          <p>
            Biên tập phụ đề SRT, lồng tiếng Voice Studio và quản lý toàn bộ timeline trực tiếp trên trình duyệt mà không cần cài đặt.
          </p>
          <Link to="/app" className="studio-link-primary w-full">
            <span>Mở Workspace Ngay</span>
            <ArrowUpRight size={18} />
          </Link>
        </section>

        {/* Card 2: Companion Desktop */}
        <section className="launch-card">
          <Monitor size={32} className="text-accent-focus mb-1" />
          <span className="tool-status">Windows 10/11 · Bản đang xác minh</span>
          <h2>VIUStudio Companion Worker</h2>
          <p>
            Chạy dưới nền máy tính để xử lý Whisper Large v3, Demucs tách stem và render video 60fps qua GPU.
            Khởi chạy trực tiếp qua mã nguồn dự án hoặc cài đặt một lần.
          </p>
          <div className="space-y-2 w-full mt-2">
            <Link to="/app/devices" className="studio-link-secondary w-full text-center block">
              <Laptop size={16} className="inline mr-1.5" />
              Ghép nối Companion với Web
            </Link>
            <Link to="/help#companion" className="back-link block text-center">
              Xem tài liệu cài đặt Worker <ArrowUpRight size={15} className="inline" />
            </Link>
          </div>
        </section>
      </div>

      {/* System Requirements Strip */}
      <div className="mt-10 rounded-card border border-border bg-surface p-6 space-y-3">
        <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-brand" />
          <span>Yêu Cầu Hệ Thống Khuyến Nghị Cho Companion</span>
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs text-text-secondary pt-1">
          <div>
            <strong className="text-text-primary block mb-0.5">Hệ điều hành</strong>
            <span>Windows 10/11 64-bit. Các hệ điều hành khác cần chạy từ mã nguồn và chưa có bộ cài chính thức.</span>
          </div>
          <div>
            <strong className="text-text-primary block mb-0.5">Card đồ họa (GPU)</strong>
            <span>NVIDIA RTX 3060 / 4060 trở lên (VRAM 6GB+) hỗ trợ CUDA</span>
          </div>
          <div>
            <strong className="text-text-primary block mb-0.5">Bộ nhớ & Lưu trữ</strong>
            <span>16 GB RAM · Tối thiểu 10 GB ổ cứng trống cho AI model</span>
          </div>
        </div>
      </div>
    </PublicLayout>
  );
};

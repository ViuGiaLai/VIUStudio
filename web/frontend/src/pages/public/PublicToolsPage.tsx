import React from 'react';
import { Link } from 'react-router-dom';
import { AudioLines, Subtitles, Mic, Music, ArrowUpRight } from 'lucide-react';
import { PublicLayout } from '../../components/layout/PublicLayout';

export const PublicToolsPage: React.FC = () => {
  const tools = [
    {
      icon: AudioLines,
      title: 'Voice Studio (SRT → MP3)',
      text: 'Chuyển phụ đề thành giọng nói bằng Piper WebAssembly, giữ đúng timeline CapCut tại mốc 00:00.',
      to: '/voice-studio',
      badge: 'WebAssembly · In Browser',
    },
    {
      icon: Subtitles,
      title: 'Trình sửa phụ đề SRT',
      text: 'Import file .srt, chỉnh sửa mốc thời gian, tách gộp câu, kiểm tra tốc độ đọc CPS và xuất UTF-8.',
      to: '/app/tools?tab=srt',
      badge: 'In Browser · 100% Riêng tư',
    },
    {
      icon: Mic,
      title: 'Nhận diện lời nói Whisper AI',
      text: 'Trích xuất kịch bản và phụ đề tự động từ video hoặc âm thanh bằng mô hình Whisper Large v3.',
      to: '/app/tools?tab=transcript',
      badge: 'GPU AI Acceleration',
    },
    {
      icon: Music,
      title: 'Tách giọng & Nhạc nền Demucs',
      text: 'Bóc tách lời thoại và âm thanh nhạc nền độc lập bằng mô hình Demucs v4 Hybrid Transformer.',
      to: '/app/tools?tab=separation',
      badge: 'Demucs Neural Stems',
    },
  ];

  return (
    <PublicLayout>
      <div className="page-intro">
        <div className="studio-eyebrow">
          <span /> BỘ CÔNG CỤ SÁNG TẠO
        </div>
        <h1>Chọn công cụ. Bắt đầu làm việc.</h1>
        <p>
          Hệ thống các công cụ xử lý phụ đề, âm thanh và giọng nói AI được thiết kế tối ưu cho người làm video recap.
        </p>
      </div>

      <div className="tool-launch-grid">
        {tools.map(({ icon: Icon, title, text, to, badge }) => (
          <section key={title} className="launch-card featured">
            <Icon size={32} className="text-brand mb-1" />
            <span className="tool-status">{badge}</span>
            <h2>{title}</h2>
            <p>{text}</p>
            <Link to={to} className="launch-action">
              <span>Mở công cụ ngay</span>
              <ArrowUpRight size={20} />
            </Link>
          </section>
        ))}
      </div>
    </PublicLayout>
  );
};

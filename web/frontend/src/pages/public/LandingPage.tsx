import React from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowUpRight,
  ArrowRight,
  FileText,
  AudioLines,
  Download,
  ShieldCheck,
  Laptop,
  Timer,
  Subtitles,
  Sparkles,
  Mic,
  Music,
  FolderKanban,
} from 'lucide-react';
import { PublicLayout } from '../../components/layout/PublicLayout';

export const LandingPage: React.FC = () => {
  return (
    <PublicLayout back={false}>
      {/* Hero Section */}
      <section className="home-hero">
        <div className="hero-copy">
          <div className="studio-eyebrow">
            <span /> NỀN TẢNG SÁNG TẠO RECAP CHUYÊN NGHIỆP
          </div>
          <h1>
            Kịch bản của bạn.
            <br />
            <span className="ai-gradient-text">Giọng kể & Video đỉnh cao.</span>
          </h1>
          <p>
            Biến file phụ đề SRT thành giọng đọc MP3 tự nhiên hoặc sản xuất toàn bộ video recap
            với Whisper AI, Demucs bóc tách âm thanh và trình biên tập timeline đa luồng.
          </p>
          <div className="hero-actions">
            <Link to="/app" className="studio-link-primary">
              <span>Mở Không Gian Làm Việc</span>
              <ArrowUpRight size={19} />
            </Link>
            <Link to="/voice-studio" className="studio-link-secondary">
              <AudioLines size={17} className="inline mr-1" />
              <span>Voice Studio (SRT → MP3)</span>
            </Link>
          </div>
          <div className="hero-note">
            <ShieldCheck size={16} className="text-brand" />
            <span>TTS và SRT xử lý cục bộ · Không tải video lớn lên đám mây · Metadata chỉ đồng bộ khi đăng nhập</span>
          </div>
        </div>

        {/* Workflow Showcase Illustration */}
        <div className="workflow-display" aria-label="Minh họa quy trình SRT thành MP3">
          <div className="display-top">
            <span>
              <AudioLines size={18} className="text-brand" /> VOICE STUDIO · RECAP PIPELINE
            </span>
            <span className="sample-tag font-mono">LIVE PREVIEW</span>
          </div>

          <div className="display-file">
            <div className="file-symbol">
              <FileText />
            </div>
            <div>
              <strong>ky-su-kham-pha-dai-duong.srt</strong>
              <p>Phụ đề song ngữ → Giọng lồng tiếng Piper VAIS</p>
            </div>
            <span className="file-ext font-mono">SRT UTF-8</span>
          </div>

          <div className="script-example">
            <span>00:03,100 → 00:07,450</span>
            <p>
              “Mỗi câu chuyện đều bắt đầu
              <br />
              từ những bí mật ẩn sâu dưới đáy biển.”
            </p>
          </div>

          {/* Soundwave Bars */}
          <div className="voice-visual" aria-hidden="true">
            {Array.from({ length: 38 }, (_, i) => (
              <i key={i} style={{ height: `${14 + ((i * 37 + i * i * 3) % 62)}px` }} />
            ))}
          </div>

          <div className="display-bottom">
            <div>
              <strong>Giữ nguyên khoảng im lặng & mốc thời gian</strong>
              <span>Kéo thả trực tiếp vào CapCut tại mốc 00:00</span>
            </div>
            <span className="output-tag font-mono font-bold">
              <Download size={16} /> .MP3 192kbps
            </span>
          </div>
        </div>
      </section>

      {/* Benefit Strip */}
      <section className="benefit-strip">
        {[
          {
            icon: Laptop,
            title: 'Xử lý trên máy bạn (Local Privacy)',
            text: 'Video và âm thanh ở lại trên thiết bị. Khi đăng nhập, Supabase chỉ đồng bộ tài khoản, cài đặt, metadata và nội dung phụ đề.',
          },
          {
            icon: Timer,
            title: 'Chuẩn xác Timeline CapCut',
            text: 'Smart Fit tự động điều chỉnh câu nói vừa khít thời lượng phụ đề, không làm lệch đồng bộ âm thanh.',
          },
          {
            icon: Sparkles,
            title: 'Tăng tốc qua Companion',
            text: 'Whisper, Demucs và xuất video chỉ chạy khi Companion được kết nối và báo đúng khả năng phần cứng.',
          },
        ].map(({ icon: Icon, title, text }) => (
          <div key={title} className="space-y-1">
            <Icon size={24} className="text-brand mb-2" />
            <h2 className="text-base font-bold text-text-primary">{title}</h2>
            <p className="text-xs text-text-secondary leading-relaxed">{text}</p>
          </div>
        ))}
      </section>

      {/* Tools Showcase */}
      <section className="home-tools pb-12">
        <div className="section-heading">
          <div>
            <div className="studio-eyebrow">
              <span /> BỘ CÔNG CỤ TÍCH HỢP
            </div>
            <h2>Mọi tính năng cần thiết cho Video Creator</h2>
          </div>
          <Link to="/tools" className="text-xs font-semibold text-brand hover:underline flex items-center gap-1">
            <span>Tất cả công cụ</span>
            <ArrowUpRight size={16} />
          </Link>
        </div>

        <div className="tool-launch-grid">
          {[
            {
              icon: AudioLines,
              title: 'Voice Studio (SRT → TTS → MP3)',
              text: 'Biến phụ đề thành giọng nói lồng tiếng tự nhiên bằng Piper WebAssembly ngay trong trình duyệt.',
              to: '/voice-studio',
              status: 'Trình duyệt · WASM',
            },
            {
              icon: Subtitles,
              title: 'Trình Sửa Phụ Đề SRT Chuyên Nghiệp',
              text: 'Import SRT, tách câu, gộp câu, đo tốc độ đọc CPS và xuất UTF-8 an toàn.',
              to: '/app/tools?tab=srt',
              status: 'In-Browser',
            },
            {
              icon: Mic,
              title: 'Nhận Diện Giọng Nói Whisper AI',
              text: 'Trích xuất tự động phụ đề và kịch bản song ngữ từ video/audio với độ chính xác cao.',
              to: '/app/tools?tab=transcript',
              status: 'Cần Companion',
            },
            {
              icon: Music,
              title: 'Tách Giọng & Nhạc Nền Demucs',
              text: 'Bóc tách lời thoại và âm thanh soundtrack độc lập bằng AI Demucs v4.',
              to: '/app/tools?tab=separation',
              status: 'Cần Companion',
            },
          ].map(({ icon: Icon, title, text, to, status }) => (
            <Link to={to} key={to} className="launch-card featured">
              <Icon size={30} className="text-brand" />
              <span className="tool-status">{status}</span>
              <h3>{title}</h3>
              <p>{text}</p>
              <span className="launch-action">
                <span>Khởi chạy công cụ</span>
                <ArrowUpRight size={18} />
              </span>
            </Link>
          ))}
        </div>
      </section>
    </PublicLayout>
  );
};

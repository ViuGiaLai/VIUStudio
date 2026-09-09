import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ArrowUpRight, Search, HelpCircle, BookOpen, Laptop, Sparkles, ChevronDown } from 'lucide-react';
import { PublicLayout } from '../../components/layout/PublicLayout';

export const HelpPage: React.FC = () => {
  const inside = useLocation().pathname.startsWith('/app');
  const [search, setSearch] = useState('');

  const faqs = [
    {
      q: 'Có cần đăng ký hoặc cài Companion để sử dụng không?',
      a: 'Hoàn toàn KHÔNG cần đối với công cụ Voice Studio (SRT → MP3). Tính năng này chạy 100% bằng WebAssembly trong trình duyệt của bạn. Bạn chỉ cần cài đặt VIUStudio Companion khi muốn sử dụng GPU cục bộ (NVIDIA CUDA) để nhận diện Whisper cho video dài nhiều tiếng hoặc tách âm thanh Demucs và Render video bằng NVENC.',
      tag: 'Cơ bản',
    },
    {
      q: 'Cách đưa file MP3 tạo từ phụ đề vào CapCut / Premiere thế nào?',
      a: 'File MP3 tạo ra luôn giữ nguyên toàn bộ khoảng im lặng và mốc thời gian chính xác tương ứng với file SRT gốc. Bạn chỉ cần kéo file MP3 vào timeline của CapCut/Premiere tại đúng mốc 00:00:00. Sau đó import chính file SRT đó vào track phụ đề thì âm thanh giọng đọc và chữ sẽ khớp nhau 100%.',
      tag: 'CapCut',
    },
    {
      q: 'Vì sao lần đầu tiên bấm Tạo MP3 lại mất một chút thời gian tải?',
      a: 'Trong lần đầu tiên, trình duyệt cần tải mô hình AI ONNX (khoảng 60MB - 80MB) và lưu vào IndexedDB / Cache Storage cục bộ. Từ lần thứ hai trở đi, mô hình được nạp tức thì từ bộ nhớ máy tính mà không cần tải lại.',
      tag: 'Hiệu năng',
    },
    {
      q: 'Tính năng Smart Fit tự động co giãn thời gian hoạt động ra sao?',
      a: 'Khi câu dịch tiếng Việt dài hơn câu thoại gốc, Smart Fit sẽ tự động tính toán tỷ lệ độ dài và tăng tốc độ đọc của riêng câu đó (lên đến 1.3x - 1.4x) để đảm bảo giọng đọc kết thúc trước mốc bắt đầu của câu kế tiếp, tránh hiện tượng chồng lấn âm thanh.',
      tag: 'Thuật toán',
    },
    {
      q: 'File phụ đề .SRT báo lỗi định dạng thì cần kiểm tra những gì?',
      a: 'Đảm bảo file được lưu với bảng mã UTF-8 (không kèm BOM). Mỗi câu phụ đề cần có 3 thành phần: Số thứ tự câu (1, 2, 3...), Dòng thời gian dạng 00:00:01,000 --> 00:00:03,500 và Nội dung văn bản câu thoại.',
      tag: 'Định dạng',
    },
    {
      q: 'Làm thế nào để ghép nối máy tính qua Companion?',
      a: 'Vào trang Thiết Bị (/app/devices), bấm "Ghép Nối Máy Tính Mới". Mở ứng dụng VIUStudio Companion trên PC của bạn, bấm "Kết nối" và nhập mã 6 số hiển thị trên web. Ngay khi kết nối, web sẽ tự động nhận diện thông số card đồ họa NVIDIA CUDA và dung lượng VRAM của bạn.',
      tag: 'Companion',
    },
  ];

  const filteredFaqs = faqs.filter(
    (f) =>
      !search.trim() ||
      f.q.toLowerCase().includes(search.toLowerCase()) ||
      f.a.toLowerCase().includes(search.toLowerCase()) ||
      f.tag.toLowerCase().includes(search.toLowerCase())
  );

  const content = (
    <div className="space-y-8 max-w-4xl mx-auto py-6">
      <div className="page-intro">
        <div className="studio-eyebrow">
          <HelpCircle className="h-4 w-4" /> TRUNG TÂM HƯỚNG DẪN & TRỢ GIÚP
        </div>
        <h1 className="ai-gradient-text text-3xl sm:text-4xl font-black mt-3">
          Làm Chủ VIUStudio Từ A Đến Z
        </h1>
        <p className="text-text-secondary text-sm sm:text-base mt-2">
          Các bước nhanh để tạo phụ đề, lồng tiếng AI chất lượng cao và đưa thẳng vào CapCut.
        </p>
      </div>

      {/* 3 Quick Steps */}
      <div className="help-steps grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[
          { step: '01', title: 'Import Phụ Đề SRT', desc: 'Chọn file SRT từ máy hoặc bấm thử file mẫu có sẵn trên giao diện.' },
          { step: '02', title: 'Chọn Giọng Đọc & Tốc Độ', desc: 'Chọn giọng nam/nữ truyền cảm (VAIS) hoặc Kokoro và tinh chỉnh tốc độ.' },
          { step: '03', title: 'Tạo MP3 Khớp Timeline', desc: 'Hệ thống tự giữ khoảng lặng; tải MP3 về và kéo vào CapCut mốc 00:00.' },
        ].map((item) => (
          <div key={item.step} className="p-5 rounded-card bg-surface border border-border space-y-2">
            <span className="font-mono text-brand font-black text-xl">{item.step}</span>
            <h2 className="text-sm font-bold text-text-primary">{item.title}</h2>
            <p className="text-xs text-text-secondary leading-relaxed">{item.desc}</p>
          </div>
        ))}
      </div>

      {/* Search FAQ */}
      <div className="space-y-4 pt-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <h2 className="text-lg font-bold text-text-primary flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-brand" /> Các Câu Hỏi Thường Gặp (FAQ)
          </h2>
          <div className="relative">
            <Search className="h-3.5 w-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
            <input
              type="text"
              placeholder="Tìm câu hỏi..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="bg-surface border border-border rounded-input pl-8 pr-3 py-1.5 text-xs text-text-primary focus:border-brand w-full sm:w-60"
            />
          </div>
        </div>

        <div className="space-y-3">
          {filteredFaqs.length === 0 ? (
            <div className="p-8 text-center text-xs text-text-muted bg-surface rounded-card border border-border">
              Không tìm thấy câu hỏi nào phù hợp với từ khóa của bạn.
            </div>
          ) : (
            filteredFaqs.map((item, idx) => (
              <details
                key={idx}
                className="group rounded-card border border-border bg-surface p-4 transition-all hover:border-border-light cursor-pointer"
              >
                <summary className="font-semibold text-sm text-text-primary flex items-center justify-between list-none">
                  <span className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-brand/10 text-brand border border-brand/20">
                      {item.tag}
                    </span>
                    <span>{item.q}</span>
                  </span>
                  <ChevronDown className="h-4 w-4 text-text-muted transition-transform group-open:rotate-180 shrink-0" />
                </summary>
                <p className="mt-3 text-xs text-text-secondary leading-relaxed border-t border-border pt-3 pl-2">
                  {item.a}
                </p>
              </details>
            ))
          )}
        </div>
      </div>

      {/* CTA Footer */}
      <div className="pt-4 flex flex-wrap items-center gap-3">
        <Link to="/voice-studio" className="studio-link-primary">
          <span>Mở Voice Studio Thử Ngay</span>
          <ArrowUpRight size={18} />
        </Link>
        <Link to="/app" className="studio-link-secondary">
          <span>Vào Không Gian Làm Việc</span>
        </Link>
      </div>
    </div>
  );

  return inside ? <div className="public-content !p-0">{content}</div> : <PublicLayout>{content}</PublicLayout>;
};

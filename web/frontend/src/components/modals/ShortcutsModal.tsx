import React, { useEffect } from 'react';
import { Modal } from '../common/Modal';
import { Keyboard, Play, Video, Type, Sparkles, Command } from 'lucide-react';

interface ShortcutsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ShortcutsModal: React.FC<ShortcutsModalProps> = ({ isOpen, onClose }) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Toggle shortcuts modal on '?' or Shift + '/'
      if ((e.key === '?' || (e.shiftKey && e.key === '/')) && !['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement).tagName)) {
        e.preventDefault();
        if (isOpen) onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  const shortcutGroups = [
    {
      category: 'Phát & Điều Khiển Media (Playback)',
      icon: <Play className="h-4 w-4 text-brand" />,
      shortcuts: [
        { key: 'Space', desc: 'Phát / Tạm dừng video hoặc âm thanh' },
        { key: 'J / L', desc: 'Tua lùi 1s / Tua tới 1s' },
        { key: 'K', desc: 'Dừng phát' },
        { key: '← / →', desc: 'Nhảy từng khung hình (Frame-by-frame)' },
        { key: '0 - 9', desc: 'Nhảy nhanh đến 0% - 90% timeline' },
      ],
    },
    {
      category: 'Biên Tập Phụ Đề & Giọng Đọc',
      icon: <Type className="h-4 w-4 text-accent-focus" />,
      shortcuts: [
        { key: 'Alt + N', desc: 'Thêm dòng phụ đề mới tại vị trí phát' },
        { key: 'Ctrl + Enter', desc: 'Lưu thay đổi & hoàn tất sửa câu' },
        { key: 'Tab / Shift + Tab', desc: 'Chuyển sang câu kế tiếp / câu trước' },
        { key: 'Ctrl + F', desc: 'Mở hộp tìm kiếm & thay thế từ' },
        { key: 'Delete', desc: 'Xóa câu phụ đề đang chọn' },
      ],
    },
    {
      category: 'Thao Tác Hệ Thống & Dự Án',
      icon: <Command className="h-4 w-4 text-status-success" />,
      shortcuts: [
        { key: 'Ctrl + K', desc: 'Mở thanh tìm kiếm & lệnh nhanh (Command Palette)' },
        { key: 'Ctrl + S', desc: 'Lưu dự án / Lưu phụ đề' },
        { key: 'Ctrl + E', desc: 'Mở cửa sổ xuất video / phụ đề' },
        { key: '?', desc: 'Bật / Tắt bảng tra cứu phím tắt này' },
        { key: 'Esc', desc: 'Đóng cửa sổ / Thoát chế độ sửa' },
      ],
    },
  ];

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Bảng Tra Cứu Phím Tắt (Keyboard Shortcuts)" maxWidth="2xl">
      <div className="space-y-6 text-text-primary">
        <div className="flex items-center gap-2 p-3 bg-surface-raised/80 rounded-card border border-border/60 text-xs text-text-secondary">
          <Keyboard className="h-4 w-4 text-brand shrink-0" />
          <span>Mẹo: Bạn có thể nhấn phím <kbd className="px-1.5 py-0.5 bg-[#050711] border border-border rounded text-brand font-mono font-bold">?</kbd> bất cứ lúc nào khi không soạn thảo để mở nhanh bảng này.</span>
        </div>

        <div className="grid sm:grid-cols-1 gap-6">
          {shortcutGroups.map((group, idx) => (
            <div key={idx} className="space-y-2.5">
              <div className="flex items-center gap-2 text-xs font-bold text-text-secondary uppercase tracking-wider">
                {group.icon}
                <span>{group.category}</span>
              </div>
              <div className="bg-surface-raised/40 border border-border rounded-card divide-y divide-border/40 overflow-hidden">
                {group.shortcuts.map((sc, sIdx) => (
                  <div key={sIdx} className="flex items-center justify-between px-4 py-2.5 text-xs hover:bg-surface-raised/70 transition-colors">
                    <span className="text-text-secondary">{sc.desc}</span>
                    <kbd className="px-2 py-1 bg-[#050711] border border-border rounded-input text-brand font-mono font-semibold text-[11px] shadow-sm">
                      {sc.key}
                    </kbd>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div className="pt-2 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-surface-raised hover:bg-surface-raised/80 border border-border rounded-input text-xs font-semibold text-text-primary transition-colors"
          >
            Đã hiểu
          </button>
        </div>
      </div>
    </Modal>
  );
};

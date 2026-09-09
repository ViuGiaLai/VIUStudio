import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Modal } from '../common/Modal';
import { Button } from '../common/Button';
import { ProjectGoal } from '@viustudio/shared';
import { Film, BookOpen, Cpu, Globe, Sparkles, Mic } from 'lucide-react';
import { useAppStore } from '../../stores/useAppStore';
import { useToast } from '../../context/ToastContext';

export interface CreateProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const CreateProjectModal: React.FC<CreateProjectModalProps> = ({ isOpen, onClose }) => {
  const navigate = useNavigate();
  const toast = useToast();
  const { devices, activeDevice, createProject } = useAppStore();

  const [name, setName] = useState('');
  const [deviceId, setDeviceId] = useState(activeDevice?.device_id || 'dev_browser_client');
  const [sourceLang, setSourceLang] = useState('auto');
  const [targetLang, setTargetLang] = useState('vi');
  const [goal, setGoal] = useState<ProjectGoal>('Subtitles + voice');
  const [selectedPreset, setSelectedPreset] = useState<string | null>('recap');
  const [voicePersona, setVoicePersona] = useState('vais_male');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const presets = [
    {
      id: 'recap',
      name: 'Tóm Tắt Phim',
      icon: Film,
      source: 'en',
      target: 'vi',
      goal: 'Subtitles + voice' as ProjectGoal,
      placeholder: 'Tóm Tắt Phim: Kẻ Trừng Phạt (Full Recap)',
    },
    {
      id: 'manga',
      name: 'Review Truyện Tranh',
      icon: BookOpen,
      source: 'ja',
      target: 'vi',
      goal: 'Subtitles + voice' as ProjectGoal,
      placeholder: 'Review Truyện: Kiếm Sĩ Thần Thoại Tập 1',
    },
    {
      id: 'tech',
      name: 'Bản Tin AI / Tech',
      icon: Cpu,
      source: 'en',
      target: 'vi',
      goal: 'Subtitles + voice' as ProjectGoal,
      placeholder: 'Bản Tin AI 2026: Đột Phá Công Nghệ Mới',
    },
    {
      id: 'vlog',
      name: 'Vlog Đời Sống',
      icon: Globe,
      source: 'auto',
      target: 'vi',
      goal: 'Translated subtitles' as ProjectGoal,
      placeholder: 'Ký Sự Du Lịch Xứ Sở Hoa Anh Đào',
    },
  ];

  const handleSelectPreset = (p: typeof presets[0]) => {
    setSelectedPreset(p.id);
    setSourceLang(p.source);
    setTargetLang(p.target);
    setGoal(p.goal);
    if (!name || presets.some((x) => x.placeholder === name)) {
      setName(p.placeholder);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError('Vui lòng nhập tên cho dự án.');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const prj = await createProject({
        name: name.trim(),
        device_id: deviceId,
        source_lang: sourceLang,
        target_lang: targetLang,
        goal,
      });
      toast.success(`Đã khởi tạo dự án "${prj.name}" thành công!`);
      onClose();
      navigate(`/app/projects/${prj.id}/editor`);
    } catch (err: any) {
      setError(err.message || 'Không thể tạo dự án');
      toast.error(`Lỗi tạo dự án: ${err.message || 'Không xác định'}`);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Tạo Dự Án Recap Video Mới"
      description="Cấu hình ngôn ngữ, mục tiêu workflow và thiết bị xử lý âm thanh."
      maxWidth="lg"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="p-3 rounded-input bg-status-error/10 border border-status-error/30 text-xs text-status-error">
            {error}
          </div>
        )}

        {/* Quick Presets Selector */}
        <div>
          <label className="block text-xs font-semibold text-text-primary mb-1.5 flex items-center gap-1.5">
            <Sparkles className="h-3.5 w-3.5 text-brand" /> Mẫu dự án dựng sẵn (Presets)
          </label>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {presets.map((p) => {
              const Icon = p.icon;
              const isSelected = selectedPreset === p.id;
              return (
                <button
                  type="button"
                  key={p.id}
                  onClick={() => handleSelectPreset(p)}
                  className={`p-2.5 rounded-input border text-left transition-all flex flex-col gap-1.5 ${
                    isSelected
                      ? 'bg-brand/10 border-brand text-brand ring-1 ring-brand/30'
                      : 'bg-surface-raised border-border text-text-secondary hover:border-border-light'
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  <span className="text-xs font-bold truncate text-text-primary">{p.name}</span>
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <label className="block text-xs font-semibold text-text-primary mb-1">
            Tên dự án <span className="text-status-error">*</span>
          </label>
          <input
            type="text"
            required
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Ví dụ: Ký Sự Khám Phá Vũ Trụ Huyền Bí #01"
            className="w-full bg-surface-raised border border-border rounded-input px-3 py-2 text-xs text-text-primary focus:outline-none focus:border-brand"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold text-text-primary mb-1">
              Thiết bị thực thi (Companion)
            </label>
            <select
              value={deviceId}
              onChange={(e) => setDeviceId(e.target.value)}
              className="w-full bg-surface-raised border border-border rounded-input px-3 py-2 text-xs text-text-primary focus:outline-none focus:border-brand"
            >
              {devices.map((d) => (
                <option key={d.device_id} value={d.device_id}>
                  {d.name} ({d.ready_state})
                </option>
              ))}
              {devices.length === 0 && <option value="dev_browser_client">Trình Duyệt Web (WASM)</option>}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-primary mb-1">
              Mục tiêu đầu ra (Workflow Goal)
            </label>
            <select
              value={goal}
              onChange={(e) => setGoal(e.target.value as ProjectGoal)}
              className="w-full bg-surface-raised border border-border rounded-input px-3 py-2 text-xs text-text-primary focus:outline-none focus:border-brand"
            >
              <option value="Subtitles + voice">Phụ đề + Lồng tiếng AI (Đầy đủ)</option>
              <option value="Translated subtitles">Chỉ dịch phụ đề (SRT Subtitles Only)</option>
              <option value="Transcript only">Trích xuất kịch bản gốc (Transcript Only)</option>
              <option value="Voice only">Chỉ tạo tệp âm thanh lồng tiếng (Voice Only)</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold text-text-primary mb-1">
              Ngôn ngữ nguồn
            </label>
            <select
              value={sourceLang}
              onChange={(e) => setSourceLang(e.target.value)}
              className="w-full bg-surface-raised border border-border rounded-input px-3 py-2 text-xs text-text-primary focus:outline-none focus:border-brand"
            >
              <option value="auto">Tự động nhận diện</option>
              <option value="en">Tiếng Anh (EN)</option>
              <option value="ja">Tiếng Nhật (JA)</option>
              <option value="zh">Tiếng Trung (ZH)</option>
              <option value="vi">Tiếng Việt (VI)</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-primary mb-1">
              Ngôn ngữ đích (Bản dịch)
            </label>
            <select
              value={targetLang}
              onChange={(e) => setTargetLang(e.target.value)}
              className="w-full bg-surface-raised border border-border rounded-input px-3 py-2 text-xs text-text-primary focus:outline-none focus:border-brand"
            >
              <option value="vi">Tiếng Việt (VN)</option>
              <option value="en">Tiếng Anh (EN)</option>
            </select>
          </div>
        </div>

        {/* Default Dubbing Voice Persona */}
        {goal.includes('voice') && (
          <div className="pt-2 border-t border-border">
            <label className="block text-xs font-semibold text-text-primary mb-1 flex items-center gap-1.5">
              <Mic className="h-3.5 w-3.5 text-brand" /> Giọng đọc lồng tiếng mặc định
            </label>
            <select
              value={voicePersona}
              onChange={(e) => setVoicePersona(e.target.value)}
              className="w-full bg-surface-raised border border-border rounded-input px-3 py-2 text-xs text-text-primary focus:outline-none focus:border-brand"
            >
              <option value="vais_male">Piper VAIS - Nam truyền cảm (Trầm ấm, recap phim)</option>
              <option value="vais_female">Piper VAIS - Nữ tự nhiên (Rõ ràng, tin tức & vlog)</option>
              <option value="kokoro_sarah">Kokoro - Sarah (English US Storytelling)</option>
              <option value="kokoro_michael">Kokoro - Michael (English US Documentary)</option>
            </select>
          </div>
        )}

        <div className="pt-4 border-t border-border flex items-center justify-end gap-3">
          <Button type="button" variant="ghost" onClick={onClose} disabled={isLoading}>
            Hủy bỏ
          </Button>
          <Button type="submit" variant="primary" isLoading={isLoading}>
            Tạo Dự Án & Mở Editor →
          </Button>
        </div>
      </form>
    </Modal>
  );
};


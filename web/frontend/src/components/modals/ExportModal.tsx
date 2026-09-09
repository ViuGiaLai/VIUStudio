import React, { useState, useMemo } from 'react';
import { Modal } from '../common/Modal';
import { Button } from '../common/Button';
import { Project } from '@viustudio/shared';
import { Film, CheckCircle2, AlertCircle, Zap, HardDrive, Music, Mic, Volume2 } from 'lucide-react';
import { useAppStore } from '../../stores/useAppStore';
import { useToast } from '../../context/ToastContext';

export interface ExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  project: Project;
  onExportStarted: (jobId: string) => void;
}

export const ExportModal: React.FC<ExportModalProps> = ({
  isOpen,
  onClose,
  project,
  onExportStarted,
}) => {
  const { createJob, activeDevice } = useAppStore();
  const toast = useToast();

  const [outputName, setOutputName] = useState(
    project.export_settings?.output_name || `${project.name.replace(/\s+/g, '_')}_Export.mp4`
  );
  const [resolution, setResolution] = useState(project.export_settings?.resolution || '1080p');
  const [fps, setFps] = useState(project.export_settings?.fps || 30);
  const [preset, setPreset] = useState(project.export_settings?.preset || 'Balanced');
  const [encoder, setEncoder] = useState(activeDevice?.hardware.has_gpu_acceleration ? 'h264_nvenc' : 'libx264');
  const [bitrateMode, setBitrateMode] = useState<'Auto' | 'Custom'>('Auto');
  const [bitrateKbps, setBitrateKbps] = useState(project.export_settings?.video_bitrate_kbps || 2800);
  const [burnSubtitles, setBurnSubtitles] = useState(project.export_settings?.burn_subtitles ?? true);
  const [includeDubVoice, setIncludeDubVoice] = useState(true);
  const [includeMusicStem, setIncludeMusicStem] = useState(true);
  const [includeOriginalAudio, setIncludeOriginalAudio] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  // Dynamic file size calculation
  const estimatedSizeMb = useMemo(() => {
    const durationSec = (project.duration_ms || 45000) / 1000;
    const totalBitrate = bitrateKbps + 192; // audio bitrate
    const sizeBytes = (durationSec * totalBitrate * 1000) / 8;
    return (sizeBytes / (1024 * 1024)).toFixed(1);
  }, [project.duration_ms, bitrateKbps]);

  const handleExport = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      const job = await createJob({
        project_id: project.id,
        device_id: project.device_id || activeDevice?.device_id || 'dev_browser_client',
        type: 'export',
        input_revision: project.revision,
        params: {
          output_name: outputName,
          resolution,
          fps,
          preset,
          video_bitrate_kbps: bitrateKbps,
          burn_subtitles: burnSubtitles,
          encoder,
          audio_tracks: [
            ...(includeDubVoice ? ['t_dub'] : []),
            ...(includeMusicStem ? ['t_music'] : []),
            ...(includeOriginalAudio ? ['t_orig'] : []),
          ],
        },
      });

      toast.success(`Đã khởi chạy tác vụ xuất video #${job.id} qua NVIDIA NVENC!`);
      onExportStarted(job.id);
      onClose();
    } catch (err: any) {
      toast.error(`Khởi chạy export thất bại: ${err.message || 'Lỗi không xác định'}`);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Xuất Bản Video (Export Video)"
      description={`Khóa render cố định theo Project Revision #${project.revision}`}
      maxWidth="lg"
    >
      <form onSubmit={handleExport} className="space-y-4">
        <div>
          <label className="block text-xs font-semibold text-text-primary mb-1">
            Tên file video đầu ra
          </label>
          <input
            type="text"
            required
            value={outputName}
            onChange={(e) => setOutputName(e.target.value)}
            className="w-full bg-surface-raised border border-border rounded-input px-3 py-2 text-xs text-text-primary focus:outline-none focus:border-brand font-mono"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold text-text-primary mb-1">
              Độ phân giải (Resolution)
            </label>
            <select
              value={resolution}
              onChange={(e) => setResolution(e.target.value as any)}
              className="w-full bg-surface-raised border border-border rounded-input px-3 py-2 text-xs text-text-primary focus:outline-none focus:border-brand"
            >
              <option value="1080p">1080p Full HD (1920x1080)</option>
              <option value="720p">720p HD (1280x720)</option>
              <option value="4k">4K Ultra HD (3840x2160)</option>
              <option value="source">Giữ nguyên gốc (Match Source)</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-primary mb-1">
              Khung hình mỗi giây (FPS)
            </label>
            <select
              value={fps}
              onChange={(e) => setFps(Number(e.target.value))}
              className="w-full bg-surface-raised border border-border rounded-input px-3 py-2 text-xs text-text-primary focus:outline-none focus:border-brand"
            >
              <option value={24}>24 fps (Điện ảnh Cinematic)</option>
              <option value={30}>30 fps (Tiêu chuẩn Video)</option>
              <option value={60}>60 fps (Mượt mà High-motion)</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold text-text-primary mb-1">
              Phần cứng Encode (Encoder)
            </label>
            <select
              value={encoder}
              onChange={(e) => setEncoder(e.target.value)}
              className="w-full bg-surface-raised border border-border rounded-input px-3 py-2 text-xs text-text-primary focus:outline-none focus:border-brand"
            >
              <option value="h264_nvenc">NVIDIA NVENC H.264 (Cực nhanh)</option>
              <option value="hevc_nvenc">NVIDIA NVENC HEVC/H.265 (Tiết kiệm)</option>
              <option value="libx264">CPU Software x264 (Tương thích cao)</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-text-primary mb-1">
              Chế độ chất lượng
            </label>
            <select
              value={preset}
              onChange={(e) => setPreset(e.target.value as any)}
              className="w-full bg-surface-raised border border-border rounded-input px-3 py-2 text-xs text-text-primary focus:outline-none focus:border-brand"
            >
              <option value="Fast">Fast (NVENC Nhanh)</option>
              <option value="Balanced">Balanced (Cân bằng chuẩn)</option>
              <option value="Maximum quality">Maximum Quality (Cao cấp)</option>
            </select>
          </div>
        </div>

        {/* Video Bitrate Control */}
        <div>
          <label className="block text-xs font-semibold text-text-primary mb-1">
            Video Bitrate ({bitrateKbps} kbps)
          </label>
          <div className="flex gap-2">
            <select
              value={bitrateMode}
              onChange={(e) => {
                setBitrateMode(e.target.value as any);
                if (e.target.value === 'Auto') setBitrateKbps(2800);
              }}
              className="w-1/2 bg-surface-raised border border-border rounded-input px-2.5 py-2 text-xs text-text-primary focus:outline-none focus:border-brand"
            >
              <option value="Auto">Tự động (Khuyên dùng: 2800 kbps)</option>
              <option value="Custom">Tùy chỉnh thủ công</option>
            </select>
            {bitrateMode === 'Custom' && (
              <input
                type="number"
                min={1000}
                max={50000}
                step={500}
                value={bitrateKbps}
                onChange={(e) => setBitrateKbps(Number(e.target.value))}
                placeholder="kbps"
                className="w-1/2 bg-surface-raised border border-border rounded-input px-3 py-2 text-xs text-text-primary font-mono focus:border-brand"
              />
            )}
          </div>
        </div>

        {/* Audio Stems Selection */}
        <div className="pt-2 border-t border-border space-y-2">
          <label className="block text-xs font-semibold text-text-primary">
            Kênh âm thanh đưa vào bản xuất
          </label>
          <div className="grid grid-cols-3 gap-2 text-xs">
            <label className={`flex items-center gap-2 p-2 rounded-input border cursor-pointer transition-colors ${includeDubVoice ? 'bg-brand/10 border-brand/40 text-text-primary' : 'bg-surface-raised border-border text-text-muted'}`}>
              <input
                type="checkbox"
                checked={includeDubVoice}
                onChange={(e) => setIncludeDubVoice(e.target.checked)}
                className="rounded border-border text-brand focus:ring-accent-focus"
              />
              <span className="truncate">Giọng đọc (Dub)</span>
            </label>

            <label className={`flex items-center gap-2 p-2 rounded-input border cursor-pointer transition-colors ${includeMusicStem ? 'bg-brand/10 border-brand/40 text-text-primary' : 'bg-surface-raised border-border text-text-muted'}`}>
              <input
                type="checkbox"
                checked={includeMusicStem}
                onChange={(e) => setIncludeMusicStem(e.target.checked)}
                className="rounded border-border text-brand focus:ring-accent-focus"
              />
              <span className="truncate">Nhạc nền (Demucs)</span>
            </label>

            <label className={`flex items-center gap-2 p-2 rounded-input border cursor-pointer transition-colors ${includeOriginalAudio ? 'bg-brand/10 border-brand/40 text-text-primary' : 'bg-surface-raised border-border text-text-muted'}`}>
              <input
                type="checkbox"
                checked={includeOriginalAudio}
                onChange={(e) => setIncludeOriginalAudio(e.target.checked)}
                className="rounded border-border text-brand focus:ring-accent-focus"
              />
              <span className="truncate">Âm thanh gốc</span>
            </label>
          </div>
        </div>

        {/* Burn Subtitles Option */}
        <div className="flex items-center gap-2.5 pt-1">
          <input
            type="checkbox"
            id="burnSub"
            checked={burnSubtitles}
            onChange={(e) => setBurnSubtitles(e.target.checked)}
            className="rounded border-border text-brand focus:ring-accent-focus"
          />
          <label htmlFor="burnSub" className="text-xs text-text-primary cursor-pointer select-none">
            In cứng phụ đề vào khung hình video (Hardsub burn-in với kiểu dáng đã chọn)
          </label>
        </div>

        {/* Output Summary Card */}
        <div className="rounded-input bg-surface-raised border border-border p-3.5 space-y-1.5 text-xs text-text-secondary">
          <div className="font-bold text-text-primary mb-1 flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <Zap className="h-3.5 w-3.5 text-brand" />
              <span>Tóm tắt thông số xuất</span>
            </span>
            <span className="font-mono text-brand font-semibold">~{estimatedSizeMb} MB</span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-[11px]">
            <div>• Máy render: <strong className="text-text-primary">{project.device_name || 'Chưa chọn thiết bị'}</strong></div>
            <div>• Revision: <strong className="text-text-primary">#{project.revision}</strong></div>
            <div>• Độ phân giải: <strong className="text-text-primary">{resolution} @ {fps}fps</strong></div>
            <div>• Encoder: <strong className="text-text-primary">{encoder}</strong></div>
          </div>
        </div>

        <div className="pt-4 border-t border-border flex items-center justify-end gap-3">
          <Button type="button" variant="ghost" onClick={onClose} disabled={isLoading}>
            Hủy bỏ
          </Button>
          <Button type="submit" variant="primary" isLoading={isLoading}>
            <Film className="h-4 w-4 mr-1.5" />
            <span>Bắt đầu Render Video</span>
          </Button>
        </div>
      </form>
    </Modal>
  );
};

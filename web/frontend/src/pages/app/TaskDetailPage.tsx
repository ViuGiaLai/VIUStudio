import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Laptop,
  Clock,
  CheckCircle2,
  AlertCircle,
  Copy,
  Check,
  Ban,
  FileCheck,
  Terminal,
  Download,
  Search,
  Filter,
  Layers,
  Cpu,
  Mic,
  Music,
  Languages,
  Video,
  ChevronRight,
} from 'lucide-react';
import { Job } from '@viustudio/shared';
import { useAppStore } from '../../stores/useAppStore';
import { Button } from '../../components/common/Button';
import { StatusBadge } from '../../components/common/StatusBadge';
import { ProgressBar } from '../../components/common/ProgressBar';
import { useToast } from '../../context/ToastContext';

export const TaskDetailPage: React.FC = () => {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const toast = useToast();
  const { activeJobs, cancelJob, activeDevice } = useAppStore();
  const [copiedError, setCopiedError] = useState(false);
  const [logFilter, setLogFilter] = useState<'all' | 'info' | 'warn' | 'error'>('all');
  const [logSearch, setLogSearch] = useState('');
  const [copiedLogs, setCopiedLogs] = useState(false);

  const job = activeJobs.find((j) => j.id === jobId) || null;

  const handleCancel = async () => {
    if (!jobId || !confirm('Bạn có chắc muốn hủy tác vụ này?')) return;
    await cancelJob(jobId);
    toast.warning(`Đã gửi lệnh dừng tác vụ #${jobId}`);
  };

  const handleCopyError = () => {
    if (!job?.error) return;
    navigator.clipboard.writeText(JSON.stringify(job.error, null, 2));
    setCopiedError(true);
    toast.info('Đã sao chép chi tiết lỗi');
    setTimeout(() => setCopiedError(false), 2000);
  };

  if (!job) {
    return (
      <div className="p-12 text-center space-y-3">
        <h2 className="text-base font-bold text-text-primary">Không tìm thấy tác vụ #{jobId}</h2>
        <Button variant="secondary" size="sm" onClick={() => navigate('/app/tasks')}>
          Quay lại danh sách tác vụ
        </Button>
      </div>
    );
  }

  const isRunning = ['Queued', 'Waiting for device', 'Preparing', 'Running', 'Finalizing'].includes(
    job.state
  );

  const stepsByType: Partial<Record<Job['type'], Array<{ id: string; label: string; icon: typeof Layers; threshold: number }>>> = {
    transcribe: [
      { id: 'extract', label: 'Đọc âm thanh', icon: Layers, threshold: 20 },
      { id: 'whisper', label: 'Nhận diện', icon: Mic, threshold: 80 },
      { id: 'subtitle', label: 'Ghi phụ đề', icon: Languages, threshold: 100 },
    ],
    separation: [
      { id: 'decode', label: 'Đọc âm thanh', icon: Layers, threshold: 20 },
      { id: 'demucs', label: 'Tách nguồn', icon: Music, threshold: 85 },
      { id: 'write', label: 'Ghi tệp', icon: Download, threshold: 100 },
    ],
    tts: [
      { id: 'prepare', label: 'Chuẩn bị câu', icon: Layers, threshold: 20 },
      { id: 'piper', label: 'Tổng hợp giọng', icon: Cpu, threshold: 85 },
      { id: 'write', label: 'Ghi âm thanh', icon: Download, threshold: 100 },
    ],
    export: [
      { id: 'prepare', label: 'Chuẩn bị', icon: Layers, threshold: 20 },
      { id: 'render', label: 'Xuất video', icon: Video, threshold: 90 },
      { id: 'finalize', label: 'Hoàn tất', icon: FileCheck, threshold: 100 },
    ],
  };
  const pipelineSteps = stepsByType[job.type] || [
    { id: 'prepare', label: 'Chuẩn bị', icon: Layers, threshold: 25 },
    { id: 'process', label: 'Xử lý', icon: Cpu, threshold: 85 },
    { id: 'finish', label: 'Hoàn tất', icon: FileCheck, threshold: 100 },
  ];

  const currentProgress = job.state === 'Completed' ? 100 : job.progress && job.progress.total > 0
    ? Math.max(0, Math.min(100, Math.round(job.progress.current / job.progress.total * 100))) : 0;

  const baseLogs = [
    `[${new Date(job.created_at).toLocaleTimeString()}] [INFO] Khởi tạo tác vụ [${job.type.toUpperCase()}] trên ${job.device_name || 'thiết bị chưa xác định'}`,
    `[${new Date(job.updated_at).toLocaleTimeString()}] [INFO] Trạng thái: ${job.state}`,
    ...(job.progress ? [`[${new Date(job.progress.timestamp).toLocaleTimeString()}] [INFO] ${job.progress.stage} · ${job.progress.current}/${job.progress.total} ${job.progress.unit}`] : []),
    ...(job.progress?.message ? [`[${new Date(job.progress.timestamp).toLocaleTimeString()}] [INFO] ${job.progress.message}`] : []),
    ...(job.progress?.speed ? [`[${new Date(job.progress.timestamp).toLocaleTimeString()}] [INFO] Tốc độ: ${job.progress.speed}`] : []),
    job.state === 'Completed'
      ? `[${new Date().toLocaleTimeString()}] [SUCCESS] Hoàn thành tác vụ thành công. File kết quả đã sẵn sàng.`
      : job.state === 'Cancelled'
      ? `[${new Date().toLocaleTimeString()}] [WARN] Người dùng đã hủy bỏ tác vụ.`
      : job.state === 'Failed'
      ? `[${new Date().toLocaleTimeString()}] [ERROR] Tác vụ dừng do lỗi thực thi.`
      : `[${new Date(job.updated_at).toLocaleTimeString()}] [INFO] Đang chờ cập nhật tiếp theo từ thiết bị xử lý.`,
  ];

  const filteredLogs = baseLogs.filter((log) => {
    const matchFilter =
      logFilter === 'all' ||
      (logFilter === 'info' && log.includes('[INFO]')) ||
      (logFilter === 'warn' && log.includes('[WARN]')) ||
      (logFilter === 'error' && log.includes('[ERROR]'));
    const matchSearch = !logSearch || log.toLowerCase().includes(logSearch.toLowerCase());
    return matchFilter && matchSearch;
  });

  const handleCopyLogs = () => {
    navigator.clipboard.writeText(baseLogs.join('\n'));
    setCopiedLogs(true);
    toast.success('Đã sao chép toàn bộ nhật ký console');
    setTimeout(() => setCopiedLogs(false), 2000);
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate('/app/tasks')}
          className="p-1.5 rounded-input text-text-secondary hover:text-text-primary hover:bg-surface-raised"
          title="Quay lại"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div>
          <h1 className="text-xl font-bold text-text-primary flex items-center gap-2.5">
            <span>Chi tiết tác vụ #{job.id}</span>
            <StatusBadge status={job.state} size="sm" />
          </h1>
          <p className="text-xs text-text-secondary mt-0.5">
            {job.project_name || 'Tác vụ độc lập'} · Loại: {job.type.toUpperCase()}
          </p>
        </div>
      </div>

      {/* Visual Pipeline Flowchart */}
      <div className="rounded-card border border-border bg-surface p-5 shadow-sm space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold text-text-primary uppercase tracking-wider flex items-center gap-2">
            <Layers className="h-4 w-4 text-brand" /> Sơ Đồ Pipeline Xử Lý (AI Flowchart)
          </span>
          <span className="text-xs font-mono text-brand font-semibold">{currentProgress}% hoàn tất</span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-6 gap-2 pt-2">
          {pipelineSteps.map((step, idx) => {
            const StepIcon = step.icon;
            const isDone = job.state === 'Completed';
            const isActive = !isDone && isRunning && job.progress?.stage === step.id;

            return (
              <div
                key={step.id}
                className={`p-3 rounded-card border transition-all relative flex flex-col items-center text-center gap-1.5 ${
                  isDone
                    ? 'bg-brand/10 border-brand/35 text-brand shadow-[0_0_12px_rgba(77,232,225,0.08)]'
                    : isActive
                    ? 'bg-surface-raised border-accent-focus/50 text-accent-focus ring-1 ring-accent-focus/30 animate-pulse'
                    : 'bg-surface-raised/50 border-border text-text-muted opacity-50'
                }`}
              >
                <StepIcon className="h-5 w-5" />
                <span className="text-[11px] font-bold leading-tight line-clamp-1">{step.label}</span>
                <span className="text-[10px] font-mono">
                  {isDone ? '✓ Hoàn thành' : isActive ? '⚡ Đang chạy' : 'Chờ'}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Main Status Card */}
      <div className="rounded-card border border-border bg-surface p-6 shadow-sm space-y-5">
        <div className="flex items-center justify-between pb-4 border-b border-border">
          <div className="space-y-1">
            <span className="text-[11px] font-bold text-text-muted uppercase tracking-wider">
              Thiết bị thực thi
            </span>
            <div className="flex items-center gap-2 text-sm font-bold text-text-primary">
              <Laptop className="h-4 w-4 text-brand" />
              <span>{job.device_name || activeDevice?.name || 'Trình duyệt Web (WASM)'}</span>
            </div>
          </div>

          {isRunning && (
            <Button variant="danger" size="sm" onClick={handleCancel}>
              <Ban className="h-3.5 w-3.5 mr-1.5" />
              <span>Hủy tác vụ</span>
            </Button>
          )}
        </div>

        {/* Progress Display */}
        {job.progress && (
          <div className="space-y-2">
            <ProgressBar
              progress={job.progress.current}
              stage={job.progress.stage}
              message={job.progress.message}
              speed={job.progress.speed}
              etaSeconds={job.progress.eta_seconds}
            />
          </div>
        )}

        {/* Output Artifacts */}
        {job.artifacts && job.artifacts.length > 0 && (
          <div className="pt-4 border-t border-border space-y-2.5">
            <h3 className="text-xs font-bold text-text-primary uppercase tracking-wider">
              File kết quả (Output Artifacts)
            </h3>
            <div className="space-y-2">
              {job.artifacts.map((art) => (
                <div
                  key={art.id}
                  className="flex items-center justify-between p-3.5 rounded-input bg-surface-raised border border-border text-xs"
                >
                  <div className="flex items-center gap-2.5">
                    <FileCheck className="h-5 w-5 text-brand" />
                    <div>
                      <div className="font-bold text-text-primary">{art.file_name}</div>
                      <div className="text-[11px] text-text-muted">
                        {art.size_bytes ? `${(art.size_bytes / (1024 * 1024)).toFixed(1)} MB · ` : ''}
                        {art.availability}
                      </div>
                    </div>
                  </div>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={!art.download_url}
                    onClick={() => {
                      if (!art.download_url) {
                        toast.error('Không thể tải trực tiếp', 'Tệp chỉ tồn tại trên thiết bị xử lý.');
                        return;
                      }
                      const anchor = document.createElement('a');
                      const url = new URL(art.download_url, window.location.origin);
                      if (!['https:', 'http:', 'blob:'].includes(url.protocol)) {
                        toast.error('Đường dẫn tải không hợp lệ');
                        return;
                      }
                      anchor.href = url.href;
                      anchor.download = art.file_name;
                      anchor.rel = 'noopener';
                      anchor.click();
                    }}
                  >
                    <Download className="h-3.5 w-3.5 mr-1" />
                    <span>Tải file</span>
                  </Button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Enhanced Console Logs Stream with Search & Level Filtering */}
        <div className="pt-4 border-t border-border space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
            <div className="flex items-center gap-1.5 text-xs font-bold text-text-primary uppercase tracking-wider">
              <Terminal className="h-4 w-4 text-brand" />
              <span>Nhật ký tiến trình (Live Console Logs)</span>
            </div>

            <div className="flex items-center gap-2">
              {/* Level Filter */}
              <div className="flex items-center gap-1 bg-surface-raised border border-border rounded-input p-0.5 text-[11px]">
                {(['all', 'info', 'warn', 'error'] as const).map((lvl) => (
                  <button
                    key={lvl}
                    onClick={() => setLogFilter(lvl)}
                    className={`px-2 py-0.5 rounded uppercase font-semibold transition-colors ${
                      logFilter === lvl
                        ? 'bg-brand/20 text-brand'
                        : 'text-text-muted hover:text-text-primary'
                    }`}
                  >
                    {lvl}
                  </button>
                ))}
              </div>

              {/* Search */}
              <div className="relative">
                <input
                  type="text"
                  placeholder="Lọc log..."
                  value={logSearch}
                  onChange={(e) => setLogSearch(e.target.value)}
                  className="bg-surface-raised border border-border rounded-input px-2.5 py-1 text-xs text-text-primary w-28 focus:w-36 transition-all focus:border-brand"
                />
              </div>

              <Button variant="ghost" size="sm" onClick={handleCopyLogs}>
                {copiedLogs ? <Check className="h-3.5 w-3.5 text-status-success" /> : <Copy className="h-3.5 w-3.5" />}
              </Button>
            </div>
          </div>

          <div className="p-3.5 rounded-input bg-[#0a0f18] border border-border font-mono text-xs text-[#c9d1d9] space-y-1.5 max-h-56 overflow-y-auto select-text scrollbar-thin">
            {filteredLogs.length === 0 ? (
              <div className="text-text-muted text-center py-3 italic">Không có dòng log nào khớp bộ lọc.</div>
            ) : (
              filteredLogs.map((log, idx) => {
                const isErr = log.includes('[ERROR]');
                const isWarn = log.includes('[WARN]');
                const isSuccess = log.includes('[SUCCESS]');
                return (
                  <div key={idx} className="leading-relaxed flex items-start gap-2 hover:bg-white/5 px-1 rounded">
                    <span className="text-text-muted select-none text-[11px]">{idx + 1}</span>
                    <span
                      className={
                        isErr
                          ? 'text-status-error'
                          : isWarn
                          ? 'text-accent-focus'
                          : isSuccess
                          ? 'text-status-success'
                          : 'text-[#c9d1d9]'
                      }
                    >
                      {log}
                    </span>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Error Details */}
        {job.error && (
          <div className="pt-4 border-t border-border space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-status-error uppercase tracking-wider">
                Lỗi thực thi
              </span>
              <Button variant="ghost" size="sm" onClick={handleCopyError}>
                {copiedError ? <Check className="h-3.5 w-3.5 mr-1 text-status-success" /> : <Copy className="h-3.5 w-3.5 mr-1" />}
                <span>{copiedError ? 'Đã sao chép' : 'Sao chép chi tiết lỗi'}</span>
              </Button>
            </div>
            <div className="p-3 rounded-input bg-status-error/10 border border-status-error/30 text-xs text-status-error font-mono">
              <div>[{job.error.code}] {job.error.message}</div>
              {job.error.details && <div className="mt-1 text-[11px] opacity-80">{job.error.details}</div>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

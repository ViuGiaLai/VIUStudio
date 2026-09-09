import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ListTodo,
  RefreshCw,
  XCircle,
  ArrowRight,
  Laptop,
  Clock,
  Plus,
  Zap,
  Search,
  CheckCircle2,
  AlertTriangle,
  PlayCircle,
} from 'lucide-react';
import { useAppStore } from '../../stores/useAppStore';
import { Button } from '../../components/common/Button';
import { StatusBadge } from '../../components/common/StatusBadge';
import { ProgressBar } from '../../components/common/ProgressBar';
import { useToast } from '../../context/ToastContext';

export const TasksPage: React.FC = () => {
  const navigate = useNavigate();
  const toast = useToast();
  const { activeJobs, refreshJobs, createJob, createProject, projects, activeDevice, companionStatus } = useAppStore();
  const [filter, setFilter] = useState<'all' | 'active' | 'completed' | 'failed'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [isRefreshing, setIsRefreshing] = useState(false);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await refreshJobs();
    setIsRefreshing(false);
    toast.info('Đã cập nhật danh sách tác vụ');
  };

  const handleStartTestJob = async () => {
    if (!companionStatus?.online) {
      toast.error('Không thể chạy tác vụ: VIUStudio Companion chưa kết nối.');
      return;
    }
    try {
    let prj = projects[0];
    if (!prj) {
      prj = await createProject({
        name: 'Dự án Render Thử Nghiệm',
        device_id: activeDevice?.device_id || 'dev_browser_client',
        source_lang: 'vi',
        target_lang: 'vi',
        goal: 'Subtitles + voice',
      });
    }
    await createJob({
      project_id: prj.id,
      device_id: activeDevice?.device_id || 'dev_browser_client',
      type: 'export',
      input_revision: 1,
      params: {
        output_name: `${prj.name.replace(/\s+/g, '_')}_Render.mp4`,
        resolution: '1080p',
        fps: 30,
        preset: 'Fast',
      },
    });
    toast.success('Đã khởi chạy tác vụ thử nghiệm thành công');
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Không thể khởi chạy tác vụ.');
    }
  };

  const runningCount = activeJobs.filter((j) =>
    ['Queued', 'Waiting for device', 'Preparing', 'Running', 'Finalizing'].includes(j.state)
  ).length;
  const completedCount = activeJobs.filter((j) => j.state === 'Completed').length;
  const failedCount = activeJobs.filter((j) =>
    ['Failed', 'Cancelled', 'Interrupted'].includes(j.state)
  ).length;

  const filteredJobs = activeJobs.filter((job) => {
    if (filter === 'active') {
      if (!['Queued', 'Waiting for device', 'Preparing', 'Running', 'Finalizing'].includes(job.state)) {
        return false;
      }
    } else if (filter === 'completed') {
      if (job.state !== 'Completed') return false;
    } else if (filter === 'failed') {
      if (!['Failed', 'Cancelled', 'Interrupted'].includes(job.state)) return false;
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchName = job.project_name?.toLowerCase().includes(q);
      const matchId = job.id.toLowerCase().includes(q);
      const matchType = job.type.toLowerCase().includes(q);
      return matchName || matchId || matchType;
    }

    return true;
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black text-text-primary tracking-tight">Hàng Đợi & Tiến Độ Tác Vụ</h1>
          <p className="text-xs text-text-secondary mt-1">
            Theo dõi quá trình kết xuất video, tách nhạc Demucs và tổng hợp giọng nói đang chạy trên Companion.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <Button variant="secondary" size="sm" onClick={handleStartTestJob}>
            <Zap className="h-3.5 w-3.5 mr-1.5 text-brand" />
            <span>Chạy tác vụ thử nghiệm</span>
          </Button>

          <Button variant="secondary" size="sm" onClick={handleRefresh} isLoading={isRefreshing}>
            <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
            <span>Làm mới</span>
          </Button>
        </div>
      </div>

      {/* Summary Metrics Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="rounded-card bg-surface border border-border p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-card bg-brand/10 border border-brand/20 flex items-center justify-center text-brand">
            <ListTodo className="h-5 w-5" />
          </div>
          <div>
            <div className="text-xs text-text-muted">Tổng số tác vụ</div>
            <div className="text-lg font-black font-mono text-text-primary">{activeJobs.length}</div>
          </div>
        </div>

        <div className="rounded-card bg-surface border border-border p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-card bg-accent-focus/10 border border-accent-focus/20 flex items-center justify-center text-accent-focus">
            <PlayCircle className="h-5 w-5 animate-pulse" />
          </div>
          <div>
            <div className="text-xs text-text-muted">Đang xử lý</div>
            <div className="text-lg font-black font-mono text-accent-focus">{runningCount}</div>
          </div>
        </div>

        <div className="rounded-card bg-surface border border-border p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-card bg-status-success/10 border border-status-success/20 flex items-center justify-center text-status-success">
            <CheckCircle2 className="h-5 w-5" />
          </div>
          <div>
            <div className="text-xs text-text-muted">Đã hoàn thành</div>
            <div className="text-lg font-black font-mono text-status-success">{completedCount}</div>
          </div>
        </div>

        <div className="rounded-card bg-surface border border-border p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-card bg-status-error/10 border border-status-error/20 flex items-center justify-center text-status-error">
            <AlertTriangle className="h-5 w-5" />
          </div>
          <div>
            <div className="text-xs text-text-muted">Lỗi / Đã hủy</div>
            <div className="text-lg font-black font-mono text-status-error">{failedCount}</div>
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border pb-3">
        <div className="flex items-center gap-2 text-xs overflow-x-auto">
          {[
            { id: 'all', label: 'Tất cả tác vụ', count: activeJobs.length },
            { id: 'active', label: 'Đang xử lý', count: runningCount },
            { id: 'completed', label: 'Đã hoàn thành', count: completedCount },
            { id: 'failed', label: 'Lỗi / Đã hủy', count: failedCount },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setFilter(tab.id as any)}
              className={`px-3.5 py-1.5 rounded-input font-semibold transition-colors flex items-center gap-2 whitespace-nowrap ${
                filter === tab.id
                  ? 'bg-brand/15 text-brand border border-brand/30'
                  : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              <span>{tab.label}</span>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-surface-raised border border-border">
                {tab.count}
              </span>
            </button>
          ))}
        </div>

        <div className="relative">
          <Search className="h-3.5 w-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            placeholder="Tìm theo tên hoặc ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="bg-surface border border-border rounded-input pl-8 pr-3 py-1.5 text-xs text-text-primary placeholder:text-text-muted focus:border-brand w-full sm:w-60"
          />
        </div>
      </div>

      {/* Tasks List */}
      {filteredJobs.length === 0 ? (
        <div className="rounded-card border border-border bg-surface p-12 text-center space-y-3">
          <ListTodo className="h-12 w-12 text-text-muted mx-auto opacity-40" />
          <h3 className="text-sm font-bold text-text-primary">Không có tác vụ nào phù hợp</h3>
          <p className="text-xs text-text-secondary max-w-sm mx-auto">
            Thử thay đổi bộ lọc tìm kiếm hoặc khởi chạy tác vụ thử nghiệm để xem quy trình hoạt động.
          </p>
          <Button variant="secondary" size="sm" onClick={handleStartTestJob}>
            <Zap className="h-3.5 w-3.5 mr-1.5 text-brand" />
            <span>Khởi chạy tác vụ mẫu</span>
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredJobs.map((job) => (
            <div
              key={job.id}
              onClick={() => navigate(`/app/tasks/${job.id}`)}
              className="rounded-card border border-border bg-surface p-5 hover:border-brand/40 transition-all cursor-pointer shadow-sm space-y-3.5 group"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
                <div className="flex items-center gap-2.5">
                  <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-brand px-2 py-0.5 rounded bg-brand/10 border border-brand/25">
                    {job.type}
                  </span>
                  <h3 className="text-sm font-bold text-text-primary group-hover:text-brand transition-colors">
                    {job.project_name || 'Tác vụ độc lập'}
                  </h3>
                </div>

                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1.5 text-xs text-text-muted">
                    <Laptop className="h-3.5 w-3.5" />
                    <span>{job.device_name || 'Thiết bị chưa xác định'}</span>
                  </div>
                  <StatusBadge status={job.state} size="sm" />
                </div>
              </div>

              {/* Progress Bar */}
              {job.progress && (
                <ProgressBar
                  progress={job.progress.current}
                  stage={job.progress.stage}
                  message={job.progress.message}
                  speed={job.progress.speed}
                  etaSeconds={job.progress.eta_seconds}
                />
              )}

              <div className="flex items-center justify-between pt-2 border-t border-border/60 text-[11px] text-text-muted">
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  <span>Khởi tạo: {new Date(job.created_at).toLocaleTimeString('vi-VN')}</span>
                </span>

                <span className="inline-flex items-center gap-1 text-brand font-semibold group-hover:underline">
                  <span>Xem chi tiết nhật ký</span>
                  <ArrowRight className="h-3 w-3" />
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

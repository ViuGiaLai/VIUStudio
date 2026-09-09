import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Laptop,
  FolderKanban,
  ListTodo,
  Plus,
  ArrowRight,
  Clock,
  Sparkles,
  Subtitles,
  Mic,
  Music,
  Zap,
  CheckCircle2,
  HardDrive,
  Cpu,
  RefreshCw,
  Activity,
  FileCode,
} from 'lucide-react';
import { useAppStore } from '../../stores/useAppStore';
import { Button } from '../../components/common/Button';
import { StatusBadge } from '../../components/common/StatusBadge';
import { ProgressBar } from '../../components/common/ProgressBar';
import { useToast } from '../../context/ToastContext';

export const OverviewPage: React.FC = () => {
  const navigate = useNavigate();
  const toast = useToast();
  const {
    activeDevice,
    projects,
    activeJobs,
    companionStatus,
    probeCompanion,
    loadSampleDemoProject,
  } = useAppStore();

  const [isProbing, setIsProbing] = useState(false);

  const handleProbe = async () => {
    setIsProbing(true);
    try {
      const res = await probeCompanion();
      if (res.online) {
        toast.success('Companion Online', `Kết nối thành công! Ping: ${res.ping_ms}ms`);
      } else {
        toast.info(
          'Companion chưa chạy',
          'Web đang chạy chế độ Trình duyệt (WASM). Hãy mở terminal chạy: python -m app.remote_api_server'
        );
      }
    } finally {
      setIsProbing(false);
    }
  };

  const runningTasks = activeJobs
    .filter((j) => ['Queued', 'Waiting for device', 'Preparing', 'Running'].includes(j.state))
    .slice(0, 3);

  const recentProjects = projects.slice(0, 6);

  const quickTools = [
    {
      title: 'Voice Studio',
      desc: 'Tạo MP3 từ file SRT giữ đúng timeline CapCut',
      icon: Sparkles,
      to: '/app/srt-tts',
      badge: 'WebAssembly',
      highlight: true,
    },
    {
      title: 'Sửa Phụ Đề SRT',
      desc: 'Chỉnh thời gian, tách gộp câu và xuất UTF-8',
      icon: Subtitles,
      to: '/app/tools?tab=srt',
      badge: 'Trình duyệt',
    },
    {
      title: 'Nhận Diện Whisper',
      desc: 'Chuyển video/audio thành phụ đề tự động',
      icon: Mic,
      to: '/app/tools?tab=transcript',
      badge: companionStatus?.online ? 'Companion' : 'Cần Companion',
      requiresCompanion: true,
    },
    {
      title: 'Tách Nhạc Demucs',
      desc: 'Bóc tách nhạc nền và lời thoại độc lập',
      icon: Music,
      to: '/app/tools?tab=separation',
      badge: companionStatus?.online ? 'Companion' : 'Cần Companion',
      requiresCompanion: true,
    },
  ];

  const isCompanionOnline = companionStatus?.online === true;
  const isBrowserDevice = activeDevice?.device_id === 'dev_browser_client';

  return (
    <div className="space-y-8 pb-8">
      {/* Top Banner: Authentic Hardware & Companion Environment */}
      <div className="rounded-card border border-border bg-gradient-to-r from-surface via-surface-raised to-surface p-6 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-5 relative overflow-hidden backdrop-blur-md">
        <div className="flex items-start sm:items-center gap-4">
          <div
            className={`h-14 w-14 rounded-card border flex items-center justify-center shrink-0 shadow-md ${
              isCompanionOnline
                ? 'bg-status-success/15 border-status-success/40 text-status-success shadow-[0_0_24px_rgba(52,211,153,0.2)]'
                : 'bg-brand/15 border-brand/40 text-brand shadow-[0_0_24px_rgba(45,212,191,0.15)]'
            }`}
          >
            <Laptop className="h-7 w-7" />
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center gap-2.5 flex-wrap">
              <h2 className="text-lg font-black text-text-primary tracking-tight">
                {activeDevice ? activeDevice.name : 'Trình Duyệt Web (WASM)'}
              </h2>
              {isCompanionOnline ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-status-success/15 text-status-success border border-status-success/30">
                  <span className="h-1.5 w-1.5 rounded-full bg-status-success animate-ping" />
                  Companion Online · {companionStatus?.ping_ms}ms
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-brand/15 text-brand border border-brand/30">
                  <Activity className="h-3 w-3" />
                  Chế độ WebAssembly Cục Bộ
                </span>
              )}
            </div>

            <p className="text-xs text-text-secondary leading-relaxed max-w-2xl">
              {activeDevice
                ? `${activeDevice.hardware.os} · ${activeDevice.hardware.cpu_name}${
                    isBrowserDevice
                      ? ' · TTS và SRT chạy cục bộ trong trình duyệt'
                      : ` · ${activeDevice.hardware.gpu_name || 'GPU chưa xác định'}`
                  }`
                : 'Môi trường xử lý trực tiếp trên trình duyệt WebAssembly.'}
              {!isCompanionOnline && (
                <span className="block text-[11px] text-text-muted mt-0.5">
                  Voice Studio (Piper WASM) & Trình sửa phụ đề SRT hoạt động trực tiếp không cần daemon.
                </span>
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5 shrink-0 flex-wrap">
          <Button
            variant="secondary"
            size="sm"
            onClick={handleProbe}
            disabled={isProbing}
            title="Kiểm tra kết nối lại với Python Companion daemon"
          >
            <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${isProbing ? 'animate-spin text-brand' : ''}`} />
            <span>{isProbing ? 'Đang kiểm tra...' : 'Kiểm tra Daemon'}</span>
          </Button>

          <Link to="/app/devices">
            <Button variant="secondary" size="sm">
              <Cpu className="h-3.5 w-3.5 mr-1.5" />
              <span>Thiết bị</span>
            </Button>
          </Link>

          <Link to="/app/projects">
            <Button variant="primary" size="sm">
              <Plus className="h-4 w-4 mr-1.5" />
              <span>Dự án mới</span>
            </Button>
          </Link>
        </div>
      </div>

      {/* Quick Tools Strip */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
            <Zap className="h-4 w-4 text-brand" />
            <span>Công Cụ Khởi Động Nhanh</span>
          </h3>
          <Link to="/app/tools" className="text-xs font-semibold text-brand hover:underline">
            Xem tất cả công cụ →
          </Link>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {quickTools.map((t) => {
            const Icon = t.icon;
            return (
              <Link
                key={t.title}
                to={t.to}
                className={`rounded-card border p-5 min-h-[205px] transition-all shadow-sm group flex flex-col justify-between ${
                  t.highlight
                    ? 'border-brand/40 bg-gradient-to-br from-brand/10 to-surface hover:border-brand'
                    : 'border-border bg-surface hover:border-border-light hover:bg-surface-raised'
                }`}
              >
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <div className="h-10 w-10 rounded-input bg-brand/15 border border-brand/25 flex items-center justify-center text-brand group-hover:scale-105 transition-transform">
                      <Icon className="h-5 w-5" />
                    </div>
                    <span className={`text-[10px] font-mono px-2 py-0.5 rounded bg-surface-raised border font-semibold ${
                      t.requiresCompanion && !isCompanionOnline
                        ? 'border-status-warning/35 text-status-warning'
                        : 'border-border text-brand'
                    }`}>
                      {t.badge}
                    </span>
                  </div>

                  <div className="text-sm font-bold text-text-primary group-hover:text-brand transition-colors">
                    {t.title}
                  </div>
                  <p className="text-xs text-text-secondary mt-1 leading-relaxed">{t.desc}</p>
                </div>

                <div className="mt-4 pt-2.5 border-t border-border/60 flex items-center justify-between text-[11px] text-text-muted">
                  <span>{t.requiresCompanion && !isCompanionOnline ? 'Mở để kết nối' : 'Khởi chạy'}</span>
                  <ArrowRight className="h-3.5 w-3.5 text-brand group-hover:translate-x-1 transition-transform" />
                </div>
              </Link>
            );
          })}
        </div>
      </div>

      {/* Active Tasks Widget (Max 3) */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
            <ListTodo className="h-4 w-4 text-brand" />
            <span>Tác Vụ Đang Xử Lý ({runningTasks.length})</span>
          </h3>
          <Link
            to="/app/tasks"
            className="text-xs font-semibold text-brand hover:underline inline-flex items-center gap-1"
          >
            <span>Hàng đợi tác vụ</span>
            <ArrowRight className="h-3 w-3" />
          </Link>
        </div>

        {runningTasks.length === 0 ? (
          <div className="rounded-card border border-border bg-surface p-6 text-center text-xs text-text-secondary">
            Hiện không có tác vụ nào đang chạy trên máy tính của bạn.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {runningTasks.map((task) => (
              <div
                key={task.id}
                onClick={() => navigate(`/app/tasks/${task.id}`)}
                className="rounded-card border border-border bg-surface p-5 hover:border-brand/40 transition-all cursor-pointer shadow-sm space-y-3"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-brand">
                    {task.type}
                  </span>
                  <StatusBadge status={task.state} size="sm" />
                </div>
                <div className="text-sm font-bold text-text-primary truncate">
                  {task.project_name || 'Tác vụ độc lập'}
                </div>
                {task.progress && (
                  <ProgressBar
                    progress={task.progress.current}
                    stage={task.progress.stage}
                    message={task.progress.message}
                    speed={task.progress.speed}
                    etaSeconds={task.progress.eta_seconds}
                  />
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Recent Projects (Up to 6) */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
            <FolderKanban className="h-4 w-4 text-brand" />
            <span>Dự Án Gần Đây</span>
          </h3>
          <Link
            to="/app/projects"
            className="text-xs font-semibold text-brand hover:underline inline-flex items-center gap-1"
          >
            <span>Xem tất cả ({projects.length})</span>
            <ArrowRight className="h-3 w-3" />
          </Link>
        </div>

        {recentProjects.length === 0 ? (
          <div className="rounded-card border border-border bg-surface p-8 text-center space-y-3">
            <div className="h-10 w-10 rounded-full bg-surface-raised border border-border flex items-center justify-center text-text-muted mx-auto">
              <FolderKanban className="h-5 w-5" />
            </div>
            <div className="text-sm font-bold text-text-primary">Chưa có dự án nào trong không gian làm việc</div>
            <p className="text-xs text-text-secondary max-w-md mx-auto">
              Khởi tạo dự án video mới để cấu hình phụ đề SRT, lồng tiếng Piper TTS hoặc nạp dự án mẫu để trải nghiệm ngay editor.
            </p>
            <div className="pt-2 flex items-center justify-center gap-3">
              <Link to="/app/projects">
                <Button size="sm" variant="primary">
                  <Plus className="h-3.5 w-3.5 mr-1" />
                  <span>Tạo Dự Án Mới</span>
                </Button>
              </Link>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  loadSampleDemoProject();
                  toast.success('Đã nạp dự án mẫu', 'Dự án demo đã được thêm vào danh sách.');
                }}
              >
                <FileCode className="h-3.5 w-3.5 mr-1 text-brand" />
                <span>Nạp Dự Án Mẫu</span>
              </Button>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {recentProjects.map((prj) => (
              <div
                key={prj.id}
                onClick={() => navigate(`/app/projects/${prj.id}/editor`)}
                className="rounded-card border border-border bg-surface p-4 hover:border-brand/40 transition-all cursor-pointer shadow-sm group flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between text-xs text-text-muted mb-2.5">
                    <span className="bg-surface-raised border border-border px-2 py-0.5 rounded-input text-[10px] font-mono font-bold text-brand">
                      {prj.languages.source_lang.toUpperCase()} → {prj.languages.target_lang.toUpperCase()}
                    </span>
                    <span className="text-[11px] text-text-muted">{prj.sync_status}</span>
                  </div>

                  <h4 className="text-sm font-bold text-text-primary group-hover:text-brand transition-colors line-clamp-1">
                    {prj.name}
                  </h4>
                  <div className="text-xs text-text-secondary mt-1 flex items-center gap-1.5">
                    <Laptop className="h-3.5 w-3.5 text-text-muted" />
                    <span className="truncate">{prj.device_name || activeDevice?.name || 'Trình duyệt Web'}</span>
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-border flex items-center justify-between text-[11px] text-text-muted">
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    <span>{new Date(prj.updated_at).toLocaleDateString('vi-VN')}</span>
                  </span>
                  <span className="text-brand font-semibold group-hover:underline">Mở Editor →</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

import React, { useState, useRef, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  Search,
  Laptop,
  Bell,
  Sparkles,
  Plus,
  ChevronDown,
  Check,
  ExternalLink,
  ShieldCheck,
  FolderKanban,
  Wrench,
  X,
  User,
  LogOut,
  Cpu,
  Keyboard,
  Mic,
  Scissors,
  Settings,
  Layers,
} from 'lucide-react';
import { useAppStore } from '../../stores/useAppStore';
import { StatusBadge } from '../common/StatusBadge';
import { ShortcutsModal } from '../modals/ShortcutsModal';
import { useToast } from '../../context/ToastContext';

export interface TopBarProps {
  onOpenPairModal: () => void;
  onOpenCreateProject?: () => void;
}

export const TopBar: React.FC<TopBarProps> = ({ onOpenPairModal, onOpenCreateProject }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const {
    user,
    activeDevice,
    devices,
    setActiveDevice,
    projects,
    activeJobs,
    companionStatus,
    resources,
    signOut,
  } = useAppStore();

  const [isDeviceMenuOpen, setIsDeviceMenuOpen] = useState(false);
  const [isNotifMenuOpen, setIsNotifMenuOpen] = useState(false);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isShortcutsOpen, setIsShortcutsOpen] = useState(false);
  const [isQuickActionOpen, setIsQuickActionOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [avatarFailed, setAvatarFailed] = useState(false);
  const toast = useToast();

  const deviceRef = useRef<HTMLDivElement>(null);
  const notifRef = useRef<HTMLDivElement>(null);
  const userRef = useRef<HTMLDivElement>(null);
  const quickActionRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setAvatarFailed(false);
  }, [user?.avatar_url]);

  // Close dropdowns on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (deviceRef.current && !deviceRef.current.contains(e.target as Node)) {
        setIsDeviceMenuOpen(false);
      }
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setIsNotifMenuOpen(false);
      }
      if (userRef.current && !userRef.current.contains(e.target as Node)) {
        setIsUserMenuOpen(false);
      }
      if (quickActionRef.current && !quickActionRef.current.contains(e.target as Node)) {
        setIsQuickActionOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Shortcut for Ctrl+K
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        setIsSearchOpen(true);
      }
      if (e.key === 'Escape') {
        setIsSearchOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Breadcrumbs title
  const pathParts = location.pathname.split('/').filter(Boolean);
  const routeNames: Record<string, string> = {
    app: 'Studio',
    projects: 'Dự án',
    tools: 'Công cụ',
    'srt-tts': 'Voice Studio',
    tasks: 'Tác vụ',
    devices: 'Thiết bị Companion',
    resources: 'Model & Giọng đọc',
    settings: 'Cài đặt',
    help: 'Hướng dẫn',
    editor: 'Editor',
  };

  const currentSection = pathParts[1] ? routeNames[pathParts[1]] || pathParts[1] : 'Tổng quan';
  const isEditor = location.pathname.includes('/editor');

  const filteredSearchResults = searchQuery.trim()
    ? projects.filter((p) => p.name.toLowerCase().includes(searchQuery.toLowerCase()))
    : [];

  const notifications = [
    ...(companionStatus?.online
      ? [
          {
            id: 'notif_companion',
            title: 'Companion Cục Bộ Đã Kết Nối',
            desc: `Đang lắng nghe trên ${companionStatus.profile || 'cổng 8765'} với độ trễ ${companionStatus.ping_ms}ms.`,
            time: 'Trực tiếp',
            type: 'success',
          },
        ]
      : [
          {
            id: 'notif_browser',
            title: 'Chế độ Trình duyệt Web (WASM)',
            desc: 'Voice Studio & Trình sửa SRT hoạt động độc lập bằng WebAssembly.',
            time: 'Hiện tại',
            type: 'info',
          },
        ]),
    ...(activeJobs.slice(0, 2).map((j) => ({
      id: `notif_job_${j.id}`,
      title: `Tác vụ ${j.type.toUpperCase()}: ${j.state}`,
      desc: j.progress?.message || `${j.project_name || 'Tác vụ độc lập'} (${j.progress?.current || 0}%).`,
      time: 'Đang chạy',
      type: j.state === 'Completed' ? 'success' : 'info',
    }))),
    ...resources.filter((resource) => resource.status === 'Downloading').map((resource) => ({
      id: `notif_resource_${resource.id}`,
      title: `Đang tải ${resource.name}`,
      desc: 'Tiến trình cài đặt được xử lý bởi Companion đang kết nối.',
      time: 'Hiện tại',
      type: 'model',
    })),
  ];

  return (
    <header className="h-[62px] border-b border-border/70 bg-surface/85 backdrop-blur-xl px-4 md:px-6 flex items-center justify-between gap-3 sticky top-0 z-30 shadow-[0_4px_24px_rgba(0,0,0,.15)]">
      {/* Left: Breadcrumbs */}
      <div className="flex items-center gap-2 min-w-0">
        <Link
          to="/app"
          className="text-xs font-bold tracking-wider text-text-muted hover:text-brand transition-colors uppercase flex items-center gap-1.5"
        >
          <Sparkles className="h-3.5 w-3.5 text-brand" />
          <span>VIUStudio</span>
        </Link>
        <span className="text-text-muted/60 text-xs">/</span>
        <span className="text-xs font-semibold text-text-primary truncate max-w-[200px] md:max-w-none">
          {isEditor ? 'Editor Workspace' : currentSection}
        </span>
      </div>

      {/* Center / Right: Quick Actions & Utilities */}
      <div className="flex items-center gap-2.5">
        {/* Quick Action Button & Menu */}
        <div className="relative" ref={quickActionRef}>
          <button
            onClick={() => setIsQuickActionOpen(!isQuickActionOpen)}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-gradient-to-r from-teal-400 via-cyan-400 to-teal-500 hover:from-teal-300 hover:to-cyan-400 text-slate-950 font-bold text-xs shadow-[0_0_18px_rgba(45,212,191,0.25)] hover:shadow-[0_0_24px_rgba(45,212,191,0.45)] transition-all active:scale-[0.98]"
            title="Tạo nhanh tác vụ hoặc dự án mới"
          >
            <Plus className="h-3.5 w-3.5 stroke-[2.5]" />
            <span className="hidden sm:inline">Tạo Nhanh</span>
            <ChevronDown className={`h-3 w-3 transition-transform ${isQuickActionOpen ? 'rotate-180' : ''}`} />
          </button>

          {isQuickActionOpen && (
            <div className="absolute left-0 sm:left-auto sm:right-0 mt-1.5 w-72 rounded-card border border-border bg-surface-raised p-2 shadow-2xl z-50 animate-in fade-in zoom-in-95 duration-100 space-y-1 text-xs">
              <div className="px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-text-muted">
                Khởi tạo tác vụ & Studio
              </div>

              <button
                onClick={() => {
                  setIsQuickActionOpen(false);
                  if (onOpenCreateProject) onOpenCreateProject();
                  else navigate('/app/projects');
                }}
                className="w-full text-left p-2 rounded-input hover:bg-surface flex items-center gap-2.5 transition-colors group text-text-primary"
              >
                <div className="h-7 w-7 rounded-lg bg-brand/15 border border-brand/30 flex items-center justify-center text-brand shrink-0 group-hover:scale-105 transition-transform">
                  <FolderKanban className="h-3.5 w-3.5" />
                </div>
                <div className="min-w-0">
                  <div className="font-semibold text-text-primary group-hover:text-brand transition-colors">
                    Dự án mới...
                  </div>
                  <div className="text-[10px] text-text-muted truncate">Khai báo video & cấu hình pipeline</div>
                </div>
              </button>

              <button
                onClick={() => {
                  setIsQuickActionOpen(false);
                  navigate('/app/tools?tab=transcript');
                }}
                className="w-full text-left p-2 rounded-input hover:bg-surface flex items-center gap-2.5 transition-colors group text-text-primary"
              >
                <div className="h-7 w-7 rounded-lg bg-status-warning/15 border border-status-warning/30 flex items-center justify-center text-status-warning shrink-0 group-hover:scale-105 transition-transform">
                  <Mic className="h-3.5 w-3.5" />
                </div>
                <div className="min-w-0">
                  <div className="font-semibold text-text-primary group-hover:text-status-warning transition-colors">
                    Nhận diện giọng nói (Whisper)
                  </div>
                  <div className="text-[10px] text-text-muted truncate">Tạo phụ đề tự động bằng GPU AI</div>
                </div>
              </button>

              <button
                onClick={() => {
                  setIsQuickActionOpen(false);
                  navigate('/app/srt-tts');
                }}
                className="w-full text-left p-2 rounded-input hover:bg-surface flex items-center gap-2.5 transition-colors group text-text-primary"
              >
                <div className="h-7 w-7 rounded-lg bg-accent-focus/15 border border-accent-focus/30 flex items-center justify-center text-accent-focus shrink-0 group-hover:scale-105 transition-transform">
                  <Sparkles className="h-3.5 w-3.5" />
                </div>
                <div className="min-w-0">
                  <div className="font-semibold text-text-primary group-hover:text-accent-focus transition-colors">
                    Voice Studio (SRT → MP3)
                  </div>
                  <div className="text-[10px] text-text-muted truncate">Lồng tiếng chuẩn timeline CapCut</div>
                </div>
              </button>

              <button
                onClick={() => {
                  setIsQuickActionOpen(false);
                  navigate('/app/tools?tab=separation');
                }}
                className="w-full text-left p-2 rounded-input hover:bg-surface flex items-center gap-2.5 transition-colors group text-text-primary"
              >
                <div className="h-7 w-7 rounded-lg bg-indigo-500/15 border border-indigo-500/30 flex items-center justify-center text-indigo-400 shrink-0 group-hover:scale-105 transition-transform">
                  <Scissors className="h-3.5 w-3.5" />
                </div>
                <div className="min-w-0">
                  <div className="font-semibold text-text-primary group-hover:text-indigo-400 transition-colors">
                    Tách nhạc & lời thoại (Demucs)
                  </div>
                  <div className="text-[10px] text-text-muted truncate">Bóc tách Voice & Music stems riêng</div>
                </div>
              </button>

              <button
                onClick={() => {
                  setIsQuickActionOpen(false);
                  navigate('/app/tools?tab=srt');
                }}
                className="w-full text-left p-2 rounded-input hover:bg-surface flex items-center gap-2.5 transition-colors group text-text-primary"
              >
                <div className="h-7 w-7 rounded-lg bg-slate-500/15 border border-slate-500/30 flex items-center justify-center text-text-secondary shrink-0 group-hover:scale-105 transition-transform">
                  <Wrench className="h-3.5 w-3.5" />
                </div>
                <div className="min-w-0">
                  <div className="font-semibold text-text-primary group-hover:text-text-primary transition-colors">
                    Trình sửa phụ đề SRT Studio
                  </div>
                  <div className="text-[10px] text-text-muted truncate">Chỉnh mốc, gộp/tách câu trong trình duyệt</div>
                </div>
              </button>

              <div className="border-t border-border pt-1 mt-1">
                <button
                  onClick={() => {
                    setIsQuickActionOpen(false);
                    onOpenPairModal();
                  }}
                  className="w-full text-left p-2 rounded-input hover:bg-brand/10 text-brand flex items-center gap-2 transition-colors font-semibold"
                >
                  <Laptop className="h-3.5 w-3.5" />
                  <span>Ghép nối máy tính mới...</span>
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Quick Search Button */}
        <button
          onClick={() => setIsSearchOpen(true)}
          className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-input bg-surface-raised/90 border border-border text-xs text-text-muted hover:text-text-primary hover:border-brand/40 transition-all shadow-sm"
          title="Tìm kiếm dự án (Ctrl + K)"
        >
          <Search className="h-3.5 w-3.5 text-text-muted" />
          <span className="text-text-secondary">Tìm kiếm...</span>
          <kbd className="text-[10px] font-mono bg-background/80 px-1.5 py-0.5 rounded border border-border text-text-muted">
            Ctrl K
          </kbd>
        </button>

        {/* Device Selector Pill with Live Pulse Dot */}
        <div className="relative" ref={deviceRef}>
          <button
            onClick={() => setIsDeviceMenuOpen(!isDeviceMenuOpen)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-input bg-surface-raised border border-border hover:border-brand/40 text-xs text-text-primary transition-all group shadow-sm"
            title="Thiết bị xử lý"
          >
            <span
              className={`h-2 w-2 rounded-full ${
                activeDevice?.ready_state === 'Ready'
                  ? 'bg-status-success shadow-[0_0_8px_rgba(52,211,153,0.8)]'
                  : activeDevice?.ready_state === 'Busy'
                  ? 'bg-status-warning shadow-[0_0_8px_rgba(251,191,36,0.8)]'
                  : 'bg-text-muted'
              }`}
            />
            <span className="font-semibold text-text-primary truncate max-w-[140px] md:max-w-[180px]">
              {activeDevice ? activeDevice.name.split('(')[0].trim() : 'Chọn thiết bị'}
            </span>
            <ChevronDown className="h-3.5 w-3.5 text-text-muted group-hover:text-text-primary transition-transform" />
          </button>

          {/* Device Dropdown Menu */}
          {isDeviceMenuOpen && (
            <div className="absolute right-0 mt-1.5 w-72 rounded-card border border-border bg-surface-raised p-2 shadow-2xl z-50 animate-in fade-in zoom-in-95 duration-100">
              <div className="px-2.5 py-1.5 border-b border-border text-[11px] font-bold uppercase tracking-wider text-text-muted flex items-center justify-between">
                <span>Thiết bị Companion</span>
                <Link to="/app/devices" onClick={() => setIsDeviceMenuOpen(false)} className="text-brand hover:underline lowercase font-normal">
                  quản lý →
                </Link>
              </div>

              <div className="space-y-1 py-1 max-h-56 overflow-y-auto">
                {devices.map((dev) => {
                  const isSelected = activeDevice?.device_id === dev.device_id;
                  return (
                    <button
                      key={dev.device_id}
                      onClick={() => {
                        setActiveDevice(dev);
                        setIsDeviceMenuOpen(false);
                      }}
                      className={`w-full text-left p-2 rounded-input text-xs flex items-center justify-between transition-colors ${
                        isSelected
                          ? 'bg-brand/10 border border-brand/25 text-brand font-semibold'
                          : 'hover:bg-surface text-text-primary'
                      }`}
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <Laptop className="h-3.5 w-3.5 shrink-0 text-text-muted" />
                        <div className="truncate">
                          <div className="truncate">{dev.name}</div>
                          <div className="text-[10px] text-text-muted truncate">
                            {dev.hardware.gpu_name || dev.hardware.cpu_name}
                          </div>
                        </div>
                      </div>
                      {isSelected && <Check className="h-3.5 w-3.5 text-brand shrink-0" />}
                    </button>
                  );
                })}
              </div>

              <div className="border-t border-border pt-1.5 mt-1">
                <button
                  onClick={() => {
                    setIsDeviceMenuOpen(false);
                    onOpenPairModal();
                  }}
                  className="w-full flex items-center gap-2 px-2.5 py-2 rounded-input text-xs font-semibold text-brand hover:bg-brand/10 transition-colors"
                >
                  <Plus className="h-3.5 w-3.5" />
                  <span>Ghép nối máy tính mới...</span>
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Keyboard Shortcuts Trigger */}
        <button
          onClick={() => setIsShortcutsOpen(true)}
          className="p-2 rounded-input text-text-secondary hover:text-text-primary hover:bg-surface-raised border border-transparent hover:border-border transition-colors hidden sm:inline-flex items-center justify-center"
          title="Bảng tra cứu phím tắt (?)"
        >
          <Keyboard className="h-4 w-4" />
        </button>

        {/* Notifications Popover */}
        <div className="relative" ref={notifRef}>
          <button
            onClick={() => setIsNotifMenuOpen(!isNotifMenuOpen)}
            className="p-2 rounded-input text-text-secondary hover:text-text-primary hover:bg-surface-raised border border-transparent hover:border-border transition-colors relative"
            title="Thông báo"
          >
            <Bell className="h-4 w-4" />
            {activeJobs.some((job) => !['Completed', 'Failed', 'Cancelled'].includes(job.state)) && (
              <span className="absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-brand shadow-[0_0_8px_rgba(77,232,225,.8)]" />
            )}
          </button>

          {isNotifMenuOpen && (
            <div className="absolute right-0 mt-1.5 w-80 rounded-card border border-border bg-surface-raised p-3 shadow-2xl z-50 animate-in fade-in zoom-in-95 duration-100">
              <div className="flex items-center justify-between pb-2 border-b border-border">
                <span className="text-xs font-bold uppercase tracking-wider text-text-primary">
                  Thông báo hoạt động
                </span>
                <span className="text-[10px] text-brand font-medium cursor-pointer hover:underline">
                  Đã đọc tất cả
                </span>
              </div>

              <div className="divide-y divide-border/60 max-h-64 overflow-y-auto">
                {notifications.length === 0 && (
                  <p className="py-5 text-center text-[11px] text-text-muted">Chưa có hoạt động mới.</p>
                )}
                {notifications.map((n) => (
                  <div key={n.id} className="py-2.5 text-xs space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-text-primary">{n.title}</span>
                      <span className="text-[10px] text-text-muted">{n.time}</span>
                    </div>
                    <p className="text-text-secondary text-[11px] leading-relaxed">{n.desc}</p>
                  </div>
                ))}
              </div>

              <div className="pt-2 border-t border-border text-center">
                <Link
                  to="/app/tasks"
                  onClick={() => setIsNotifMenuOpen(false)}
                  className="text-xs font-semibold text-brand hover:underline"
                >
                  Xem toàn bộ tiến độ tác vụ →
                </Link>
              </div>
            </div>
          )}
        </div>

        {/* User Profile Avatar & Menu */}
        <div className="relative" ref={userRef}>
          <button
            onClick={() => setIsUserMenuOpen(!isUserMenuOpen)}
            className="flex items-center gap-2 p-1 rounded-full hover:bg-surface-raised transition-colors"
            title={user?.name || 'Tài khoản'}
          >
              <div className="h-8 w-8 rounded-full bg-gradient-to-br from-brand via-accent-focus to-indigo-600 p-[1.5px] shadow-[0_0_12px_rgba(77,232,225,.3)] overflow-hidden">
                <div className="h-full w-full rounded-full bg-surface-raised flex items-center justify-center text-xs font-bold text-brand">
                {user?.avatar_url && !avatarFailed ? (
                  <img
                    src={user.avatar_url}
                    alt={user.name ? `Ảnh đại diện của ${user.name}` : 'Ảnh đại diện'}
                    className="h-full w-full object-cover"
                    referrerPolicy="no-referrer"
                    onError={() => setAvatarFailed(true)}
                  />
                ) : user?.name ? user.name[0].toUpperCase() : 'K'}
                </div>
            </div>
          </button>

          {isUserMenuOpen && (
            <div className="absolute right-0 mt-1.5 w-60 rounded-card border border-border bg-surface-raised p-2 shadow-2xl z-50 animate-in fade-in zoom-in-95 duration-100">
              <div className="p-2 border-b border-border space-y-0.5">
                <div className="text-xs font-bold text-text-primary flex items-center justify-between">
                  <span>{user?.name || 'Khách'}</span>
                  <span className="px-1.5 py-0.2 rounded bg-brand/15 text-brand font-mono text-[9px] uppercase font-bold">{user ? 'SYNC' : 'LOCAL'}</span>
                </div>
                <div className="text-[11px] text-text-muted truncate">{user?.email || 'Dữ liệu chỉ lưu trong trình duyệt'}</div>
              </div>

              <div className="py-1 space-y-0.5 text-xs">
                <Link
                  to="/app/settings"
                  onClick={() => setIsUserMenuOpen(false)}
                  className="flex items-center gap-2 px-2.5 py-1.5 rounded-input text-text-secondary hover:text-text-primary hover:bg-surface"
                >
                  <User className="h-3.5 w-3.5" />
                  <span>Cài đặt tài khoản & Privacy</span>
                </Link>
                <Link
                  to="/app/help"
                  onClick={() => setIsUserMenuOpen(false)}
                  className="flex items-center gap-2 px-2.5 py-1.5 rounded-input text-text-secondary hover:text-text-primary hover:bg-surface"
                >
                  <ShieldCheck className="h-3.5 w-3.5 text-status-success" />
                  <span>Hướng dẫn & Bản quyền</span>
                </Link>
              </div>

              <div className="pt-1 border-t border-border">
                <button
                  onClick={() => {
                    setIsUserMenuOpen(false);
                    if (user) void signOut().then(() => navigate('/sign-in'));
                    else navigate('/sign-in');
                  }}
                  className="flex items-center gap-2 px-2.5 py-1.5 rounded-input text-xs text-status-error hover:bg-status-error/10"
                >
                  <LogOut className="h-3.5 w-3.5" />
                  <span>{user ? 'Đăng xuất' : 'Đăng nhập để đồng bộ'}</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Search Modal Overlay (Ctrl + K) */}
      {isSearchOpen && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-md z-50 flex items-start justify-center pt-20 p-4 animate-in fade-in duration-150">
          <div className="w-full max-w-lg rounded-card border border-border bg-surface p-4 shadow-2xl space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-border">
              <div className="flex items-center gap-2 flex-1">
                <Search className="h-4 w-4 text-brand" />
                <input
                  type="text"
                  autoFocus
                  placeholder="Gõ tên dự án hoặc công cụ cần tìm..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full bg-transparent border-none text-sm text-text-primary placeholder:text-text-muted focus:outline-none"
                />
              </div>
              <button
                onClick={() => setIsSearchOpen(false)}
                className="p-1 rounded text-text-muted hover:text-text-primary"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="max-h-80 overflow-y-auto space-y-1 py-1">
              <div className="text-[10px] font-bold uppercase tracking-wider text-text-muted px-2 py-1">
                Công cụ Studio & AI
              </div>
              <div
                onClick={() => {
                  navigate('/app/srt-tts');
                  setIsSearchOpen(false);
                }}
                className="p-2 rounded-input hover:bg-surface-raised cursor-pointer flex items-center justify-between text-xs"
              >
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-brand" />
                  <span className="font-semibold text-text-primary">Voice Studio (SRT → TTS → MP3)</span>
                </div>
                <span className="text-[10px] text-brand bg-brand/10 px-1.5 py-0.5 rounded">WebAssembly</span>
              </div>
              <div
                onClick={() => {
                  navigate('/app/tools?tab=srt');
                  setIsSearchOpen(false);
                }}
                className="p-2 rounded-input hover:bg-surface-raised cursor-pointer flex items-center justify-between text-xs"
              >
                <div className="flex items-center gap-2">
                  <Wrench className="h-4 w-4 text-text-secondary" />
                  <span className="font-semibold text-text-primary">Trình sửa phụ đề SRT Studio</span>
                </div>
                <span className="text-[10px] text-text-muted">In Browser</span>
              </div>
              <div
                onClick={() => {
                  navigate('/app/tools?tab=transcript');
                  setIsSearchOpen(false);
                }}
                className="p-2 rounded-input hover:bg-surface-raised cursor-pointer flex items-center justify-between text-xs"
              >
                <div className="flex items-center gap-2">
                  <Mic className="h-4 w-4 text-status-warning" />
                  <span className="font-semibold text-text-primary">Nhận diện giọng nói Whisper AI</span>
                </div>
                <span className="text-[10px] text-text-muted">Speech-to-Text</span>
              </div>
              <div
                onClick={() => {
                  navigate('/app/tools?tab=separation');
                  setIsSearchOpen(false);
                }}
                className="p-2 rounded-input hover:bg-surface-raised cursor-pointer flex items-center justify-between text-xs"
              >
                <div className="flex items-center gap-2">
                  <Scissors className="h-4 w-4 text-accent-focus" />
                  <span className="font-semibold text-text-primary">Tách âm thanh nền & giọng hát Demucs</span>
                </div>
                <span className="text-[10px] text-text-muted">Stems Separation</span>
              </div>

              <div className="text-[10px] font-bold uppercase tracking-wider text-text-muted px-2 pt-3 pb-1">
                Điều hướng & Hệ thống
              </div>
              <div
                onClick={() => {
                  setIsSearchOpen(false);
                  setIsShortcutsOpen(true);
                }}
                className="p-2 rounded-input hover:bg-surface-raised cursor-pointer flex items-center justify-between text-xs"
              >
                <div className="flex items-center gap-2">
                  <Keyboard className="h-4 w-4 text-brand" />
                  <span className="font-semibold text-text-primary">Bảng tra cứu phím tắt (Keyboard Shortcuts)</span>
                </div>
                <span className="text-[10px] text-text-muted font-mono">?</span>
              </div>
              <div
                onClick={() => {
                  navigate('/app/devices');
                  setIsSearchOpen(false);
                }}
                className="p-2 rounded-input hover:bg-surface-raised cursor-pointer flex items-center justify-between text-xs"
              >
                <div className="flex items-center gap-2">
                  <Cpu className="h-4 w-4 text-text-secondary" />
                  <span className="font-semibold text-text-primary">Thiết bị Companion & Cấu hình phần cứng</span>
                </div>
                <span className="text-[10px] text-text-muted truncate max-w-[150px]">
                  {activeDevice?.hardware.gpu_name || activeDevice?.hardware.cpu_name || 'Thiết bị'}
                </span>
              </div>
              <div
                onClick={() => {
                  navigate('/app/settings');
                  setIsSearchOpen(false);
                }}
                className="p-2 rounded-input hover:bg-surface-raised cursor-pointer flex items-center justify-between text-xs"
              >
                <div className="flex items-center gap-2">
                  <Settings className="h-4 w-4 text-text-secondary" />
                  <span className="font-semibold text-text-primary">Cài đặt hệ thống & Giao diện</span>
                </div>
              </div>

              <div className="text-[10px] font-bold uppercase tracking-wider text-text-muted px-2 pt-3 pb-1">
                Dự án gần đây
              </div>
              {(filteredSearchResults.length > 0 ? filteredSearchResults : projects).map((prj) => (
                <div
                  key={prj.id}
                  onClick={() => {
                    navigate(`/app/projects/${prj.id}/editor`);
                    setIsSearchOpen(false);
                  }}
                  className="p-2 rounded-input hover:bg-surface-raised cursor-pointer flex items-center justify-between text-xs"
                >
                  <div className="flex items-center gap-2">
                    <FolderKanban className="h-4 w-4 text-text-muted" />
                    <span className="font-medium text-text-primary">{prj.name}</span>
                  </div>
                  <span className="text-[10px] font-mono text-text-muted">
                    {prj.languages.source_lang.toUpperCase()} → {prj.languages.target_lang.toUpperCase()}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Global Shortcuts Modal */}
      <ShortcutsModal isOpen={isShortcutsOpen} onClose={() => setIsShortcutsOpen(false)} />
    </header>
  );
};

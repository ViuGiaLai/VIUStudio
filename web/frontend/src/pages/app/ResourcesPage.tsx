import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Cpu,
  Download,
  Check,
  AlertCircle,
  Sparkles,
  HardDrive,
  RefreshCw,
  Search,
  Zap,
  Volume2,
  Trash2,
  CheckCircle2,
  Layers,
  Filter,
  Radio,
  Play,
  Pause,
  Smartphone,
  Laptop,
  Cloud,
  Info,
} from 'lucide-react';
import { useAppStore } from '../../stores/useAppStore';
import { Button } from '../../components/common/Button';
import { StatusBadge } from '../../components/common/StatusBadge';
import { useToast } from '../../context/ToastContext';

export const ResourcesPage: React.FC = () => {
  const {
    activeDevice,
    companionStatus,
    resources,
    installResource,
    uninstallResource,
    refreshResources,
    browserStorage,
  } = useAppStore();
  const toast = useToast();
  const navigate = useNavigate();
  const isCompanion = Boolean(companionStatus?.online);
  const isMobile = typeof navigator !== 'undefined' && /mobile|android|iphone|ipad|ipod/i.test(navigator.userAgent);
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [selectedLang, setSelectedLang] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [playingModelId, setPlayingModelId] = useState<string | null>(null);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await refreshResources();
    setIsRefreshing(false);
    toast.info(companionStatus?.online ? 'Đã đồng bộ trạng thái model từ Companion' : 'Đang hiển thị danh mục cục bộ; Companion chưa kết nối');
  };

  const handleInstall = async (id: string, name: string) => {
    try {
      toast.info(`Đang yêu cầu Companion cài "${name}"...`);
      await installResource(id);
      toast.success(`Đã cài đặt thành công mô hình "${name}" vào thư mục Companion!`);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Không thể cài model.');
    }
  };

  const handleUninstall = async (id: string, name: string) => {
    try {
      await uninstallResource(id);
      toast.info(`Đã gỡ bỏ "${name}" và giải phóng bộ nhớ.`);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Không thể gỡ model.');
    }
  };

  const handleBatchInstall = async () => {
    const uninstalled = resources.filter((r) => r.status === 'Not installed');
    if (uninstalled.length === 0) {
      toast.info('Tất cả mô hình AI cốt lõi đã được cài đặt đầy đủ!');
      return;
    }
    toast.info(`Đang gửi ${uninstalled.length} yêu cầu cài đặt đến Companion...`);
    let installed = 0;
    for (const resource of uninstalled) {
      try {
        await installResource(resource.id);
        installed += 1;
      } catch (cause) {
        toast.error(cause instanceof Error ? cause.message : `Không thể cài ${resource.name}.`);
        break;
      }
    }
    if (installed === uninstalled.length) toast.success('Hoàn tất cài bộ Model AI cốt lõi!');
  };

  const handleToggleVoicePreview = (modelId: string, modelName: string) => {
    if (playingModelId === modelId) {
      window.speechSynthesis?.cancel();
      setPlayingModelId(null);
      return;
    }

    setPlayingModelId(null);
    toast.info(`Mở Voice Studio để nghe đúng model "${modelName}" thay vì giọng mặc định của trình duyệt.`);
    navigate('/app/srt-tts');
  };

  // Filtered resources
  const filtered = resources.filter((r) => {
    const matchCat =
      selectedCategory === 'all'
        ? true
        : selectedCategory === 'mobile'
        ? ['res_whisper_base', 'res_whisper_tiny', 'res_piper_vais', 'res_piper_vivos'].includes(r.id)
        : selectedCategory === 'pc_heavy'
        ? ['res_whisper_large', 'res_whisper_turbo', 'res_demucs_v4'].includes(r.id)
        : r.category === selectedCategory;
    const matchLang =
      selectedLang === 'all' ||
      r.languages.includes(selectedLang) ||
      (selectedLang === 'all_langs' && r.languages.includes('all'));
    const matchSearch =
      !searchQuery.trim() ||
      r.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.engine.toLowerCase().includes(searchQuery.toLowerCase());
    return matchCat && matchLang && matchSearch;
  });

  const installedCount = resources.filter((r) => r.status === 'Ready').length;
  const totalDiskBytes = resources
    .filter((r) => r.status === 'Ready')
    .reduce((acc, r) => acc + (r.installed_size_bytes || r.download_size_bytes || 0), 0);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black text-text-primary tracking-tight">Model & Tài Nguyên AI</h1>
          <p className="text-xs text-text-secondary mt-1">
            Quản lý các mô hình AI ngoại tuyến (Whisper, Piper, Kokoro, Demucs) cài đặt trên {activeDevice?.name || 'máy trạm của bạn'}.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <Button variant="secondary" size="sm" onClick={handleBatchInstall}>
            <Sparkles className="h-3.5 w-3.5 mr-1.5 text-brand" />
            <span>Tải gói Model cốt lõi</span>
          </Button>

          <Button variant="secondary" size="sm" onClick={handleRefresh} isLoading={isRefreshing}>
            <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
            <span>Đồng bộ mới</span>
          </Button>
        </div>
      </div>

      {/* Summary Telemetry Stats Bar - Dynamic, truthful and platform-aware */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="rounded-card bg-surface border border-border p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-card bg-brand/10 border border-brand/20 flex items-center justify-center text-brand">
            <Layers className="h-5 w-5" />
          </div>
          <div>
            <div className="text-xs text-text-muted">Model khả dụng</div>
            <div className="text-lg font-black font-mono text-text-primary">
              {installedCount} / {resources.length}
            </div>
          </div>
        </div>

        <div className="rounded-card bg-surface border border-border p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-card bg-accent-focus/10 border border-accent-focus/20 flex items-center justify-center text-accent-focus">
            <HardDrive className="h-5 w-5" />
          </div>
          <div>
            <div className="text-xs text-text-muted">
              {isCompanion ? 'Dung lượng Companion' : 'Bộ nhớ Cache Web'}
            </div>
            <div className="text-lg font-black font-mono text-accent-focus">
              {isCompanion
                ? `${(totalDiskBytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
                : `${browserStorage.usageMb.toFixed(1)} MB`}
            </div>
          </div>
        </div>

        <div className="rounded-card bg-surface border border-border p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-card bg-status-success/10 border border-status-success/20 flex items-center justify-center text-status-success">
            <Zap className="h-5 w-5" />
          </div>
          <div>
            <div className="text-xs text-text-muted">
              {isCompanion ? 'Tăng tốc phần cứng' : 'Công nghệ Web'}
            </div>
            <div className="text-lg font-black font-mono text-status-success truncate max-w-[130px]" title={activeDevice?.hardware.gpu_name}>
              {isCompanion
                ? (activeDevice?.hardware.has_gpu_acceleration ? 'GPU CUDA' : 'CPU Mode')
                : (isMobile ? 'WASM SIMD' : 'WebAssembly')}
            </div>
          </div>
        </div>

        <div className="rounded-card bg-surface border border-border p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-card bg-status-info/10 border border-status-info/20 flex items-center justify-center text-status-info">
            <Radio className="h-5 w-5 animate-pulse" />
          </div>
          <div>
            <div className="text-xs text-text-muted">
              {isCompanion ? 'RAM hệ thống' : 'Hạn mức Web Quota'}
            </div>
            <div className="text-lg font-black font-mono text-status-info">
              {isCompanion
                ? `${Math.round((activeDevice?.hardware.total_memory_bytes || 8e9) / 1e9)} GB RAM`
                : (browserStorage.quotaMb > 0 ? `${(browserStorage.quotaMb / 1024).toFixed(1)} GB` : 'W3C Quota')}
            </div>
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border pb-3">
        <div className="flex items-center gap-2 text-xs overflow-x-auto">
          {[
            { id: 'all', label: 'Tất cả tài nguyên' },
            { id: 'mobile', label: '📱 Tối ưu Điện Thoại & Web' },
            { id: 'pc_heavy', label: '💻 PC GPU (Whisper Large / Demucs)' },
            { id: 'speech_recognition', label: 'Whisper AI' },
            { id: 'tts', label: 'Giọng đọc AI (Piper TTS)' },
            { id: 'separation', label: 'Tách âm thanh (Demucs)' },
          ].map((cat) => (
            <button
              key={cat.id}
              onClick={() => setSelectedCategory(cat.id)}
              className={`px-3 py-1.5 rounded-input font-semibold transition-colors whitespace-nowrap ${
                selectedCategory === cat.id
                  ? 'bg-brand/15 text-brand border border-brand/30'
                  : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              {cat.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2.5">
          {/* Language filter */}
          <select
            value={selectedLang}
            onChange={(e) => setSelectedLang(e.target.value)}
            className="bg-surface border border-border rounded-input px-2.5 py-1.5 text-xs text-text-primary focus:border-brand"
          >
            <option value="all">Mọi ngôn ngữ</option>
            <option value="vi">Tiếng Việt (vi)</option>
            <option value="en">Tiếng Anh (en)</option>
            <option value="ja">Tiếng Nhật (ja)</option>
            <option value="all_langs">Đa ngôn ngữ</option>
          </select>

          {/* Search bar */}
          <div className="relative">
            <Search className="h-3.5 w-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
            <input
              type="text"
              placeholder="Tìm theo tên model..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-surface border border-border rounded-input pl-8 pr-3 py-1.5 text-xs text-text-primary placeholder:text-text-muted focus:border-brand w-36 sm:w-48"
            />
          </div>
        </div>
      </div>

      {/* 3-Tier Adaptive Architecture Guide */}
      <div className="p-3.5 rounded-card bg-surface border border-border/80 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 text-xs">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-brand/10 text-brand flex items-center justify-center shrink-0">
            <Sparkles className="h-4 w-4" />
          </div>
          <div>
            <div className="font-bold text-text-primary flex items-center gap-2">
              <span>Kiến Trúc AI Thích Ứng (3-Tier Adaptive Architecture)</span>
              <span className="px-2 py-0.5 rounded-full bg-brand/10 text-brand font-mono text-[10px] font-semibold">
                Tiết kiệm 100% Server Cost
              </span>
            </div>
            <p className="text-text-muted mt-0.5">
              Hệ thống tự động phân loại mô hình phù hợp thiết bị để tránh văng RAM trên điện thoại và tối ưu VRAM trên PC.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 w-full md:w-auto shrink-0">
          <div className="flex items-center gap-2 p-2 rounded-button bg-surface-hover/60 border border-border/60">
            <Smartphone className="h-3.5 w-3.5 text-status-success shrink-0" />
            <div>
              <div className="font-semibold text-text-primary text-[11px]">📱 Mobile & Web</div>
              <div className="text-[10px] text-text-muted">Whisper Base/Tiny (WASM &lt; 3m)</div>
            </div>
          </div>
          <div className="flex items-center gap-2 p-2 rounded-button bg-surface-hover/60 border border-border/60">
            <Laptop className="h-3.5 w-3.5 text-brand shrink-0" />
            <div>
              <div className="font-semibold text-text-primary text-[11px]">💻 Local PC (Companion)</div>
              <div className="text-[10px] text-text-muted">Whisper Large v3 + Demucs (Đã hỗ trợ)</div>
            </div>
          </div>
          <div className="flex items-center gap-2 p-2 rounded-button bg-surface-hover/60 border border-border/60">
            <Cloud className="h-3.5 w-3.5 text-status-info shrink-0" />
            <div>
              <div className="font-semibold text-text-primary text-[11px]">☁️ Cloud GPU (Sắp ra mắt)</div>
              <div className="text-[10px] text-text-muted">Đang phát triển server cluster</div>
            </div>
          </div>
        </div>
      </div>

      {/* Model Cards Grid */}
      {filtered.length === 0 ? (
        <div className="rounded-card border border-border bg-surface p-12 text-center space-y-3">
          <Layers className="h-12 w-12 text-text-muted mx-auto opacity-40" />
          <h3 className="text-sm font-bold text-text-primary">Không tìm thấy mô hình AI nào</h3>
          <p className="text-xs text-text-secondary max-w-sm mx-auto">
            Thử thay đổi từ khóa tìm kiếm hoặc chọn danh mục khác.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {filtered.map((res) => {
            const isInstalled = res.status === 'Ready';
            const isDownloading = res.status === 'Downloading';
            const isComingSoon = res.status === 'Coming soon';
            const isTts = res.category === 'tts';
            const isPlayingThis = playingModelId === res.id;

            return (
              <div
                key={res.id}
                className={`rounded-card border bg-surface p-5 shadow-sm space-y-4 flex flex-col justify-between transition-all ${
                  isInstalled
                    ? 'border-border hover:border-brand/40 shadow-[0_0_20px_rgba(77,232,225,0.03)]'
                    : 'border-border/70 hover:border-border-light'
                }`}
              >
                <div className="space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-bold text-text-primary">{res.name}</h3>
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-surface-raised border border-border text-text-muted uppercase font-bold">
                          {res.engine}
                        </span>
                      </div>

                      <div className="flex flex-wrap items-center gap-1.5 mt-2">
                        {res.languages.map((l) => (
                          <span
                            key={l}
                            className="bg-brand/10 border border-brand/20 px-2 py-0.5 rounded text-[10px] font-mono text-brand font-bold uppercase"
                          >
                            {l === 'all' ? 'TẤT CẢ' : l}
                          </span>
                        ))}
                        <span className="text-[11px] text-text-muted capitalize">
                          · {res.category === 'speech_recognition' ? 'Whisper STT' : res.category === 'tts' ? 'Voice TTS' : 'Stem Demucs'}
                        </span>
                      </div>
                    </div>

                    <StatusBadge status={res.status} size="sm" />
                  </div>

                  <p className="text-xs text-text-secondary leading-relaxed">{res.description}</p>

                  {/* Hardware requirements and size badges */}
                  <div className="flex flex-wrap items-center gap-3 pt-1 text-[11px] text-text-muted">
                    {res.download_size_bytes && (
                      <div className="flex items-center gap-1.5">
                        <HardDrive className="h-3.5 w-3.5 text-text-muted" />
                        <span>
                          Dung lượng:{' '}
                          <strong className="text-text-primary font-mono">
                            {res.download_size_bytes > 1024 * 1024 * 1024
                              ? `${(res.download_size_bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
                              : `${(res.download_size_bytes / (1024 * 1024)).toFixed(0)} MB`}
                          </strong>
                        </span>
                      </div>
                    )}

                    <div className="flex items-center gap-1 text-accent-focus font-semibold">
                      <Zap className="h-3 w-3" />
                      <span>{res.engine === 'piper' ? 'WebAssembly / CPU' : 'CUDA Tối Ưu'}</span>
                    </div>
                  </div>

                  {/* Downloading Progress Bar */}
                  {isDownloading && (
                    <div className="space-y-1.5 pt-2">
                      <div className="flex justify-between text-[11px]">
                        <span className="text-brand font-medium">Companion đang tải và xác minh model...</span>
                        <span className="font-mono text-brand font-bold">ĐANG XỬ LÝ</span>
                      </div>
                      <div className="w-full bg-surface-raised rounded-full h-1.5 overflow-hidden">
                        <div
                          className="bg-brand h-full w-1/2 rounded-full animate-pulse"
                        />
                      </div>
                    </div>
                  )}
                </div>

                {/* Card Action Bar */}
                <div className="pt-3 border-t border-border flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {/* Voice Sample Preview for TTS models */}
                    {isTts && (
                      <button
                        onClick={() => handleToggleVoicePreview(res.id, res.name)}
                        className={`text-xs px-2.5 py-1 rounded-input font-semibold flex items-center gap-1.5 transition-colors ${
                          isPlayingThis
                            ? 'bg-brand text-background font-bold'
                            : 'bg-surface-raised border border-border text-text-primary hover:border-brand'
                        }`}
                      >
                        {isPlayingThis ? <Pause className="h-3 w-3" /> : <Volume2 className="h-3 w-3 text-brand" />}
                        <span>{isPlayingThis ? 'Dừng nghe' : 'Nghe thử giọng'}</span>
                      </button>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    {isComingSoon ? (
                      <span className="text-xs text-text-muted font-medium italic">Sắp ra mắt</span>
                    ) : !isCompanion && (res.category === 'separation' || ['res_whisper_large', 'res_whisper_turbo'].includes(res.id)) ? (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => {
                          toast.info(
                            'Yêu cầu PC Companion',
                            'Mô hình này cần chạy qua Companion trên máy tính để tận dụng CPU/GPU thật mà không làm treo trình duyệt.'
                          );
                          navigate('/app/devices');
                        }}
                      >
                        <Laptop className="h-3.5 w-3.5 mr-1.5 text-brand" />
                        <span>Cần PC Companion</span>
                      </Button>
                    ) : !isCompanion && ['res_whisper_base', 'res_whisper_tiny'].includes(res.id) ? (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => {
                          toast.info(
                            'Chạy WebAssembly trực tiếp',
                            'Mô hình Whisper Web được tải và cache tự động trong trình duyệt khi bạn sử dụng tính năng Tạo phụ đề.'
                          );
                          navigate('/app/tools?tab=transcript');
                        }}
                      >
                        <Sparkles className="h-3.5 w-3.5 mr-1.5 text-accent-focus" />
                        <span>Chạy trên Web</span>
                      </Button>
                    ) : isInstalled ? (
                      <>
                        <span className="text-xs text-status-success font-semibold flex items-center gap-1">
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          <span>Đã cài đặt</span>
                        </span>
                        <button
                          onClick={() => handleUninstall(res.id, res.name)}
                          className="text-text-muted hover:text-status-error p-1 transition-colors"
                          title="Gỡ cài đặt để giải phóng ổ đĩa"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </>
                    ) : (
                      <Button
                        variant="primary"
                        size="sm"
                        isLoading={isDownloading}
                        onClick={() => handleInstall(res.id, res.name)}
                      >
                        <Download className="h-3.5 w-3.5 mr-1.5" />
                        <span>{isDownloading ? 'Đang tải...' : 'Tải Model về máy'}</span>
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

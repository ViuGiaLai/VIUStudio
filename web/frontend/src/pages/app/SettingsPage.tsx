import React, { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Check,
  Cpu,
  Database,
  Download,
  ExternalLink,
  Globe2,
  Palette,
  Save,
  Shield,
  Trash2,
  Upload,
  User,
  Zap,
} from 'lucide-react';
import { Button } from '../../components/common/Button';
import { useToast } from '../../context/ToastContext';
import { useAppStore } from '../../stores/useAppStore';

type StudioTheme = 'cyber-neon' | 'midnight-oled' | 'sapphire-slate';

const themes: Array<{ id: StudioTheme; title: string; desc: string; dot: string; preview: string }> = [
  { id: 'cyber-neon', title: 'Cyber Neon', desc: 'Cyan và tím, cân bằng độ tương phản', dot: 'bg-[#4de8e1]', preview: 'bg-[#0b1020]' },
  { id: 'midnight-oled', title: 'Midnight OLED', desc: 'Nền đen sâu cho màn hình OLED', dot: 'bg-[#a594ff]', preview: 'bg-black' },
  { id: 'sapphire-slate', title: 'Sapphire Slate', desc: 'Xanh hải quân dịu mắt', dot: 'bg-[#38bdf8]', preview: 'bg-[#07111f]' },
];

const bytesLabel = (bytes: number) => {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 MB';
  const mb = bytes / (1024 * 1024);
  return mb >= 1024 ? `${(mb / 1024).toFixed(2)} GB` : `${mb.toFixed(1)} MB`;
};

export const SettingsPage: React.FC = () => {
  const {
    user,
    settings,
    updateSettings,
    projects,
    projectCues,
    devices,
    resources,
    companionStatus,
    browserStorage,
    clearBrowserStorage,
    restoreBackup,
  } = useAppStore();
  const toast = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedTheme, setSelectedTheme] = useState<StudioTheme>(() => {
    const saved = localStorage.getItem('viustudio_studio_theme');
    return themes.some((theme) => theme.id === saved) ? (saved as StudioTheme) : 'cyber-neon';
  });
  const [syncSubtitles, setSyncSubtitles] = useState(settings?.sync.sync_subtitles_enabled ?? false);
  const [defaultSourceLang, setDefaultSourceLang] = useState(settings?.preferences.default_source_lang || 'auto');
  const [defaultTargetLang, setDefaultTargetLang] = useState(settings?.preferences.default_target_lang || 'vi');
  const [exportPreset, setExportPreset] = useState(settings?.preferences.export_preset || 'Balanced');
  const [savedSuccess, setSavedSuccess] = useState(false);
  const [clearingCache, setClearingCache] = useState(false);

  const handleThemeChange = (theme: StudioTheme) => {
    setSelectedTheme(theme);
    localStorage.setItem('viustudio_studio_theme', theme);
    document.documentElement.dataset.studioTheme = theme;
  };

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    const currentPrefs = settings?.preferences || {
      default_source_lang: 'auto',
      default_target_lang: 'vi',
      export_preset: 'Balanced',
      export_bitrate_kbps: 2800,
      theme: 'dark',
      density: 'comfortable',
      preferred_device_id: 'dev_browser_client',
    };
    const currentSync = settings?.sync || {
      sync_subtitles_enabled: false,
      sync_metadata_enabled: true,
      last_synced_at: new Date().toISOString(),
    };
    try {
    await updateSettings({
      preferences: {
        ...currentPrefs,
        default_source_lang: defaultSourceLang,
        default_target_lang: defaultTargetLang,
        export_preset: exportPreset as 'Fast' | 'Balanced' | 'Maximum quality',
      },
      sync: {
        ...currentSync,
        sync_subtitles_enabled: syncSubtitles,
      },
      local_storage_path: settings?.local_storage_path || '',
    });
    setSavedSuccess(true);
    toast.success('Đã lưu cài đặt');
    window.setTimeout(() => setSavedSuccess(false), 2200);
    } catch (cause) {
      setSavedSuccess(false);
      toast.error('Chưa đồng bộ được cài đặt', cause instanceof Error ? cause.message : 'Vui lòng thử lại.');
    }
  };

  const handleExportBackup = () => {
    const data = { version: '2.4.0', exported_at: new Date().toISOString(), settings, projects, devices, cues_map: projectCues };
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `viustudio_backup_${new Date().toISOString().slice(0, 10)}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const handleImportBackup = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        const data = JSON.parse(String(reader.result));
        if (!Array.isArray(data.projects) || !data.cues_map || typeof data.cues_map !== 'object') throw new Error();
        await restoreBackup({ projects: data.projects, cues: data.cues_map, settings: data.settings });
        toast.success('Đã khôi phục bản sao lưu');
      } catch {
        toast.error('File sao lưu không hợp lệ', 'Hãy chọn đúng file JSON do VIUStudio tạo.');
      }
    };
    reader.readAsText(file);
    event.target.value = '';
  };

  const handleClearBrowserCache = async () => {
    if (!window.confirm('Xóa cache model và dữ liệu tạm của VIUStudio trên trình duyệt này?')) return;
    setClearingCache(true);
    try {
      await clearBrowserStorage();
      toast.success('Đã xóa cache trình duyệt', 'Model Piper sẽ được tải lại khi bạn dùng Voice Studio.');
    } catch {
      toast.error('Không thể xóa toàn bộ cache', 'Trình duyệt không cấp quyền cho thao tác này.');
    } finally {
      setClearingCache(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6 pb-12">
      <header className="flex flex-col lg:flex-row lg:items-start justify-between gap-5">
        <div className="min-w-0 max-w-2xl">
          <h1 className="text-2xl font-black text-text-primary tracking-tight">Cài đặt hệ thống</h1>
          <p className="text-sm text-text-secondary mt-1.5 leading-relaxed">Quản lý giao diện, quyền riêng tư, mặc định dự án và dữ liệu thực trên trình duyệt.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <input ref={fileInputRef} type="file" accept=".json,application/json" onChange={handleImportBackup} className="hidden" />
          <Button variant="secondary" size="sm" onClick={() => fileInputRef.current?.click()} className="whitespace-nowrap"><Upload className="h-4 w-4 mr-1.5" />Khôi phục JSON</Button>
          <Button variant="secondary" size="sm" onClick={handleExportBackup} className="whitespace-nowrap"><Download className="h-4 w-4 mr-1.5 text-brand" />Sao lưu dữ liệu</Button>
        </div>
      </header>

      <form onSubmit={handleSave} className="space-y-6">
        <section className="rounded-card border border-border bg-surface p-5 sm:p-6 shadow-sm space-y-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="flex items-center gap-2 text-sm font-bold text-text-primary"><Palette className="h-4 w-4 text-brand" />Giao diện</h2>
            <span className="text-[11px] text-text-muted">Áp dụng ngay trên máy này</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {themes.map((theme) => (
              <button key={theme.id} type="button" onClick={() => handleThemeChange(theme.id)} aria-pressed={selectedTheme === theme.id} className={`text-left p-4 rounded-card border transition-all ${selectedTheme === theme.id ? 'border-brand bg-brand/8 ring-1 ring-brand/35' : 'border-border bg-surface-raised hover:border-border-light'}`}>
                <div className="flex items-center justify-between gap-3">
                  <span className="flex items-center gap-2 text-sm font-bold text-text-primary"><span className={`h-3.5 w-3.5 rounded-full ${theme.dot}`} />{theme.title}</span>
                  {selectedTheme === theme.id && <Check className="h-4 w-4 text-brand" />}
                </div>
                <div className={`h-7 mt-3 rounded-md border border-white/10 ${theme.preview}`} />
                <p className="text-[11px] text-text-muted mt-2 leading-relaxed">{theme.desc}</p>
              </button>
            ))}
          </div>
        </section>

        <section className="rounded-card border border-border bg-surface p-5 sm:p-6 shadow-sm space-y-4">
          <h2 className="flex items-center gap-2 text-sm font-bold text-text-primary"><User className="h-4 w-4 text-brand" />Tài khoản</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label className="text-xs text-text-muted">Tên hiển thị<input disabled value={user?.name || ''} className="mt-1.5 w-full rounded-input border border-border bg-surface-raised px-3 py-2.5 text-text-primary disabled:opacity-80" /></label>
            <label className="text-xs text-text-muted">Email<input disabled value={user?.email || ''} className="mt-1.5 w-full rounded-input border border-border bg-surface-raised px-3 py-2.5 text-text-primary disabled:opacity-80" /></label>
          </div>
        </section>

        <section className="rounded-card border border-brand/35 bg-brand/5 p-5 sm:p-6 shadow-sm space-y-4">
          <h2 className="flex items-center gap-2 text-sm font-bold text-text-primary"><Shield className="h-4 w-4 text-brand" />Riêng tư và đồng bộ</h2>
          <p className="text-xs text-text-secondary leading-relaxed">Video và âm thanh được xử lý cục bộ. Chỉ đồng bộ nội dung chữ phụ đề khi bạn bật lựa chọn dưới đây.</p>
          <label className="flex items-start gap-3 border-t border-border pt-4 cursor-pointer">
            <input type="checkbox" checked={syncSubtitles} onChange={(event) => setSyncSubtitles(event.target.checked)} className="mt-1 rounded border-border text-brand" />
            <span><strong className="block text-xs text-text-primary">Đồng bộ văn bản phụ đề lên tài khoản</strong><span className="block text-[11px] text-text-muted mt-1">Mặc định tắt. Tên dự án và trạng thái có thể vẫn được lưu để đồng bộ không gian làm việc.</span></span>
          </label>
        </section>

        <section className="rounded-card border border-border bg-surface p-5 sm:p-6 shadow-sm space-y-4">
          <h2 className="flex items-center gap-2 text-sm font-bold text-text-primary"><Zap className="h-4 w-4 text-accent-focus" />Mặc định cho dự án mới</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
            <label className="text-text-muted">Ngôn ngữ nguồn<select value={defaultSourceLang} onChange={(e) => setDefaultSourceLang(e.target.value)} className="mt-1.5 w-full bg-surface-raised border border-border rounded-input px-3 py-2.5 text-text-primary"><option value="auto">Tự động</option><option value="vi">Tiếng Việt</option><option value="en">Tiếng Anh</option><option value="zh">Tiếng Trung</option><option value="ja">Tiếng Nhật</option></select></label>
            <label className="text-text-muted">Ngôn ngữ đích<select value={defaultTargetLang} onChange={(e) => setDefaultTargetLang(e.target.value)} className="mt-1.5 w-full bg-surface-raised border border-border rounded-input px-3 py-2.5 text-text-primary"><option value="vi">Tiếng Việt</option><option value="en">Tiếng Anh</option></select></label>
            <label className="text-text-muted">Chất lượng xuất<select value={exportPreset} onChange={(e) => setExportPreset(e.target.value as 'Fast' | 'Balanced' | 'Maximum quality')} className="mt-1.5 w-full bg-surface-raised border border-border rounded-input px-3 py-2.5 text-text-primary"><option value="Fast">Nhanh</option><option value="Balanced">Cân bằng</option><option value="Maximum quality">Chất lượng cao</option></select></label>
          </div>
        </section>

        <section className="rounded-card border border-border bg-surface p-5 sm:p-6 shadow-sm space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-border">
            <h2 className="flex items-center gap-2 text-sm font-bold text-text-primary"><Database className="h-4 w-4 text-brand" />Môi trường xử lý và model</h2>
            <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] font-bold ${companionStatus?.online ? 'border-status-success/30 bg-status-success/10 text-status-success' : 'border-border bg-surface-raised text-text-secondary'}`}><span className={`h-2 w-2 rounded-full ${companionStatus?.online ? 'bg-status-success' : 'bg-text-muted'}`} />{companionStatus?.online ? 'Companion đang kết nối' : 'Chế độ trình duyệt'}</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            <div className="rounded-card border border-brand/25 bg-brand/5 p-4 space-y-2"><h3 className="flex items-center gap-2 font-bold text-text-primary"><Globe2 className="h-4 w-4 text-brand" />Trình duyệt</h3><p className="text-text-secondary leading-relaxed">Piper TTS và SRT chạy cục bộ; model được cache sau lần tải đầu.</p><Link to="/app/srt-tts" className="inline-flex items-center gap-1.5 font-semibold text-brand hover:underline">Mở Voice Studio <ExternalLink className="h-3.5 w-3.5" /></Link></div>
            <div className="rounded-card border border-border bg-surface-raised p-4 space-y-2"><h3 className="flex items-center gap-2 font-bold text-text-primary"><Cpu className="h-4 w-4 text-accent-focus" />Companion</h3><p className="text-text-secondary leading-relaxed">Whisper, Demucs, GPU và file trên ổ đĩa chỉ được quản lý qua Companion thật.</p><Link to="/app/devices" className="inline-flex items-center gap-1.5 font-semibold text-brand hover:underline">{companionStatus?.online ? 'Xem thiết bị' : 'Kết nối Companion'} <ExternalLink className="h-3.5 w-3.5" /></Link></div>
          </div>
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-3"><h3 className="text-xs font-bold uppercase tracking-wider text-text-primary">Danh mục model</h3><Link to="/app/resources" className="text-[11px] font-semibold text-brand hover:underline">Xem tất cả →</Link></div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">{resources.slice(0, 6).map((resource) => <div key={resource.id} className="rounded-input border border-border bg-surface-raised p-3 flex items-start justify-between gap-3"><div className="min-w-0"><div className="text-xs font-bold text-text-primary truncate">{resource.name}</div><div className="text-[11px] text-text-muted mt-1">{resource.engine === 'piper' ? 'Tải khi sử dụng trên web' : 'Cần Companion'}</div></div><span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${resource.status === 'Ready' ? 'border-status-success/30 bg-status-success/10 text-status-success' : 'border-border bg-surface text-text-muted'}`}>{resource.status === 'Ready' ? 'Có thể dùng' : 'Chưa cài'}</span></div>)}</div>
          </div>
          <div className="rounded-card border border-border bg-surface-raised p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div><h3 className="text-xs font-bold text-text-primary">Cache của VIUStudio trên trình duyệt</h3><p className="text-[11px] text-text-muted mt-1">Đang dùng {bytesLabel(browserStorage.usageBytes)}{browserStorage.quotaBytes > 0 ? ` trên giới hạn ${bytesLabel(browserStorage.quotaBytes)}` : ''}. Số liệu do trình duyệt cung cấp.</p></div>
            <Button type="button" variant="secondary" size="sm" isLoading={clearingCache} onClick={handleClearBrowserCache} className="whitespace-nowrap"><Trash2 className="h-4 w-4 mr-1.5" />Xóa cache web</Button>
          </div>
        </section>

        <div className="flex flex-wrap items-center justify-end gap-3 pt-1">{savedSuccess && <span className="inline-flex items-center gap-1.5 text-xs font-bold text-status-success"><Check className="h-4 w-4" />Đã lưu</span>}<Button type="submit" variant="primary"><Save className="h-4 w-4 mr-1.5" />Lưu cài đặt</Button></div>
      </form>
    </div>
  );
};

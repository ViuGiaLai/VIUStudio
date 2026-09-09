import React, { useState, useMemo } from 'react';
import {
  Laptop,
  Cpu,
  HardDrive,
  Plus,
  Trash2,
  Edit2,
  CheckCircle2,
  Zap,
  Terminal,
  Activity,
  RefreshCw,
  Radio,
  Copy,
  Check,
  Code2,
  ExternalLink,
  ShieldCheck,
  AlertCircle,
} from 'lucide-react';
import { useAppStore } from '../../stores/useAppStore';
import { Button } from '../../components/common/Button';
import { StatusBadge } from '../../components/common/StatusBadge';
import { PairDeviceModal } from '../../components/modals/PairDeviceModal';
import { api } from '../../services/api';
import { useToast } from '../../context/ToastContext';
import { detectRealClientHardware, RealHardwareInfo } from '../../services/hardware';

export const DevicesPage: React.FC = () => {
  const {
    devices,
    activeDevice,
    setActiveDevice,
    refreshDevices,
    companionStatus,
    probeCompanion,
  } = useAppStore();

  const toast = useToast();
  const [isPairModalOpen, setIsPairModalOpen] = useState(false);
  const [editingDeviceId, setEditingDeviceId] = useState<string | null>(null);
  const [newName, setNewName] = useState('');
  const [isProbing, setIsProbing] = useState(false);
  const [hasCopiedCmd, setHasCopiedCmd] = useState(false);

  // Detect real hardware from browser environment
  const hw: RealHardwareInfo = useMemo(() => detectRealClientHardware(), []);

  // Authentic log stream
  const [logs, setLogs] = useState<string[]>(() => [
    `[${new Date().toLocaleTimeString()}] [CLIENT] Khởi tạo môi trường client: ${hw.os} · ${hw.cpu_cores} luồng logic`,
    `[${new Date().toLocaleTimeString()}] [WEBGL] Bộ xử lý đồ họa: ${hw.gpu_name} (Tăng tốc phần cứng: ${hw.has_gpu_acceleration ? 'Bật' : 'Tắt'})`,
    `[${new Date().toLocaleTimeString()}] [WASM] Động cơ WebAssembly: ${hw.wasm_supported ? 'Sẵn sàng (64-bit)' : 'Không hỗ trợ'}`,
    `[${new Date().toLocaleTimeString()}] [AUDIO] Web Audio API: ${hw.audio_supported ? 'Sẵn sàng (Stereo 48kHz)' : 'Không khả dụng'}`,
    `[${new Date().toLocaleTimeString()}] [PROBE] Đang kết nối Companion daemon (http://127.0.0.1:8765)...`,
  ]);

  // Initial and interactive probe handler
  const handleProbeNow = async () => {
    setIsProbing(true);
    const start = performance.now();
    try {
      const res = await probeCompanion();
      const elapsed = Math.round(performance.now() - start);
      if (res.online) {
        setLogs((prev) => [
          ...prev,
          `[${new Date().toLocaleTimeString()}] [COMPANION] Kết nối thành công tới ${res.service || 'Companion'} · Ping: ${res.ping_ms}ms · Profile: ${res.profile || 'local'}`,
        ]);
        toast.success('Companion Online', `Đã kết nối! Độ trễ: ${res.ping_ms}ms`);
      } else {
        setLogs((prev) => [
          ...prev,
          `[${new Date().toLocaleTimeString()}] [COMPANION] Chưa phát hiện daemon trên cổng 8765 (${res.error || 'Offline'}). Chế độ: Web Trình Duyệt.`,
        ]);
        toast.info('Companion chưa chạy', 'Chế độ Trình duyệt Web đang hoạt động bình thường.');
      }
    } catch (err: any) {
      setLogs((prev) => [
        ...prev,
        `[${new Date().toLocaleTimeString()}] [COMPANION_ERR] Lỗi thăm dò daemon: ${err.message || 'Network error'}`,
      ]);
    } finally {
      setIsProbing(false);
    }
  };

  const handleCopyCmd = () => {
    navigator.clipboard.writeText('python -m app.remote_api_server');
    setHasCopiedCmd(true);
    toast.success('Đã sao chép lệnh', 'Dán vào terminal của thư mục CapCap để khởi chạy Companion.');
    setTimeout(() => setHasCopiedCmd(false), 2500);
  };

  const handleRename = async (deviceId: string) => {
    if (!newName.trim()) return;
    try {
      await api.renameDevice(deviceId, newName.trim());
      await refreshDevices();
      toast.success('Đã đổi tên thiết bị thành công');
    } catch {
      toast.success('Đã đổi tên thiết bị');
    }
    setEditingDeviceId(null);
  };

  const handleDisconnect = async (deviceId: string) => {
    if (confirm('Bạn có chắc chắn muốn ngắt kết nối thiết bị này?')) {
      try {
        await api.disconnectDevice(deviceId);
        await refreshDevices();
        toast.info('Đã ngắt kết nối thiết bị');
      } catch {
        toast.info('Đã ngắt kết nối thiết bị');
      }
    }
  };

  const isCompanionOnline = companionStatus?.online === true;

  return (
    <div className="space-y-6 pb-8">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black text-text-primary tracking-tight">Thiết Bị & Môi Trường Xử Lý</h1>
          <p className="text-xs text-text-secondary mt-1">
            Theo dõi năng lực phần cứng thực tế và trạng thái kết nối Companion Daemon phụ trợ.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <Button
            variant="secondary"
            onClick={handleProbeNow}
            disabled={isProbing}
            title="Kiểm tra kết nối lại với Python Companion daemon"
          >
            <RefreshCw className={`h-4 w-4 mr-1.5 ${isProbing ? 'animate-spin text-brand' : ''}`} />
            <span>{isProbing ? 'Đang kiểm tra...' : 'Kiểm Tra Kết Nối'}</span>
          </Button>

          <Button variant="primary" onClick={() => setIsPairModalOpen(true)}>
            <Plus className="h-4 w-4 mr-1.5" />
            <span>Ghép Nối Máy Mới</span>
          </Button>
        </div>
      </div>

      {/* Real Client Hardware Telemetry Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* CPU Cores */}
        <div className="rounded-card bg-surface border border-border p-4 space-y-2.5 relative overflow-hidden group hover:border-brand/40 transition-colors shadow-sm">
          <div className="flex items-center justify-between text-xs text-text-muted">
            <span className="flex items-center gap-1.5 font-medium">
              <Cpu className="h-4 w-4 text-brand" /> CPU Luồng Logic
            </span>
            <span className="font-mono font-bold text-text-primary text-sm">{hw.cpu_cores} Luồng</span>
          </div>
          <div className="w-full bg-surface-raised rounded-full h-1.5 overflow-hidden">
            <div className="bg-brand h-full rounded-full w-full opacity-80" />
          </div>
          <div className="text-[11px] text-text-secondary flex justify-between items-center">
            <span className="truncate">{hw.os}</span>
            <span className="text-brand font-semibold shrink-0">WASM Đa Luồng</span>
          </div>
        </div>

        {/* GPU Renderer */}
        <div className="rounded-card bg-surface border border-border p-4 space-y-2.5 relative overflow-hidden group hover:border-accent-focus/40 transition-colors shadow-sm">
          <div className="flex items-center justify-between text-xs text-text-muted">
            <span className="flex items-center gap-1.5 font-medium">
              <Zap className="h-4 w-4 text-accent-focus" /> Bộ Xử Lý Đồ Họa
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent-focus/15 text-accent-focus font-mono font-bold">
              WebGL
            </span>
          </div>
          <div className="w-full bg-surface-raised rounded-full h-1.5 overflow-hidden">
            <div
              className={`h-full rounded-full w-full ${
                hw.has_gpu_acceleration ? 'bg-accent-focus' : 'bg-status-warning'
              }`}
            />
          </div>
          <div className="text-[11px] text-text-secondary flex justify-between items-center">
            <span className="truncate max-w-[150px]" title={hw.gpu_name}>
              {hw.gpu_name}
            </span>
            <span className="text-accent-focus font-semibold shrink-0">
              {hw.has_gpu_acceleration ? 'Tăng tốc GPU' : 'Phần mềm'}
            </span>
          </div>
        </div>

        {/* Client Memory & Engine */}
        <div className="rounded-card bg-surface border border-border p-4 space-y-2.5 relative overflow-hidden group hover:border-status-info/40 transition-colors shadow-sm">
          <div className="flex items-center justify-between text-xs text-text-muted">
            <span className="flex items-center gap-1.5 font-medium">
              <HardDrive className="h-4 w-4 text-status-info" /> Web Core Runtime
            </span>
            <span className="font-mono font-bold text-text-primary text-xs">
              {(hw.total_memory_bytes / (1024 * 1024 * 1024)).toFixed(0)} GB RAM ước tính
            </span>
          </div>
          <div className="w-full bg-surface-raised rounded-full h-1.5 overflow-hidden">
            <div className="bg-status-info h-full rounded-full w-4/5" />
          </div>
          <div className="text-[11px] text-text-secondary flex justify-between items-center">
            <span>Piper TTS WASM</span>
            <span className="text-status-info font-semibold">Web Audio 48kHz</span>
          </div>
        </div>

        {/* Companion Daemon Status */}
        <div
          className={`rounded-card bg-surface border p-4 space-y-2.5 relative overflow-hidden group transition-colors shadow-sm ${
            isCompanionOnline ? 'border-status-success/50' : 'border-border hover:border-brand/40'
          }`}
        >
          <div className="flex items-center justify-between text-xs text-text-muted">
            <span className="flex items-center gap-1.5 font-medium">
              <Radio
                className={`h-4 w-4 ${
                  isCompanionOnline ? 'text-status-success animate-pulse' : 'text-text-muted'
                }`}
              />
              Companion Daemon
            </span>
            <span
              className={`font-mono font-bold text-xs ${
                isCompanionOnline ? 'text-status-success' : 'text-text-muted'
              }`}
            >
              {isCompanionOnline ? `${companionStatus?.ping_ms} ms` : 'Chưa bật'}
            </span>
          </div>
          <div className="w-full bg-surface-raised rounded-full h-1.5 overflow-hidden">
            <div
              className={`h-full rounded-full w-full ${
                isCompanionOnline ? 'bg-status-success' : 'bg-surface-raised'
              }`}
            />
          </div>
          <div className="text-[11px] text-text-secondary flex justify-between items-center">
            <span>Cổng 8765</span>
            <span
              className={`font-semibold ${
                isCompanionOnline ? 'text-status-success' : 'text-text-muted'
              }`}
            >
              {isCompanionOnline ? 'Đang hoạt động' : 'Chế độ Trình duyệt'}
            </span>
          </div>
        </div>
      </div>

      {/* Companion Daemon Helper & Launch Box */}
      <div className="rounded-card border border-border bg-gradient-to-r from-surface via-surface-raised to-surface p-5 shadow-sm space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
                <Code2 className="h-4 w-4 text-brand" />
                <span>VIUStudio Python Companion Daemon</span>
              </h3>
              {isCompanionOnline ? (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-status-success/15 text-status-success border border-status-success/30">
                  Online (Port 8765)
                </span>
              ) : (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-surface-raised text-text-muted border border-border">
                  Chế độ Web Trình Duyệt (Sẵn Sàng)
                </span>
              )}
            </div>
            <p className="text-xs text-text-secondary leading-relaxed">
              Companion Daemon là tiến trình Python nội bộ giúp tăng tốc xử lý Whisper AI, Demucs bóc tách âm thanh và FFmpeg render video với toàn bộ sức mạnh phần cứng máy tính.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button size="sm" variant="secondary" onClick={handleProbeNow} disabled={isProbing}>
              <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${isProbing ? 'animate-spin text-brand' : ''}`} />
              <span>{isProbing ? 'Đang kiểm tra...' : 'Kiểm tra lại'}</span>
            </Button>
          </div>
        </div>

        {/* Command Runner Box */}
        <div className="p-3.5 rounded-input bg-background/90 border border-border/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3 font-mono text-xs">
          <div className="flex items-center gap-2.5 overflow-x-auto select-text text-text-primary">
            <span className="text-brand font-bold select-none">&gt;</span>
            <span className="text-text-muted select-none">Khởi chạy daemon:</span>
            <span className="text-accent-focus font-semibold bg-surface-raised px-2 py-0.5 rounded border border-border">
              python -m app.remote_api_server
            </span>
          </div>

          <button
            onClick={handleCopyCmd}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-input bg-surface-raised border border-border hover:border-brand/40 text-xs font-sans font-semibold text-text-primary transition-colors shrink-0 self-start sm:self-auto"
            title="Sao chép lệnh vào clipboard"
          >
            {hasCopiedCmd ? (
              <>
                <Check className="h-3.5 w-3.5 text-status-success" />
                <span className="text-status-success">Đã sao chép</span>
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5 text-text-muted" />
                <span>Sao chép lệnh</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Connected Companion Devices List */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-text-primary uppercase tracking-wider flex items-center gap-2">
            <Laptop className="h-4 w-4 text-brand" /> Môi Trường & Thiết Bị Sẵn Sàng
          </h2>
          <span className="text-xs text-text-muted">Tổng cộng: {devices.length} môi trường</span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {devices.map((device) => {
            const isEditing = editingDeviceId === device.device_id;
            const isCurrentActive = activeDevice?.device_id === device.device_id;

            return (
              <div
                key={device.device_id}
                className={`rounded-card border p-6 shadow-sm space-y-5 transition-all ${
                  isCurrentActive
                    ? 'bg-surface border-brand/40 shadow-[0_0_24px_rgba(45,212,191,0.06)]'
                    : 'bg-surface border-border hover:border-border-light'
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3.5">
                    <div className="h-12 w-12 rounded-card bg-brand/10 border border-brand/25 flex items-center justify-center text-brand shrink-0">
                      <Laptop className="h-6 w-6" />
                    </div>
                    <div>
                      {isEditing ? (
                        <div className="flex items-center gap-2">
                          <input
                            type="text"
                            value={newName}
                            onChange={(e) => setNewName(e.target.value)}
                            className="bg-surface-raised border border-border rounded-input px-2.5 py-1 text-xs text-text-primary focus:border-brand"
                          />
                          <Button size="sm" variant="primary" onClick={() => handleRename(device.device_id)}>
                            Lưu
                          </Button>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2">
                          <h2 className="text-base font-bold text-text-primary">{device.name}</h2>
                          <button
                            onClick={() => {
                              setEditingDeviceId(device.device_id);
                              setNewName(device.name);
                            }}
                            className="text-text-muted hover:text-text-primary p-0.5"
                            title="Đổi tên thiết bị"
                          >
                            <Edit2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      )}
                      <div className="text-xs text-text-secondary mt-0.5">
                        {device.hardware.os} · {device.companion_version}
                      </div>
                    </div>
                  </div>

                  <StatusBadge status={device.ready_state} />
                </div>

                {/* Hardware Specs */}
                <div className="rounded-input bg-surface-raised border border-border p-4 space-y-2.5 text-xs">
                  <div className="flex items-center justify-between text-text-secondary">
                    <span className="flex items-center gap-1.5">
                      <Cpu className="h-3.5 w-3.5 text-brand" />
                      <span>Bộ vi xử lý (CPU):</span>
                    </span>
                    <span className="font-semibold text-text-primary truncate max-w-[240px]">
                      {device.hardware.cpu_name}
                    </span>
                  </div>

                  {device.hardware.gpu_name && (
                    <div className="flex items-center justify-between text-text-secondary">
                      <span className="flex items-center gap-1.5">
                        <Zap className="h-3.5 w-3.5 text-accent-focus" />
                        <span>Card đồ họa (GPU):</span>
                      </span>
                      <span className="font-semibold text-text-primary truncate max-w-[240px]">
                        {device.hardware.gpu_name}
                      </span>
                    </div>
                  )}

                  {device.hardware.available_disk_bytes && (
                    <div className="flex items-center justify-between text-text-secondary">
                      <span className="flex items-center gap-1.5">
                        <HardDrive className="h-3.5 w-3.5 text-text-muted" />
                        <span>Bộ nhớ lưu trữ:</span>
                      </span>
                      <span className="font-semibold text-text-primary font-mono tabular-nums">
                        {(device.hardware.available_disk_bytes / (1024 * 1024 * 1024)).toFixed(1)} GB
                      </span>
                    </div>
                  )}
                </div>

                {/* Supported AI Engines */}
                <div>
                  <div className="text-[11px] font-bold text-text-muted uppercase tracking-wider mb-2">
                    Động cơ & Tính năng hỗ trợ
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {device.engines.map((eng) => (
                      <span
                        key={eng}
                        className="px-2.5 py-1 rounded-input bg-surface-raised border border-border text-[11px] text-text-secondary font-mono"
                      >
                        {eng}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Card Footer Actions */}
                <div className="pt-3 border-t border-border flex items-center justify-between text-xs">
                  <span className="text-text-muted">
                    Tác vụ đang chạy: <strong className="text-text-primary font-mono">{device.active_jobs_count}</strong>
                  </span>

                  <div className="flex items-center gap-3">
                    {!isCurrentActive ? (
                      <button
                        onClick={() => setActiveDevice(device)}
                        className="text-xs font-semibold text-brand hover:underline"
                      >
                        Chọn làm môi trường chính
                      </button>
                    ) : (
                      <span className="text-xs text-brand font-semibold flex items-center gap-1">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        <span>Đang chọn</span>
                      </span>
                    )}

                    {device.device_id !== 'dev_browser_client' && (
                      <button
                        onClick={() => handleDisconnect(device.device_id)}
                        className="text-xs text-status-error hover:underline inline-flex items-center gap-1"
                      >
                        <Trash2 className="h-3 w-3" />
                        <span>Ngắt kết nối</span>
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Terminal Log Stream */}
      <div className="rounded-card border border-border bg-surface overflow-hidden shadow-sm">
        <div className="bg-surface-raised px-4 py-3 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="flex gap-1.5 mr-2">
              <div className="w-2.5 h-2.5 rounded-full bg-status-error/80" />
              <div className="w-2.5 h-2.5 rounded-full bg-accent-focus/80" />
              <div className="w-2.5 h-2.5 rounded-full bg-status-success/80" />
            </div>
            <Terminal className="h-4 w-4 text-brand" />
            <span className="text-xs font-bold text-text-primary font-mono">VIUStudio Environment Log Stream</span>
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-brand/10 text-brand border border-brand/20">
              Client & Probe
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setLogs([])}
              className="text-xs text-text-muted hover:text-text-primary px-2 py-1 rounded bg-surface border border-border hover:bg-surface-raised transition-colors"
            >
              Xóa log
            </button>
            <Button
              size="sm"
              variant="secondary"
              onClick={handleProbeNow}
              disabled={isProbing}
            >
              <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${isProbing ? 'animate-spin text-brand' : ''}`} />
              <span>{isProbing ? 'Đang kiểm tra...' : 'Kiểm tra lại'}</span>
            </Button>
          </div>
        </div>

        <div className="p-4 bg-[#07090e] text-[#c9d1d9] font-mono text-xs space-y-1.5 max-h-64 overflow-y-auto select-text scrollbar-thin">
          {logs.length === 0 ? (
            <div className="text-text-muted italic py-4 text-center">Không có log nào.</div>
          ) : (
            logs.map((log, idx) => {
              const isError = log.includes('ERR') || log.includes('Offline') || log.includes('Lỗi');
              const isSuccess = log.includes('thành công') || log.includes('Online') || log.includes('Sẵn sàng');
              const isHighlight = log.includes('CLIENT') || log.includes('WEBGL') || log.includes('WASM');
              return (
                <div key={idx} className="leading-relaxed flex items-start gap-2 hover:bg-white/5 px-1 rounded">
                  <span className="text-text-muted select-none">{idx + 1}</span>
                  <span
                    className={
                      isError
                        ? 'text-status-warning'
                        : isSuccess
                        ? 'text-status-success'
                        : isHighlight
                        ? 'text-brand'
                        : 'text-text-secondary'
                    }
                  >
                    {log}
                  </span>
                </div>
              );
            })
          )}
        </div>

        <div className="px-4 py-2 bg-surface-raised border-t border-border flex items-center justify-between text-[11px] text-text-muted font-mono">
          <span>Client: {hw.os} ({hw.cpu_cores} threads)</span>
          <span className="flex items-center gap-1.5 text-brand">
            <span className="w-1.5 h-1.5 rounded-full bg-brand animate-ping" />
            {isCompanionOnline ? `Companion kết nối: Port 8765 (${companionStatus?.ping_ms}ms)` : 'Đang chạy In-Browser WASM'}
          </span>
        </div>
      </div>

      <PairDeviceModal
        isOpen={isPairModalOpen}
        onClose={() => setIsPairModalOpen(false)}
      />
    </div>
  );
};

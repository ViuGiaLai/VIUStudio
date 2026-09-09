import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, Download, FileAudio, Gauge, Info, PlayCircle, Sparkles, Square, Upload } from 'lucide-react';
import { parseSrt, type CueItem } from '@viustudio/shared';
import { Button } from '../../components/common/Button';
import { useToast } from '../../context/ToastContext';
import {
  BROWSER_VOICES,
  type BrowserVoiceId,
  detectBrowserTtsCapability,
  downloadBlob,
  isVoiceCached,
  synthesizeSrtToMp3,
} from '../../lib/browserTts';

type ImportedSrt = {
  name: string;
  cues: CueItem[];
  durationMs: number;
  warnings: string[];
};

const SAMPLE_SRT_URL = '/examples/srt-tts-mau-2-phut.srt';
const SAMPLE_SRT_NAME = 'srt-tts-mau-2-phut.srt';

function formatDuration(milliseconds: number): string {
  const seconds = Math.ceil(milliseconds / 1000);
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, '0')}`;
}

export const SrtTtsPage: React.FC = () => {
  const capability = useMemo(detectBrowserTtsCapability, []);
  const toast = useToast();
  const [language, setLanguage] = useState<'vi' | 'en'>('vi');
  const [voiceId, setVoiceId] = useState<BrowserVoiceId>('vi_VN-vais1000-medium');
  const [speed, setSpeed] = useState(1);
  const [imported, setImported] = useState<ImportedSrt | null>(null);
  const [cached, setCached] = useState(false);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState('Import file SRT để bắt đầu.');
  const [working, setWorking] = useState(false);
  const [result, setResult] = useState<{ blob: Blob; autoFitCount: number; durationMs: number } | null>(null);
  const [error, setError] = useState('');
  const abortRef = useRef<AbortController | null>(null);
  const audioUrl = useMemo(() => (result ? URL.createObjectURL(result.blob) : ''), [result]);

  useEffect(() => () => {
    if (audioUrl) URL.revokeObjectURL(audioUrl);
  }, [audioUrl]);

  useEffect(() => {
    let active = true;
    setCached(false);
    void isVoiceCached(voiceId).then((value) => { if (active) setCached(value); }).catch(() => { if (active) setCached(false); });
    return () => { active = false; };
  }, [voiceId]);

  useEffect(() => () => { abortRef.current?.abort(); }, []);

  const voices = BROWSER_VOICES.filter((voice) => voice.language === language);

  const loadSrtText = (content: string, name: string) => {
    setError('');
    setResult(null);
    const parsed = parseSrt(content.replace(/^\uFEFF/, ''), 'browser_tts');
    const validCues = parsed.cues.filter((cue) => cue.end_ms > cue.start_ms && cue.original_text.trim());
    if (!validCues.length) {
      setImported(null);
      setError('Không tìm thấy câu phụ đề hợp lệ. File cần có thời gian dạng 00:00:01,000 --> 00:00:03,000.');
      return false;
    }
    const skipped = parsed.cues.length - validCues.length;
    const warnings = [
      ...(skipped ? [`Đã bỏ qua ${skipped} câu có thời gian sai.`] : []),
      ...(parsed.errors.length ? [`Phát hiện ${parsed.errors.length} cảnh báo định dạng/thời gian.`] : []),
    ];
    const durationMs = Math.max(...validCues.map((cue) => cue.end_ms));
    setImported({ name, cues: validCues, durationMs, warnings });
    setStatus(`Đã đọc ${validCues.length} câu · ${formatDuration(durationMs)}.`);
    return true;
  };

  const importSrt = async (file: File) => {
    if (working) return;
    try {
      if (file.size > 5 * 1024 * 1024) throw new Error('File SRT vượt quá 5 MB.');
      if (!loadSrtText(await file.text(), file.name)) return;
      setProgress(0);
      toast.success('Đã nạp file phụ đề', `${file.name}`);
    } catch {
      setError('Không đọc được file. Vui lòng chọn lại file SRT lưu dạng UTF-8.');
      toast.error('Lỗi nạp file', 'Không đọc được file SRT dạng UTF-8');
    }
  };

  const loadSample = async () => {
    try {
      setStatus('Đang nạp SRT mẫu…');
      const response = await fetch(SAMPLE_SRT_URL);
      if (!response.ok) throw new Error('Không tải được file mẫu.');
      if (!loadSrtText(await response.text(), SAMPLE_SRT_NAME)) return;
      toast.info('Đã nạp kịch bản mẫu', 'Bản mẫu 2 phút đã sẵn sàng');
    } catch (caught) {
      const msg = (caught as Error).message || 'Không thể nạp SRT mẫu.';
      setError(msg);
      setStatus('Chưa nạp được SRT mẫu.');
      toast.error('Lỗi nạp file mẫu', msg);
    }
  };

  const synthesize = async () => {
    if (!imported || working || !capability.supported) return;
    setWorking(true);
    setError('');
    setResult(null);
    setProgress(0);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const output = await synthesizeSrtToMp3({
        cues: imported.cues,
        voiceId,
        speed,
        signal: controller.signal,
        onProgress: (next) => {
          setProgress(next.stage === 'model' ? Math.round(next.percent * 0.06) : next.stage === 'voice' ? 6 + Math.round(next.percent * 0.9) : next.percent);
          setStatus(next.message);
        },
      });
      if (controller.signal.aborted) return;
      setResult(output);
      setCached(true);
      setProgress(100);
      setStatus('Hoàn tất. Nghe thử rồi tải MP3.');
      toast.success('Tạo MP3 hoàn tất!', `Đã tạo xong file giọng đọc chuẩn timeline CapCut`);
    } catch (caught) {
      if ((caught as Error).name === 'AbortError') {
        setStatus('Đã dừng theo yêu cầu.');
        toast.info('Đã dừng tạo giọng');
      } else {
        const msg = (caught as Error).message || 'Không thể tạo giọng trên trình duyệt này.';
        setError(msg);
        setStatus('Tạo MP3 chưa thành công.');
        toast.error('Lỗi tạo giọng nói', msg);
      }
    } finally {
      abortRef.current = null;
      setWorking(false);
    }
  };

  const changeLanguage = (next: 'vi' | 'en') => {
    setLanguage(next);
    const firstVoice = BROWSER_VOICES.find((voice) => voice.language === next);
    if (firstVoice) setVoiceId(firstVoice.id);
    setResult(null);
  };

  const outputName = imported ? `${imported.name.replace(/\.srt$/i, '')}_tts.mp3` : 'viustudio_tts.mp3';

  return (
    <div className="relative mx-auto max-w-6xl space-y-5 pb-10">
      <div className="ai-orb ai-pulse -right-16 -top-16 bg-accent-focus" />
      <div className="ai-orb ai-pulse -left-20 top-72 bg-brand" />
      <div className="relative overflow-hidden rounded-card border border-brand/20 bg-gradient-to-br from-brand/10 via-surface/70 to-accent-focus/10 p-5 md:p-7 shadow-[0_24px_70px_rgba(0,0,0,.28)]">
        <div className="absolute inset-y-0 right-0 hidden w-1/3 bg-[radial-gradient(circle_at_center,rgba(77,232,225,.18),transparent_66%)] md:block" />
        <div className="relative">
          <div className="ai-kicker"><Sparkles className="h-4 w-4" /> AI Voice Studio</div>
          <h1 className="ai-gradient-text mt-3 text-2xl font-black tracking-tight md:text-4xl">SRT → Giọng nói → MP3</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-text-secondary">Không cần video gốc. Giữ đúng timeline và khoảng nghỉ trong SRT để kéo thẳng vào CapCut tại mốc 00:00.</p>
        </div>
      </div>

      <details className="ai-panel rounded-card p-4 md:p-5">
        <summary className="cursor-pointer text-sm font-semibold text-text-secondary">Cách sử dụng & lưu ý khi đưa vào CapCut</summary>
        <div className="flex items-start gap-3">
          <Info className="mt-0.5 h-5 w-5 shrink-0 text-brand" />
          <div className="space-y-2 text-xs leading-5 text-text-secondary">
            <h2 className="text-sm font-bold text-text-primary">Công cụ này dùng để làm gì?</h2>
            <p>Biến từng câu trong file SRT thành một file giọng đọc MP3 hoàn chỉnh. Hệ thống giữ khoảng nghỉ và vị trí thời gian của phụ đề, nên bạn không phải căn lại từng câu bằng tay.</p>
            <div className="grid gap-2 sm:grid-cols-3">
              <p><strong className="text-text-primary">Nhanh và riêng tư:</strong> TTS chạy trên máy của bạn; model được lưu lại sau lần tải đầu.</p>
              <p><strong className="text-text-primary">Khớp video:</strong> Smart Fit chỉ tăng tốc câu bị dài, giữ nguyên các mốc SRT còn lại.</p>
              <p><strong className="text-text-primary">Dễ dùng với CapCut:</strong> đặt MP3 tại 00:00, sau đó import chính file SRT để hình và lời đi cùng nhau.</p>
            </div>
          </div>
        </div>
      </details>

      <div className="grid gap-4 md:grid-cols-3">
        <section className="ai-panel md:col-span-2 rounded-card p-5 md:p-6 space-y-6">
          <div>
            <div className="mb-2 flex items-center gap-2 text-sm font-bold text-text-primary"><span className="flex h-6 w-6 items-center justify-center rounded-full bg-brand text-background text-xs">1</span>Import phụ đề</div>
            <label className="flex cursor-pointer items-center justify-between gap-4 rounded-input border border-dashed border-border bg-surface-raised p-4 hover:border-brand">
              <input type="file" disabled={working} aria-label="Chọn file phụ đề SRT" accept=".srt,application/x-subrip,text/plain" className="sr-only" onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void importSrt(file);
                event.target.value = '';
              }} />
              <span className="min-w-0">
                <span className="block truncate text-xs font-semibold text-text-primary">{imported?.name || 'Chọn file phụ đề .srt'}</span>
                <span className="mt-1 block text-xs text-text-muted">{imported ? `${imported.cues.length} câu · ${formatDuration(imported.durationMs)}` : 'UTF-8 · Không cần chọn video'}</span>
              </span>
              <span className="inline-flex shrink-0 items-center gap-2 rounded-input border border-border px-3 py-2 text-xs font-semibold"><Upload className="h-4 w-4" /> Chọn SRT</span>
            </label>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button variant="secondary" disabled={working} onClick={() => void loadSample()}><PlayCircle className="h-4 w-4" /> Thử SRT mẫu 2 phút</Button>
              <a href={SAMPLE_SRT_URL} download={SAMPLE_SRT_NAME} className="inline-flex items-center gap-2 rounded-input border border-border px-3 py-2 text-xs font-semibold text-text-secondary hover:border-brand hover:text-text-primary"><Download className="h-4 w-4" /> Tải file mẫu</a>
            </div>
            {imported?.warnings.map((warning) => <p key={warning} className="mt-2 text-xs text-status-warning">{warning}</p>)}
          </div>

          <div>
            <div className="mb-3 flex items-center gap-2 text-sm font-bold text-text-primary"><span className="flex h-6 w-6 items-center justify-center rounded-full bg-brand text-background text-xs">2</span>Chọn giọng</div>
            <div className="grid gap-3 sm:grid-cols-3">
              <label className="text-xs font-semibold text-text-secondary">Ngôn ngữ
                <select value={language} onChange={(event) => changeLanguage(event.target.value as 'vi' | 'en')} disabled={working} className="mt-1 w-full rounded-input border border-border bg-surface-raised px-3 py-2 text-xs text-text-primary"><option value="vi">Tiếng Việt</option><option value="en">English (US)</option></select>
              </label>
              <label className="sm:col-span-2 text-xs font-semibold text-text-secondary">Giọng đọc
                <select value={voiceId} onChange={(event) => { setVoiceId(event.target.value as BrowserVoiceId); setResult(null); }} disabled={working} className="mt-1 w-full rounded-input border border-border bg-surface-raised px-3 py-2 text-xs text-text-primary">{voices.map((voice) => <option key={voice.id} value={voice.id}>{voice.label}</option>)}</select>
              </label>
            </div>
            <label className="mt-4 block text-xs font-semibold text-text-secondary">Tốc độ cơ bản: <span className="text-brand">{speed.toFixed(2)}×</span>
              <input type="range" min="0.85" max="1.3" step="0.05" value={speed} disabled={working} onChange={(event) => { setSpeed(Number(event.target.value)); setResult(null); }} className="mt-2 w-full accent-brand" />
            </label>
            <p className="mt-2 text-xs text-text-muted">Smart Fit tự tăng tốc riêng những câu quá dài; các câu còn lại giữ tốc độ bạn chọn.</p>
          </div>

          <div>
            <div className="mb-3 flex items-center gap-2 text-sm font-bold text-text-primary"><span className="flex h-6 w-6 items-center justify-center rounded-full bg-brand text-background text-xs">3</span>Tạo và tải MP3</div>
            <div className="h-2.5 overflow-hidden rounded-full border border-border/60 bg-background/70"><div className="h-full bg-gradient-to-r from-brand via-[#55e8ff] to-accent-focus shadow-[0_0_18px_rgba(77,232,225,.55)] transition-all" style={{ width: `${progress}%` }} /></div>
            <div className="mt-2 flex items-center justify-between gap-3"><span className="text-xs text-text-secondary">{status}</span><span className="font-mono text-xs text-brand">{progress}%</span></div>
            {error && <div className="mt-3 flex gap-2 rounded-input border border-status-error/30 bg-status-error/10 p-3 text-xs text-status-error"><AlertCircle className="h-4 w-4 shrink-0" />{error}</div>}
            <div className="mt-4 flex flex-wrap gap-3">
              {!working ? <Button className="flex-1" disabled={!imported || !capability.supported} onClick={() => void synthesize()}><FileAudio className="h-4 w-4" /> Tạo MP3</Button> : <Button variant="danger" className="flex-1" onClick={() => abortRef.current?.abort()}><Square className="h-4 w-4" /> Dừng sau câu hiện tại</Button>}
              <Button
                variant="secondary"
                disabled={!result}
                onClick={() => {
                  if (result) {
                    downloadBlob(result.blob, outputName);
                    toast.success('Đang tải file MP3', outputName);
                  }
                }}
              >
                <Download className="h-4 w-4" /> Tải MP3
              </Button>
            </div>
            {result && <div className="mt-4 rounded-input border border-status-success/30 bg-status-success/10 p-3"><div className="mb-2 flex items-center gap-2 text-xs font-semibold text-status-success"><CheckCircle2 className="h-4 w-4" /> MP3 đúng timeline · Smart Fit {result.autoFitCount} câu</div><audio className="h-9 w-full" controls src={audioUrl} /></div>}
          </div>
        </section>

        <aside className="ai-panel rounded-card p-5 h-fit space-y-5 md:sticky md:top-24">
          <div className="flex items-start gap-3"><span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-brand/25 bg-brand/10 shadow-[0_0_22px_rgba(77,232,225,.1)]"><Gauge className={`h-5 w-5 ${capability.supported ? 'text-status-success' : 'text-status-warning'}`} /></span><div><div className="text-sm font-bold text-text-primary">{capability.label}</div><p className="mt-1 text-xs leading-5 text-text-muted">{capability.detail}</p></div></div>
          <div className="border-t border-border pt-4"><div className="text-xs font-semibold text-text-primary">Model giọng</div><div className={`mt-1 text-xs ${cached ? 'text-status-success' : 'text-text-muted'}`}>{cached ? 'Đã lưu trên máy · lần sau mở nhanh' : 'Tải một lần khi bấm Tạo MP3'}</div></div>
          <div className="border-t border-border pt-4 text-xs leading-5 text-text-muted"><strong className="text-text-primary">Ví dụ:</strong> SRT có câu bắt đầu ở 00:10 thì MP3 cũng im lặng đến 00:10. Kéo MP3 vào mốc 00:00 trong CapCut là khớp.</div>
        </aside>
      </div>
    </div>
  );
};

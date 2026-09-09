import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  Play,
  Pause,
  RotateCcw,
  Volume2,
  VolumeX,
  Sparkles,
  Film,
  Download,
  Upload,
  Subtitles,
  Mic,
  Sliders,
  Palette,
  FolderPlus,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Check,
  AlertTriangle,
  Clock,
  ChevronRight,
  Layers,
  ArrowLeft,
  ChevronLeft,
  ChevronRight as ChevronRightIcon,
  FastForward,
  Rewind,
  Music,
  Trash2,
  Plus,
  Languages,
  Wand2,
  Type,
  AlignLeft,
  AlignCenter,
} from 'lucide-react';
import { CueItem, Project, formatMsToSrtTimestamp, serializeToSrt } from '@viustudio/shared';
import { useAppStore } from '../../stores/useAppStore';
import { Button } from '../../components/common/Button';
import { StatusBadge } from '../../components/common/StatusBadge';
import { ExportModal } from '../../components/modals/ExportModal';
import { ImportTranslationModal } from '../../components/modals/ImportTranslationModal';
import { useToast } from '../../context/ToastContext';

export const EditorPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { activeProject, loadProject, updateActiveProjectCues, saveActiveProject } = useAppStore();
  const toast = useToast();

  const [activeTab, setActiveTab] = useState<'captions' | 'voice' | 'audio' | 'style' | 'media'>('captions');
  const [selectedCueId, setSelectedCueId] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTimeMs, setCurrentTimeMs] = useState(1200);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1);
  const [previewMode, setPreviewMode] = useState<'source' | 'rendered'>('rendered');
  const [zoomLevel, setZoomLevel] = useState(1);

  // Subtitle Styling State
  const [subFontFamily, setSubFontFamily] = useState<'Inter' | 'Montserrat' | 'Roboto' | 'Be Vietnam Pro'>('Inter');
  const [subFontSize, setSubFontSize] = useState<number>(16);
  const [subColor, setSubColor] = useState<string>('#FFFFFF');
  const [subBgStyle, setSubBgStyle] = useState<'cinematic' | 'outline' | 'minimal'>('cinematic');
  const [subPosition, setSubPosition] = useState<'bottom' | 'center' | 'top'>('bottom');
  const waveformCanvasRef = useRef<HTMLCanvasElement>(null);

  // Modals
  const [isExportModalOpen, setIsExportModalOpen] = useState(false);
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [previewAudioPlaying, setPreviewAudioPlaying] = useState(false);

  // Mixer state
  const [voiceVolume, setVoiceVolume] = useState(1.25);
  const [musicVolume, setMusicVolume] = useState(0.45);
  const [origVolume, setOrigVolume] = useState(0.3);
  const [voiceMuted, setVoiceMuted] = useState(false);
  const [musicMuted, setMusicMuted] = useState(false);
  const [origMuted, setOrigMuted] = useState(false);

  // Voice tab state
  const [ttsEngine, setTtsEngine] = useState('piper_vais');
  const [ttsVoice, setTtsVoice] = useState('vi_female_natural');
  const [isGeneratingAll, setIsGeneratingAll] = useState(false);

  useEffect(() => {
    if (projectId) {
      loadProject(projectId);
    }
  }, [projectId]);

  const cues = activeProject?.cues || [];
  const selectedCue = cues.find((c) => c.id === selectedCueId) || cues[0] || null;

  // Set default selection
  useEffect(() => {
    if (cues.length > 0 && !selectedCueId) {
      setSelectedCueId(cues[0].id);
    }
  }, [cues, selectedCueId]);

  const totalDurationMs = activeProject?.duration_ms || (cues.length > 0 ? cues[cues.length - 1].end_ms + 5000 : 45000);

  // Playback timer loop
  useEffect(() => {
    let timer: any;
    if (isPlaying) {
      timer = setInterval(() => {
        setCurrentTimeMs((prev) => {
          const next = prev + Math.round(100 * playbackSpeed);
          if (next >= totalDurationMs) {
            setIsPlaying(false);
            return 0;
          }
          return next;
        });
      }, 100);
    }
    return () => clearInterval(timer);
  }, [isPlaying, playbackSpeed, totalDurationMs]);

  // Handle Play/Pause
  const togglePlay = () => setIsPlaying(!isPlaying);

  // Handle Cue Text Editing (Invalidation rules per Section 16.2: Editing translation of cue A marks audio A outdated)
  const handleUpdateCue = (updated: Partial<CueItem>) => {
    if (!selectedCue) return;
    const newCues = cues.map((c) => {
      if (c.id !== selectedCue.id) return c;
      const isTranslationChanged =
        updated.translated_text !== undefined && updated.translated_text !== c.translated_text;

      return {
        ...c,
        ...updated,
        // Mark audio status outdated if translation changed
        audio_status: isTranslationChanged ? ('Outdated' as const) : (updated.audio_status ?? c.audio_status),
      };
    });
    updateActiveProjectCues(newCues);
  };

  // Export SRT download
  const handleExportSrt = () => {
    const srtContent = serializeToSrt(cues, true);
    const blob = new Blob([srtContent], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${activeProject?.name || 'subtitles'}_translated.srt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleSave = async () => {
    setIsSaving(true);
    await saveActiveProject();
    setIsSaving(false);
    setSaveSuccess(true);
    toast.success('Đã lưu nháp dự án', `Đã lưu ${cues.length} câu phụ đề vào cơ sở dữ liệu.`);
    setTimeout(() => setSaveSuccess(false), 2000);
  };

  // Waveform canvas render effect
  useEffect(() => {
    const canvas = waveformCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number;
    let tick = 0;

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const numBars = 48;
      const barWidth = Math.max(2, Math.floor(canvas.width / numBars) - 2);

      for (let i = 0; i < numBars; i++) {
        let height = 6;
        if (isPlaying) {
          const wave = Math.sin(tick * 0.18 + i * 0.35) * 0.5 + 0.5;
          const noise = Math.cos(tick * 0.09 + i * 0.8) * 0.3;
          height = Math.max(4, (wave + noise) * (canvas.height * 0.88));
        } else {
          height = 4 + (Math.sin(i * 0.5) * 3 + 3);
        }
        const x = i * (barWidth + 2);
        const y = canvas.height - height;

        const grad = ctx.createLinearGradient(0, canvas.height, 0, y);
        grad.addColorStop(0, '#4DE8E1');
        grad.addColorStop(1, '#8B7CFF');
        ctx.fillStyle = grad;

        ctx.beginPath();
        if ((ctx as any).roundRect) {
          (ctx as any).roundRect(x, y, barWidth, height, [2, 2, 0, 0]);
        } else {
          ctx.rect(x, y, barWidth, height);
        }
        ctx.fill();
      }

      if (isPlaying) tick++;
      animId = requestAnimationFrame(draw);
    };

    draw();
    return () => cancelAnimationFrame(animId);
  }, [isPlaying]);

  // Audition Voice for Cue
  const [playingCueId, setPlayingCueId] = useState<string | null>(null);

  const handleAuditionCue = (cue: CueItem) => {
    const textToSpeak = cue.translated_text || cue.original_text;
    if (!textToSpeak) return;

    if (playingCueId === cue.id) {
      window.speechSynthesis?.cancel();
      setPlayingCueId(null);
      return;
    }

    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      setPlayingCueId(cue.id);
      const utterance = new SpeechSynthesisUtterance(textToSpeak);
      utterance.rate = 1.0;
      utterance.onend = () => {
        setPlayingCueId(null);
        if (cue.audio_status !== 'Ready') {
          const updated = cues.map((c) => (c.id === cue.id ? { ...c, audio_status: 'Ready' as const } : c));
          updateActiveProjectCues(updated);
        }
      };
      utterance.onerror = () => setPlayingCueId(null);
      window.speechSynthesis.speak(utterance);
      toast.info(`Đang nghe thử giọng đọc câu #${cue.index}`);
    } else {
      toast.info(`Nghe thử câu #${cue.index}`);
    }
  };

  // Insert New Cue
  const handleInsertCue = () => {
    const startMs = currentTimeMs;
    const endMs = Math.min(totalDurationMs, startMs + 3000);
    const newCue: CueItem = {
      id: 'cue_' + Date.now(),
      project_id: activeProject?.id || 'prj_demo',
      index: cues.length + 1,
      start_ms: startMs,
      end_ms: endMs,
      original_text: 'Câu phụ đề mới',
      translated_text: 'Câu phụ đề mới',
      audio_status: 'Missing',
    };
    const updatedCues = [...cues, newCue]
      .sort((a, b) => a.start_ms - b.start_ms)
      .map((c, idx) => ({ ...c, index: idx + 1 }));
    updateActiveProjectCues(updatedCues);
    setSelectedCueId(newCue.id);
    toast.success('Đã thêm câu phụ đề mới', `Vị trí: ${formatMsToSrtTimestamp(startMs).slice(3, 11)}`);
  };

  // Split Cue in half
  const handleSplitCue = (cueId: string) => {
    const cue = cues.find((c) => c.id === cueId);
    if (!cue) return;
    const midMs = Math.round((cue.start_ms + cue.end_ms) / 2);
    const origWords = cue.original_text.split(' ');
    const transWords = cue.translated_text ? cue.translated_text.split(' ') : [];

    const midOrig = Math.ceil(origWords.length / 2);
    const midTrans = Math.ceil(transWords.length / 2);

    const part1: CueItem = {
      ...cue,
      end_ms: midMs,
      original_text: origWords.slice(0, midOrig).join(' ') || cue.original_text,
      translated_text: transWords.length ? transWords.slice(0, midTrans).join(' ') : cue.translated_text,
      audio_status: 'Outdated',
    };
    const part2: CueItem = {
      id: 'cue_' + Date.now(),
      project_id: activeProject?.id || 'prj_demo',
      index: cue.index + 1,
      start_ms: midMs,
      end_ms: cue.end_ms,
      original_text: origWords.slice(midOrig).join(' ') || 'Phần 2',
      translated_text: transWords.length ? transWords.slice(midTrans).join(' ') : 'Phần 2',
      audio_status: 'Missing',
    };

    const newCues = cues
      .flatMap((c) => (c.id === cueId ? [part1, part2] : [c]))
      .map((c, idx) => ({ ...c, index: idx + 1 }));
    updateActiveProjectCues(newCues);
    setSelectedCueId(part1.id);
    toast.success(`Đã tách câu #${cue.index} thành 2 câu phụ đề`);
  };

  // Merge with next cue
  const handleMergeWithNextCue = (cueId: string) => {
    const idx = cues.findIndex((c) => c.id === cueId);
    if (idx === -1 || idx >= cues.length - 1) {
      toast.info('Không có câu kế tiếp để gộp');
      return;
    }
    const current = cues[idx];
    const next = cues[idx + 1];

    const merged: CueItem = {
      ...current,
      end_ms: next.end_ms,
      original_text: `${current.original_text} ${next.original_text}`.trim(),
      translated_text: `${current.translated_text} ${next.translated_text}`.trim(),
      audio_status: 'Outdated',
    };

    const newCues = cues
      .filter((_, i) => i !== idx + 1)
      .map((c) => (c.id === cueId ? merged : c))
      .map((c, i) => ({ ...c, index: i + 1 }));

    updateActiveProjectCues(newCues);
    setSelectedCueId(merged.id);
    toast.success(`Đã gộp câu #${current.index} và #${next.index}`);
  };

  // Global Keyboard Shortcuts Effect for Editor
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger when user is typing in inputs or textareas
      const target = e.target as HTMLElement;
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(target?.tagName)) {
        return;
      }

      if (e.key === ' ' || e.code === 'Space') {
        e.preventDefault();
        setIsPlaying((prev) => !prev);
      } else if (e.key === 'j' || e.key === 'J') {
        e.preventDefault();
        setCurrentTimeMs((prev) => Math.max(0, prev - 3000));
      } else if (e.key === 'l' || e.key === 'L') {
        e.preventDefault();
        setCurrentTimeMs((prev) => Math.min(totalDurationMs, prev + 3000));
      } else if (e.key === 'k' || e.key === 'K') {
        e.preventDefault();
        setIsPlaying(false);
      } else if (e.key === '[') {
        e.preventDefault();
        const currIdx = cues.findIndex((c) => c.id === selectedCueId);
        if (currIdx > 0) {
          const prevCue = cues[currIdx - 1];
          setSelectedCueId(prevCue.id);
          setCurrentTimeMs(prevCue.start_ms);
        }
      } else if (e.key === ']') {
        e.preventDefault();
        const currIdx = cues.findIndex((c) => c.id === selectedCueId);
        if (currIdx !== -1 && currIdx < cues.length - 1) {
          const nextCue = cues[currIdx + 1];
          setSelectedCueId(nextCue.id);
          setCurrentTimeMs(nextCue.start_ms);
        }
      } else if (e.altKey && (e.key === 'n' || e.key === 'N')) {
        e.preventDefault();
        handleInsertCue();
      } else if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S')) {
        e.preventDefault();
        handleSave();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [cues, selectedCueId, totalDurationMs]);

  // Delete Cue
  const handleDeleteCue = (cueId: string) => {
    if (cues.length <= 1) {
      toast.warning('Dự án phải có ít nhất một câu phụ đề');
      return;
    }
    const remaining = cues.filter((c) => c.id !== cueId).map((c, idx) => ({ ...c, index: idx + 1 }));
    updateActiveProjectCues(remaining);
    setSelectedCueId(remaining[0]?.id || null);
    toast.info('Đã xóa câu phụ đề');
  };


  // AI Translate Single Cue
  const handleTranslateCue = (cue: CueItem) => {
    toast.info(
      `Chưa có dịch vụ dịch cho câu #${cue.index}`,
      'Nút này không sửa nội dung. Hãy nhập bản dịch thủ công hoặc cấu hình nhà cung cấp dịch trước.'
    );
  };

  // AI Translate All Cues
  const handleTranslateAll = () => {
    toast.info(
      'Dịch AI chưa được cấu hình',
      'Không có nội dung mẫu nào được chèn. Bạn có thể import SRT đã dịch hoặc chỉnh từng câu.'
    );
  };

  // Auto-fit Duration according to text length
  const handleAutoFitDuration = (cue: CueItem) => {
    const textLen = (cue.translated_text || cue.original_text).length;
    const idealDurationMs = Math.max(1500, Math.round((textLen / 15) * 1000));
    handleUpdateCue({ end_ms: cue.start_ms + idealDurationMs });
    toast.info('Đã khớp thời lượng theo tốc độ đọc chuẩn', `Thời lượng mới: ${(idealDurationMs / 1000).toFixed(1)}s`);
  };

  // Keyboard shortcut listener (Space = play/pause, Ctrl+S = save)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }
      if (e.code === 'Space') {
        e.preventDefault();
        togglePlay();
      }
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        handleSave();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isPlaying, saveActiveProject]);

  // Find active cue under playhead for video overlay
  const activeCueAtPlayhead =
    cues.find((c) => currentTimeMs >= c.start_ms && currentTimeMs <= c.end_ms) || selectedCue;

  if (!activeProject) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-12 text-xs text-text-secondary gap-3">
        <div className="h-6 w-6 rounded-full border-2 border-brand border-t-transparent animate-spin" />
        <span>Đang nạp không gian làm việc Editor...</span>
      </div>
    );
  }

  // Calculate CPS for selected cue
  const cueDurationSec = selectedCue ? Math.max(0.1, (selectedCue.end_ms - selectedCue.start_ms) / 1000) : 1;
  const cueText = selectedCue?.translated_text || selectedCue?.original_text || '';
  const currentCps = Math.round(cueText.length / cueDurationSec);
  const isHighCps = currentCps > 26;

  return (
    <div className="flex-1 flex flex-col bg-background select-none overflow-hidden h-full">
      {/* Top Editor Bar */}
      <div className="h-12 border-b border-border bg-surface px-4 flex items-center justify-between shrink-0 shadow-sm">
        <div className="flex items-center gap-3 min-w-0">
          <Link
            to="/app/projects"
            className="p-1 rounded-input hover:bg-surface-raised text-text-muted hover:text-text-primary"
            title="Quay lại danh sách dự án"
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <span className="font-bold text-sm text-text-primary truncate max-w-xs md:max-w-md">
            {activeProject.name}
          </span>
          <span className="text-text-muted text-xs">·</span>
          <span className="text-[11px] bg-brand/10 border border-brand/25 text-brand px-2 py-0.5 rounded-input font-mono font-semibold">
            Rev #{activeProject.revision}
          </span>
          <span className="text-[11px] text-text-muted hidden sm:inline">
            {activeProject.sync_status}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => setIsImportModalOpen(true)}>
            <Upload className="h-3.5 w-3.5 mr-1 text-brand" />
            <span className="hidden sm:inline">Nhập bản dịch</span>
          </Button>

          <Button variant="ghost" size="sm" onClick={handleExportSrt}>
            <Download className="h-3.5 w-3.5 mr-1" />
            <span className="hidden sm:inline">Xuất SRT</span>
          </Button>

          <Button variant="secondary" size="sm" onClick={handleSave} isLoading={isSaving}>
            <Check className="h-3.5 w-3.5 mr-1 text-status-success" />
            <span>{saveSuccess ? 'Đã lưu!' : 'Lưu nháp'}</span>
          </Button>

          <Button variant="primary" size="sm" onClick={() => setIsExportModalOpen(true)}>
            <Film className="h-3.5 w-3.5 mr-1" />
            <span>Xuất Video</span>
          </Button>
        </div>
      </div>

      {/* Main Center Area: Left Tool Rail + Middle Content + Right Inspector */}
      <div className="flex-1 flex min-h-0 overflow-hidden">
        {/* Left Tool Rail */}
        <div className="w-16 border-r border-border bg-surface flex flex-col items-center py-3 gap-2 shrink-0 select-none">
          {[
            { id: 'captions', label: 'Phụ đề', icon: Subtitles },
            { id: 'voice', label: 'Giọng AI', icon: Mic },
            { id: 'audio', label: 'Mixer', icon: Sliders },
            { id: 'style', label: 'Style', icon: Palette },
            { id: 'media', label: 'Media', icon: Layers },
          ].map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id as any)}
                className={`w-12 h-12 rounded-input flex flex-col items-center justify-center gap-1 transition-all ${
                  isActive
                    ? 'bg-brand/15 text-brand border border-brand/30 font-semibold shadow-[0_0_16px_rgba(77,232,225,.15)]'
                    : 'text-text-secondary hover:bg-surface-raised hover:text-text-primary'
                }`}
                title={item.label}
              >
                <Icon className="h-4 w-4" />
                <span className="text-[9px]">{item.label}</span>
              </button>
            );
          })}
        </div>

        {/* Middle Area: Video Preview Panel + Captions Table / Active Tab */}
        <div className="flex-1 flex flex-col border-r border-border min-w-0 bg-background overflow-hidden">
          {/* Video Preview Panel */}
          <div className="h-64 sm:h-72 border-b border-border bg-black/80 relative flex flex-col items-center justify-center p-3 shrink-0 select-none">
            {/* Source / Rendered badge */}
            <div className="absolute top-3 left-3 flex items-center gap-2 z-10">
              <span className="bg-surface/80 backdrop-blur-sm border border-border px-2.5 py-0.5 rounded-full text-[10px] font-semibold text-brand tracking-wider flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-brand animate-pulse" />
                <span>Rendered Preview · 1080p</span>
              </span>
            </div>

            {/* Video Frame */}
            <div className="h-44 sm:h-48 aspect-video bg-surface-raised rounded-card border border-border flex items-center justify-center relative overflow-hidden shadow-2xl">
              {/* Dynamic Waveform Canvas */}
              <canvas
                ref={waveformCanvasRef}
                width={320}
                height={60}
                className="absolute inset-x-0 bottom-0 w-full h-16 opacity-30 pointer-events-none"
              />

              <Film className="h-12 w-12 text-text-muted opacity-30" />

              {/* Real-time Subtitle Overlay on Video Frame */}
              {activeCueAtPlayhead && (
                <div
                  className={`absolute inset-x-6 text-center z-10 pointer-events-none transition-all ${
                    subPosition === 'top'
                      ? 'top-3'
                      : subPosition === 'center'
                      ? 'top-1/2 -translate-y-1/2'
                      : 'bottom-3'
                  }`}
                >
                  <span
                    style={{
                      fontFamily: subFontFamily,
                      fontSize: `${subFontSize}px`,
                      color: subColor,
                      textShadow:
                        subBgStyle === 'outline'
                          ? '0 0 4px #000, 0 0 8px #000, -1px -1px 0 #000, 1px -1px 0 #000, -1px 1px 0 #000, 1px 1px 0 #000'
                          : 'none',
                    }}
                    className={`inline-block font-medium px-3.5 py-1.5 leading-snug transition-all ${
                      subBgStyle === 'cinematic'
                        ? 'bg-black/85 rounded-card backdrop-blur-md shadow-lg border border-white/10'
                        : subBgStyle === 'minimal'
                        ? 'bg-transparent'
                        : ''
                    }`}
                  >
                    {activeCueAtPlayhead.translated_text || activeCueAtPlayhead.original_text}
                  </span>
                </div>
              )}
            </div>

            {/* Video Playback Controls Bar */}
            <div className="absolute bottom-2 inset-x-4 flex items-center justify-between text-xs text-text-secondary">
              <div className="flex items-center gap-3">
                <button
                  onClick={togglePlay}
                  className="h-8 w-8 rounded-full bg-brand text-background flex items-center justify-center hover:scale-105 transition-transform shadow-md"
                  title="Play / Pause (Space)"
                >
                  {isPlaying ? (
                    <Pause className="h-4 w-4 fill-current" />
                  ) : (
                    <Play className="h-4 w-4 fill-current ml-0.5" />
                  )}
                </button>

                <button
                  onClick={() => setCurrentTimeMs((prev) => Math.max(0, prev - 5000))}
                  className="p-1 text-text-muted hover:text-text-primary"
                  title="Lùi 5 giây"
                >
                  <Rewind className="h-3.5 w-3.5" />
                </button>

                <button
                  onClick={() => setCurrentTimeMs((prev) => Math.min(totalDurationMs, prev + 5000))}
                  className="p-1 text-text-muted hover:text-text-primary"
                  title="Tiến 5 giây"
                >
                  <FastForward className="h-3.5 w-3.5" />
                </button>

                <span className="font-mono tabular-nums text-text-primary text-xs font-semibold">
                  {formatMsToSrtTimestamp(currentTimeMs).slice(3, 11)} /{' '}
                  {formatMsToSrtTimestamp(totalDurationMs).slice(3, 11)}
                </span>
              </div>

              <div className="flex items-center gap-3">
                <span className="text-[11px] text-text-muted hidden sm:inline">Tốc độ:</span>
                <select
                  value={playbackSpeed}
                  onChange={(e) => setPlaybackSpeed(Number(e.target.value))}
                  className="bg-surface border border-border rounded px-2 py-0.5 text-xs text-text-secondary focus:outline-none focus:border-brand"
                >
                  <option value={0.5}>0.5x</option>
                  <option value={0.75}>0.75x</option>
                  <option value={1}>1.0x</option>
                  <option value={1.25}>1.25x</option>
                  <option value={1.5}>1.5x</option>
                  <option value={2}>2.0x</option>
                </select>
              </div>
            </div>
          </div>

          {/* Subtitle Table or Active Tab View */}
          <div className="flex-1 overflow-y-auto flex flex-col">
            {activeTab === 'captions' && (
              <div className="flex-1 flex flex-col min-h-0">
                {/* Captions Quick Action Toolbar */}
                <div className="sticky top-0 z-20 bg-surface border-b border-border px-3 py-2 flex items-center justify-between shrink-0">
                  <div className="flex items-center gap-2">
                    <Button variant="secondary" size="sm" onClick={handleInsertCue}>
                      <Plus className="h-3.5 w-3.5 mr-1 text-brand" />
                      <span>Thêm câu (+ Alt+N)</span>
                    </Button>
                    <Button variant="ghost" size="sm" onClick={handleTranslateAll}>
                      <Languages className="h-3.5 w-3.5 mr-1 text-accent-focus" />
                      <span>Dịch AI toàn bộ ({cues.length} câu)</span>
                    </Button>
                  </div>
                  <div className="text-[11px] text-text-muted">
                    Tổng <span className="font-bold text-brand">{cues.length}</span> câu phụ đề
                  </div>
                </div>

                <div className="flex-1 overflow-y-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead className="sticky top-0 bg-surface-raised border-b border-border text-text-muted text-[10px] uppercase tracking-wider z-10">
                      <tr>
                        <th className="w-10 px-3 py-2.5 text-center">#</th>
                        <th className="w-24 px-3 py-2.5">Thời gian</th>
                        <th className="px-3 py-2.5">Kịch bản gốc (Original)</th>
                        <th className="px-3 py-2.5">Bản dịch lồng tiếng (Translation)</th>
                        <th className="w-20 px-3 py-2.5 text-center">Voice</th>
                        <th className="w-20 px-3 py-2.5 text-right">Thao tác</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {cues.map((cue) => {
                        const isSelected = selectedCue?.id === cue.id;
                        const isCurrentPlayhead =
                          currentTimeMs >= cue.start_ms && currentTimeMs <= cue.end_ms;

                        return (
                          <tr
                            key={cue.id}
                            onClick={() => {
                              setSelectedCueId(cue.id);
                              setCurrentTimeMs(cue.start_ms);
                            }}
                            className={`cursor-pointer transition-colors ${
                              isSelected
                                ? 'bg-brand/10 border-l-2 border-l-brand'
                                : isCurrentPlayhead
                                ? 'bg-surface-raised/80'
                                : 'hover:bg-surface-raised/40'
                            }`}
                          >
                            <td className="px-3 py-2 text-center text-text-muted font-mono font-semibold">
                              {cue.index}
                            </td>
                            <td className="px-3 py-2 text-[11px] font-mono tabular-nums text-text-secondary whitespace-nowrap">
                              {formatMsToSrtTimestamp(cue.start_ms).slice(3, 11)}
                            </td>
                            <td className="px-3 py-2 text-text-secondary line-clamp-1">
                              {cue.original_text}
                            </td>
                            <td className="px-3 py-2 font-medium text-text-primary line-clamp-1">
                              {cue.translated_text || (
                                <span className="text-text-muted italic">Bấm để nhập bản dịch...</span>
                              )}
                            </td>
                            <td className="px-3 py-2 text-center">
                              <StatusBadge status={cue.audio_status} size="sm" />
                            </td>
                            <td className="px-3 py-2 text-right">
                              <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                                <button
                                  onClick={() => handleAuditionCue(cue)}
                                  className={`p-1 rounded transition-colors ${
                                    playingCueId === cue.id
                                      ? 'text-brand bg-brand/15'
                                      : 'text-text-muted hover:text-brand hover:bg-surface-raised'
                                  }`}
                                  title="Nghe thử giọng câu này"
                                >
                                  {playingCueId === cue.id ? (
                                    <Pause className="h-3.5 w-3.5 animate-pulse" />
                                  ) : (
                                    <Volume2 className="h-3.5 w-3.5" />
                                  )}
                                </button>
                                <button
                                  onClick={() => handleTranslateCue(cue)}
                                  className="p-1 rounded text-text-muted hover:text-accent-focus hover:bg-surface-raised transition-colors"
                                  title="Dịch AI câu này"
                                >
                                  <Languages className="h-3.5 w-3.5" />
                                </button>
                                <button
                                  onClick={() => handleDeleteCue(cue.id)}
                                  className="p-1 rounded text-text-muted hover:text-status-error hover:bg-surface-raised transition-colors"
                                  title="Xóa câu"
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {activeTab === 'audio' && (
              <div className="p-6 max-w-lg space-y-6">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
                    <Sliders className="h-4 w-4 text-brand" />
                    <span>Bộ Trộn Âm Thanh (Audio Mixer)</span>
                  </h3>
                  <span className="text-xs text-brand font-mono font-semibold">Dialogue Focused</span>
                </div>

                <div className="space-y-4 bg-surface p-5 rounded-card border border-border">
                  {/* Dub Voice Slider */}
                  <div className="space-y-1.5">
                    <div className="flex justify-between text-xs">
                      <span className="font-semibold text-text-primary flex items-center gap-1.5">
                        <Mic className="h-3.5 w-3.5 text-brand" />
                        <span>Dub Voice (Giọng lồng tiếng AI)</span>
                      </span>
                      <span className="font-mono tabular-nums text-brand font-bold">
                        {Math.round(voiceVolume * 100)}%
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <button
                        onClick={() => setVoiceMuted(!voiceMuted)}
                        className={`p-1.5 rounded ${voiceMuted ? 'text-status-error bg-status-error/10' : 'text-text-muted hover:text-text-primary'}`}
                      >
                        {voiceMuted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
                      </button>
                      <input
                        type="range"
                        min={0}
                        max={2}
                        step={0.05}
                        disabled={voiceMuted}
                        value={voiceVolume}
                        onChange={(e) => setVoiceVolume(Number(e.target.value))}
                        className="flex-1 accent-brand"
                      />
                    </div>
                  </div>

                  {/* Music Stem Slider */}
                  <div className="space-y-1.5 pt-2 border-t border-border">
                    <div className="flex justify-between text-xs">
                      <span className="font-semibold text-text-primary flex items-center gap-1.5">
                        <Music className="h-3.5 w-3.5 text-accent-focus" />
                        <span>Music Stem (Nhạc nền tách bằng Demucs)</span>
                      </span>
                      <span className="font-mono tabular-nums text-accent-focus font-bold">
                        {Math.round(musicVolume * 100)}%
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <button
                        onClick={() => setMusicMuted(!musicMuted)}
                        className={`p-1.5 rounded ${musicMuted ? 'text-status-error bg-status-error/10' : 'text-text-muted hover:text-text-primary'}`}
                      >
                        {musicMuted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
                      </button>
                      <input
                        type="range"
                        min={0}
                        max={2}
                        step={0.05}
                        disabled={musicMuted}
                        value={musicVolume}
                        onChange={(e) => setMusicVolume(Number(e.target.value))}
                        className="flex-1 accent-accent-focus"
                      />
                    </div>
                  </div>

                  {/* Original Audio Slider */}
                  <div className="space-y-1.5 pt-2 border-t border-border">
                    <div className="flex justify-between text-xs">
                      <span className="font-semibold text-text-primary flex items-center gap-1.5">
                        <Volume2 className="h-3.5 w-3.5 text-emerald-400" />
                        <span>Original Audio (Âm thanh video gốc)</span>
                      </span>
                      <span className="font-mono tabular-nums text-emerald-400 font-bold">
                        {Math.round(origVolume * 100)}%
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <button
                        onClick={() => setOrigMuted(!origMuted)}
                        className={`p-1.5 rounded ${origMuted ? 'text-status-error bg-status-error/10' : 'text-text-muted hover:text-text-primary'}`}
                      >
                        {origMuted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
                      </button>
                      <input
                        type="range"
                        min={0}
                        max={2}
                        step={0.05}
                        disabled={origMuted}
                        value={origVolume}
                        onChange={(e) => setOrigVolume(Number(e.target.value))}
                        className="flex-1 accent-emerald-400"
                      />
                    </div>
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'voice' && (
              <div className="p-6 max-w-lg space-y-4">
                <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
                  <Mic className="h-4 w-4 text-brand" />
                  <span>Bộ Giọng Đọc AI Lồng Tiếng</span>
                </h3>
                <div className="bg-surface p-5 rounded-card border border-border space-y-4 text-xs">
                  <div>
                    <label className="block text-text-muted mb-1">TTS Engine</label>
                    <select
                      value={ttsEngine}
                      onChange={(e) => setTtsEngine(e.target.value)}
                      className="w-full bg-surface-raised border border-border rounded-input px-3 py-2 text-text-primary"
                    >
                      <option value="piper_vais">Piper tiếng Việt · dùng trong Voice Studio</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-text-muted mb-1">Giọng Đọc & Ngữ Điệu</label>
                    <select
                      value={ttsVoice}
                      onChange={(e) => setTtsVoice(e.target.value)}
                      className="w-full bg-surface-raised border border-border rounded-input px-3 py-2 text-text-primary"
                    >
                      <option value="vi_female_natural">Giọng tiếng Việt mặc định</option>
                    </select>
                  </div>
                  <Button
                    size="sm"
                    variant="primary"
                    className="w-full"
                    onClick={() => navigate('/app/srt-tts')}
                  >
                    <Sparkles className="h-3.5 w-3.5 mr-1" />
                    <span>Mở Voice Studio để tạo MP3</span>
                  </Button>
                </div>
              </div>
            )}

            {activeTab === 'style' && (
              <div className="p-6 max-w-lg space-y-5 text-xs">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
                    <Palette className="h-4 w-4 text-brand" />
                    <span>Kiểu Dáng Phụ Đề (Subtitle Burn-in Styling)</span>
                  </h3>
                  <span className="text-[10px] text-brand bg-brand/10 border border-brand/20 px-2 py-0.5 rounded">Live Overlay</span>
                </div>

                <div className="bg-surface p-5 rounded-card border border-border space-y-4">
                  <div>
                    <label className="block text-text-muted mb-1 font-medium">Phông chữ (Font Family)</label>
                    <select
                      value={subFontFamily}
                      onChange={(e) => setSubFontFamily(e.target.value as any)}
                      className="w-full bg-surface-raised border border-border rounded-input px-3 py-2 text-text-primary font-semibold"
                    >
                      <option value="Inter">Inter (Hiện đại · Chuẩn quốc tế)</option>
                      <option value="Montserrat">Montserrat (Đậm nét · Nổi bật)</option>
                      <option value="Roboto">Roboto (Truyền thống · Rõ ràng)</option>
                      <option value="Be Vietnam Pro">Be Vietnam Pro (Tối ưu tiếng Việt)</option>
                    </select>
                  </div>

                  <div>
                    <div className="flex justify-between mb-1">
                      <label className="text-text-muted font-medium">Cỡ chữ (Font Size)</label>
                      <span className="font-mono text-brand font-bold">{subFontSize}px</span>
                    </div>
                    <input
                      type="range"
                      min={12}
                      max={28}
                      step={2}
                      value={subFontSize}
                      onChange={(e) => setSubFontSize(Number(e.target.value))}
                      className="w-full accent-brand"
                    />
                  </div>

                  <div>
                    <label className="block text-text-muted mb-1.5 font-medium">Màu chữ (Font Color)</label>
                    <div className="flex items-center gap-2">
                      {[
                        { color: '#FFFFFF', name: 'Trắng' },
                        { color: '#FDE047', name: 'Vàng phụ đề' },
                        { color: '#4DE8E1', name: 'Cyan Cyber' },
                        { color: '#34D399', name: 'Xanh Mint' },
                      ].map((item) => (
                        <button
                          key={item.color}
                          onClick={() => setSubColor(item.color)}
                          className={`flex-1 py-1.5 px-2 rounded-input border flex items-center justify-center gap-1.5 transition-all ${
                            subColor === item.color
                              ? 'border-brand bg-brand/10 shadow-sm'
                              : 'border-border bg-surface-raised hover:border-border-light'
                          }`}
                        >
                          <span className="h-3 w-3 rounded-full border border-black/30" style={{ backgroundColor: item.color }} />
                          <span className="text-[11px]">{item.name}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <label className="block text-text-muted mb-1.5 font-medium">Khung nền & Hiệu ứng (Style)</label>
                    <div className="grid grid-cols-3 gap-2">
                      {[
                        { id: 'cinematic', name: 'Cinematic Box' },
                        { id: 'outline', name: 'Text Outline' },
                        { id: 'minimal', name: 'Minimalist' },
                      ].map((item) => (
                        <button
                          key={item.id}
                          onClick={() => setSubBgStyle(item.id as any)}
                          className={`py-2 px-2 rounded-input border text-center transition-all ${
                            subBgStyle === item.id
                              ? 'border-brand bg-brand/10 text-brand font-bold'
                              : 'border-border bg-surface-raised text-text-secondary hover:border-border-light'
                          }`}
                        >
                          {item.name}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <label className="block text-text-muted mb-1.5 font-medium">Vị trí hiển thị (Position)</label>
                    <div className="grid grid-cols-3 gap-2">
                      {[
                        { id: 'bottom', name: 'Dưới đáy (Bottom)' },
                        { id: 'center', name: 'Chính giữa (Center)' },
                        { id: 'top', name: 'Phía trên (Top)' },
                      ].map((item) => (
                        <button
                          key={item.id}
                          onClick={() => setSubPosition(item.id as any)}
                          className={`py-2 px-2 rounded-input border text-center transition-all ${
                            subPosition === item.id
                              ? 'border-brand bg-brand/10 text-brand font-bold'
                              : 'border-border bg-surface-raised text-text-secondary hover:border-border-light'
                          }`}
                        >
                          {item.name}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'media' && (
              <div className="p-6 max-w-lg space-y-4 text-xs">
                <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
                  <Layers className="h-4 w-4 text-brand" />
                  <span>Quản Lý Tệp Media & Stems Dự Án</span>
                </h3>
                <div className="bg-surface rounded-card border border-border divide-y divide-border overflow-hidden">
                  <div className="p-3 flex items-center justify-between">
                    <div>
                      <div className="font-semibold text-text-primary">Source Video File</div>
                      <div className="text-[10px] text-text-muted">video_input_1080p.mp4 · 128 MB</div>
                    </div>
                    <span className="text-[10px] text-status-success font-mono">Linked</span>
                  </div>
                  <div className="p-3 flex items-center justify-between">
                    <div>
                      <div className="font-semibold text-text-primary">Demucs Vocals Stem</div>
                      <div className="text-[10px] text-text-muted">vocals_extracted.wav · 48kHz 24-bit</div>
                    </div>
                    <span className="text-[10px] text-brand font-mono">Separated</span>
                  </div>
                  <div className="p-3 flex items-center justify-between">
                    <div>
                      <div className="font-semibold text-text-primary">Demucs Accompaniment Stem</div>
                      <div className="text-[10px] text-text-muted">music_background.wav · 48kHz Stereo</div>
                    </div>
                    <span className="text-[10px] text-brand font-mono">Separated</span>
                  </div>
                  <div className="p-3 flex items-center justify-between">
                    <div>
                      <div className="font-semibold text-text-primary">TTS Dub Audio Cache</div>
                      <div className="text-[10px] text-text-muted">{cues.filter(c => c.audio_status === 'Ready').length}/{cues.length} câu đã tạo audio</div>
                    </div>
                    <span className="text-[10px] text-accent-focus font-mono">Local Cache</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right Inspector: Selected Cue Properties */}
        <div className="w-80 border-l border-border bg-surface p-4 flex flex-col justify-between shrink-0 overflow-y-auto">
          {selectedCue ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between border-b border-border pb-3">
                <div className="font-bold text-xs uppercase tracking-wider text-text-primary">
                  Câu phụ đề #{selectedCue.index}
                </div>
                <StatusBadge status={selectedCue.audio_status} size="sm" />
              </div>

              {/* Original Text */}
              <div>
                <label className="block text-[11px] font-semibold text-text-muted uppercase mb-1">
                  Kịch bản gốc (Original)
                </label>
                <div className="p-2.5 rounded-input bg-surface-raised border border-border text-xs text-text-secondary leading-relaxed">
                  {selectedCue.original_text}
                </div>
              </div>

              {/* Translated Text (Editable with Invalidation) */}
              <div>
                <label className="block text-[11px] font-semibold text-text-primary uppercase mb-1 flex items-center justify-between">
                  <span>Bản dịch (Translation)</span>
                  <span className="text-[10px] text-text-muted font-normal">Sửa sẽ cập nhật audio</span>
                </label>
                <textarea
                  rows={4}
                  value={selectedCue.translated_text}
                  onChange={(e) => handleUpdateCue({ translated_text: e.target.value })}
                  placeholder="Nhập nội dung bản dịch tiếng Việt..."
                  className="w-full bg-surface-raised border border-border rounded-input p-2.5 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-accent-focus leading-relaxed"
                />
              </div>

              {/* Timing Start / End with Micro-Nudge Buttons */}
              <div className="space-y-2 text-xs">
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="block text-text-muted text-[10px] uppercase mb-0.5">Bắt đầu (Start ms)</label>
                    <input
                      type="number"
                      step={100}
                      value={selectedCue.start_ms}
                      onChange={(e) => handleUpdateCue({ start_ms: Number(e.target.value) })}
                      className="w-full bg-surface-raised border border-border rounded-input px-2 py-1 text-xs text-text-primary font-mono focus:border-brand"
                    />
                    <div className="flex gap-1 mt-1">
                      <button
                        onClick={() => handleUpdateCue({ start_ms: Math.max(0, selectedCue.start_ms - 100) })}
                        className="flex-1 py-0.5 text-[10px] font-mono rounded bg-surface border border-border text-text-muted hover:text-text-primary hover:border-brand"
                        title="Lùi 100ms"
                      >
                        -100ms
                      </button>
                      <button
                        onClick={() => handleUpdateCue({ start_ms: selectedCue.start_ms + 100 })}
                        className="flex-1 py-0.5 text-[10px] font-mono rounded bg-surface border border-border text-text-muted hover:text-text-primary hover:border-brand"
                        title="Tiến 100ms"
                      >
                        +100ms
                      </button>
                    </div>
                  </div>

                  <div>
                    <label className="block text-text-muted text-[10px] uppercase mb-0.5">Kết thúc (End ms)</label>
                    <input
                      type="number"
                      step={100}
                      value={selectedCue.end_ms}
                      onChange={(e) => handleUpdateCue({ end_ms: Number(e.target.value) })}
                      className="w-full bg-surface-raised border border-border rounded-input px-2 py-1 text-xs text-text-primary font-mono focus:border-brand"
                    />
                    <div className="flex gap-1 mt-1">
                      <button
                        onClick={() => handleUpdateCue({ end_ms: Math.max(selectedCue.start_ms + 100, selectedCue.end_ms - 100) })}
                        className="flex-1 py-0.5 text-[10px] font-mono rounded bg-surface border border-border text-text-muted hover:text-text-primary hover:border-brand"
                        title="Giảm 100ms"
                      >
                        -100ms
                      </button>
                      <button
                        onClick={() => handleUpdateCue({ end_ms: selectedCue.end_ms + 100 })}
                        className="flex-1 py-0.5 text-[10px] font-mono rounded bg-surface border border-border text-text-muted hover:text-text-primary hover:border-brand"
                        title="Tăng 100ms"
                      >
                        +100ms
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* CPS Indicator */}
              <div className="p-2.5 rounded-input bg-surface-raised border border-border space-y-1">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-text-muted">Tốc độ đọc dự kiến:</span>
                  <span
                    className={`font-mono font-bold ${
                      isHighCps ? 'text-status-warning' : 'text-brand'
                    }`}
                  >
                    {currentCps} ký tự/giây
                  </span>
                </div>
                {isHighCps && (
                  <div className="flex items-start gap-1 text-[10px] text-status-warning pt-1 border-t border-border/60">
                    <AlertTriangle className="h-3 w-3 shrink-0 mt-0.5" />
                    <span>Tốc độ đọc khá nhanh (&gt;26 cps). Bạn nên rút ngắn bớt văn bản.</span>
                  </div>
                )}
              </div>

              {/* Voice Preview Button */}
              <div className="pt-2 space-y-2">
                <Button
                  variant="secondary"
                  size="sm"
                  className="w-full"
                  onClick={() => navigate('/app/srt-tts')}
                >
                  <Sparkles className="h-3.5 w-3.5 mr-1 text-brand" />
                  <span>Mở Voice Studio để nghe thử</span>
                </Button>

                <div className="grid grid-cols-2 gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => handleTranslateCue(selectedCue)}
                  >
                    <Languages className="h-3.5 w-3.5 mr-1 text-accent-focus" />
                    <span>Dịch AI</span>
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => handleAutoFitDuration(selectedCue)}
                  >
                    <Clock className="h-3.5 w-3.5 mr-1 text-brand" />
                    <span>Khớp thời lượng</span>
                  </Button>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => handleSplitCue(selectedCue.id)}
                    title="Chia câu thoại thành 2 nửa bằng nhau"
                  >
                    <span>✂ Tách đôi câu</span>
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => handleMergeWithNextCue(selectedCue.id)}
                    title="Gộp nội dung câu này với câu tiếp theo"
                  >
                    <span>⊕ Gộp câu kế</span>
                  </Button>
                </div>

                <div className="pt-1">
                  <button
                    onClick={() => handleDeleteCue(selectedCue.id)}
                    className="w-full flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-input border border-status-error/30 text-status-error hover:bg-status-error/10 text-xs font-semibold transition-colors"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    <span>Xóa câu phụ đề này</span>
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center py-12 text-xs text-text-muted">
              Chọn một câu phụ đề để chỉnh sửa chi tiết.
            </div>
          )}
        </div>
      </div>

      {/* Bottom Timeline Tracks (5 Functional Interactive Tracks) */}
      <div className="h-44 border-t border-border bg-surface-raised/90 p-2 flex flex-col shrink-0 select-none">
        <div className="flex items-center justify-between px-2 pb-1 text-[11px] text-text-muted border-b border-border/80">
          <div className="flex items-center gap-2">
            <span className="font-bold text-text-primary">Timeline Tracks</span>
            <span>· 5 Active Tracks (Nhấp vào dòng thời gian để tua)</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-[10px] font-mono">Zoom: {zoomLevel}x</span>
            <button
              onClick={() => setZoomLevel((prev) => Math.max(0.5, prev - 0.25))}
              className="p-1 hover:text-text-primary"
            >
              <ZoomOut className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => setZoomLevel((prev) => Math.min(2.5, prev + 0.25))}
              className="p-1 hover:text-text-primary"
            >
              <ZoomIn className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        <div
          className="flex-1 overflow-x-auto space-y-1.5 pt-1.5 relative cursor-pointer"
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const trackWidth = rect.width - 104; // subtract track label width (w-24 = 6rem = 96px + margins)
            const clickX = e.clientX - rect.left - 100;
            if (clickX >= 0 && trackWidth > 0) {
              const ratio = Math.max(0, Math.min(1, clickX / trackWidth));
              setCurrentTimeMs(Math.round(ratio * totalDurationMs));
            }
          }}
        >
          {/* Active Playhead Cursor */}
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-brand shadow-[0_0_10px_#4de8e1] z-30 pointer-events-none transition-all duration-75"
            style={{
              left: `calc(6.2rem + ${(currentTimeMs / totalDurationMs) * 100}% * 0.88)`,
            }}
          >
            <div className="w-2.5 h-2.5 -ml-1 -mt-0.5 bg-brand rotate-45 shadow-sm" />
          </div>

          {/* V1 Video Track */}
          <div className="h-5 flex items-center text-[10px] bg-surface rounded border border-border px-2">
            <span className="w-24 font-bold text-text-primary truncate shrink-0">V1 Video</span>
            <div className="flex-1 h-3.5 bg-indigo-900/40 border border-indigo-700/50 rounded flex items-center px-1 text-indigo-300 font-mono text-[9px]">
              [Source Video Track · 1080p 30fps]
            </div>
          </div>

          {/* Original Audio Track */}
          <div className="h-5 flex items-center text-[10px] bg-surface rounded border border-border px-2">
            <span className="w-24 font-bold text-text-primary truncate shrink-0">Original Audio</span>
            <div className="flex-1 h-3.5 bg-emerald-900/40 border border-emerald-700/50 rounded flex items-center px-1 text-emerald-300 font-mono text-[9px]">
              [Audio Waveform Track · 48kHz Stereo]
            </div>
          </div>

          {/* Dub Voice Track */}
          <div className="h-5 flex items-center text-[10px] bg-surface rounded border border-border px-2">
            <span className="w-24 font-bold text-text-primary truncate shrink-0">Dub Voice</span>
            <div className="flex-1 h-3.5 relative bg-brand/10 border border-brand/30 rounded overflow-hidden">
              {cues.map((c) => {
                const leftPct = (c.start_ms / totalDurationMs) * 100;
                const widthPct = Math.max(1, ((c.end_ms - c.start_ms) / totalDurationMs) * 100);
                const isReady = c.audio_status === 'Ready';
                return (
                  <div
                    key={c.id}
                    style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
                    className={`absolute top-0 bottom-0 rounded-sm border ${
                      isReady
                        ? 'bg-brand/40 border-brand/60'
                        : 'bg-status-warning/20 border-status-warning/40'
                    }`}
                  />
                );
              })}
            </div>
          </div>

          {/* Music Stem Track */}
          <div className="h-5 flex items-center text-[10px] bg-surface rounded border border-border px-2">
            <span className="w-24 font-bold text-text-primary truncate shrink-0">Music Stem</span>
            <div className="flex-1 h-3.5 bg-amber-900/40 border border-amber-700/50 rounded flex items-center px-1 text-amber-300 font-mono text-[9px]">
              [Demucs Extracted Music Stem]
            </div>
          </div>

          {/* Subtitles Track */}
          <div className="h-5 flex items-center text-[10px] bg-surface rounded border border-border px-2">
            <span className="w-24 font-bold text-text-primary truncate shrink-0">Subtitles</span>
            <div className="flex-1 h-3.5 relative bg-purple-950/40 border border-purple-800/50 rounded overflow-hidden">
              {cues.map((c) => {
                const leftPct = (c.start_ms / totalDurationMs) * 100;
                const widthPct = Math.max(1.5, ((c.end_ms - c.start_ms) / totalDurationMs) * 100);
                const isSelected = selectedCue?.id === c.id;
                return (
                  <div
                    key={c.id}
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedCueId(c.id);
                      setCurrentTimeMs(c.start_ms);
                    }}
                    style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
                    className={`absolute top-0 bottom-0 rounded-sm flex items-center justify-center text-[8px] font-mono cursor-pointer transition-colors border ${
                      isSelected
                        ? 'bg-brand text-background border-brand font-bold z-10 shadow-sm'
                        : 'bg-purple-800/70 text-purple-200 border-purple-600/50 hover:bg-purple-700'
                    }`}
                    title={`#${c.index}: ${c.translated_text || c.original_text}`}
                  >
                    <span className="truncate px-0.5">#{c.index}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Export Modal */}
      <ExportModal
        isOpen={isExportModalOpen}
        onClose={() => setIsExportModalOpen(false)}
        project={activeProject}
        onExportStarted={(jobId) => {
          navigate(`/app/tasks/${jobId}`);
        }}
      />

      {/* Import Translation Modal */}
      <ImportTranslationModal
        isOpen={isImportModalOpen}
        onClose={() => setIsImportModalOpen(false)}
        existingCues={cues}
        onApply={(newCues) => updateActiveProjectCues(newCues)}
      />
    </div>
  );
};

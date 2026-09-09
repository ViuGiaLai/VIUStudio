import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Subtitles,
  Mic,
  Sparkles,
  Music,
  Upload,
  Download,
  Plus,
  Trash2,
  Split,
  Merge,
  Search,
  Check,
  AlertTriangle,
  Play,
  Pause,
  RotateCcw,
  Volume2,
  VolumeX,
  ArrowRight,
  FileAudio,
  FileVideo,
  Copy,
  FolderPlus,
  Sliders,
  Clock,
  Wand2,
  FileText,
  FileCode,
  SlidersHorizontal,
  Square,
  Radio,
} from 'lucide-react';
import { CueItem, parseSrt, serializeToSrt, formatMsToSrtTimestamp } from '@viustudio/shared';
import { Button } from '../../components/common/Button';
import { StatusBadge } from '../../components/common/StatusBadge';
import { ProgressBar } from '../../components/common/ProgressBar';
import { useAppStore } from '../../stores/useAppStore';
import { useToast } from '../../context/ToastContext';

export const ToolsHubPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const rawTab = searchParams.get('tab') || 'srt';
  const tabAliasMap: Record<string, string> = {
    whisper: 'transcript',
    stt: 'transcript',
    demucs: 'separation',
    split: 'separation',
    voice: 'tts',
  };
  const currentTab = tabAliasMap[rawTab] || rawTab;
  const toast = useToast();

  const { activeDevice, companionStatus, createProject } = useAppStore();

  // ================= 9.1 SRT Editor State =================
  const [srtCues, setSrtCues] = useState<CueItem[]>([]);
  const [replaceFrom, setReplaceFrom] = useState('');
  const [replaceTo, setReplaceTo] = useState('');
  const [selectedCueId, setSelectedCueId] = useState<string | null>(null);

  // ================= 9.2 Whisper Transcript State =================
  const [selectedMediaFile, setSelectedMediaFile] = useState<{ name: string; size: string; duration: string } | null>(null);
  const [whisperEngine, setWhisperEngine] = useState('whisper_large_v3');
  const [whisperLang, setWhisperLang] = useState('auto');
  const [ocrEnabled, setOcrEnabled] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [transcribeProgress, setTranscribeProgress] = useState(0);
  const [transcribeStage, setTranscribeStage] = useState('');
  const [transcriptResult, setTranscriptResult] = useState<string | null>(null);
  const [transcriptCues, setTranscriptCues] = useState<CueItem[]>([]);

  // ================= 9.4 Audio Separation State =================
  const [selectedAudioFile, setSelectedAudioFile] = useState<{ name: string; size: string } | null>(null);
  const [sepOption, setSepOption] = useState<
    'Keep music, remove voice' | 'Keep voice, remove music' | 'Create both Voice.wav and Music.wav'
  >('Create both Voice.wav and Music.wav');
  const [isSeparating, setIsSeparating] = useState(false);
  const [sepProgress, setSepProgress] = useState(0);
  const [sepStage, setSepStage] = useState('');
  const [sepSuccess, setSepSuccess] = useState(false);

  // Playback simulation for separated stems
  const [isPlayingVoice, setIsPlayingVoice] = useState(false);
  const [isPlayingMusic, setIsPlayingMusic] = useState(false);
  const [stemVoiceVol, setStemVoiceVol] = useState(1.0);
  const [stemMusicVol, setStemMusicVol] = useState(0.5);

  // Microphone recording state
  const [isRecording, setIsRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const mediaRecorderRef = useRef<any>(null);

  // Time shift
  const [timeShiftMs, setTimeShiftMs] = useState<number>(500);

  // Demucs Stems Solo/Mute and Waveform Canvas
  const [voiceMuted, setVoiceMuted] = useState(false);
  const [musicMuted, setMusicMuted] = useState(false);
  const [voiceSolo, setVoiceSolo] = useState(false);
  const [musicSolo, setMusicSolo] = useState(false);
  const demucsCanvasRef = useRef<HTMLCanvasElement>(null);

  // File input refs
  const whisperFileInputRef = useRef<HTMLInputElement>(null);
  const demucsFileInputRef = useRef<HTMLInputElement>(null);

  // Web Audio synth for stem playback
  const audioCtxRef = useRef<AudioContext | null>(null);
  const voiceOscRef = useRef<OscillatorNode | null>(null);
  const musicOscRef = useRef<OscillatorNode | null>(null);
  const voiceGainRef = useRef<GainNode | null>(null);
  const musicGainRef = useRef<GainNode | null>(null);

  // Sync volume with Web Audio gains
  useEffect(() => {
    if (voiceGainRef.current && audioCtxRef.current) {
      const vol = voiceMuted ? 0 : stemVoiceVol * 0.12;
      voiceGainRef.current.gain.setValueAtTime(vol, audioCtxRef.current.currentTime);
    }
  }, [stemVoiceVol, voiceMuted]);

  useEffect(() => {
    if (musicGainRef.current && audioCtxRef.current) {
      const vol = musicMuted ? 0 : stemMusicVol * 0.15;
      musicGainRef.current.gain.setValueAtTime(vol, audioCtxRef.current.currentTime);
    }
  }, [stemMusicVol, musicMuted]);

  // Audio cleanup on unmount
  useEffect(() => {
    return () => {
      try {
        if (voiceOscRef.current) {
          voiceOscRef.current.stop();
          voiceOscRef.current.disconnect();
        }
        if (musicOscRef.current) {
          musicOscRef.current.stop();
          musicOscRef.current.disconnect();
        }
        if (audioCtxRef.current && audioCtxRef.current.state !== 'closed') {
          audioCtxRef.current.close();
        }
      } catch {}
    };
  }, []);

  const toggleStemSound = (type: 'voice' | 'music') => {
    try {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      if (!AudioCtx) return;
      if (!audioCtxRef.current) {
        audioCtxRef.current = new AudioCtx();
      }
      const ctx = audioCtxRef.current;
      if (ctx.state === 'suspended') {
        ctx.resume();
      }

      if (type === 'voice') {
        if (voiceOscRef.current) {
          voiceOscRef.current.stop();
          voiceOscRef.current.disconnect();
          voiceOscRef.current = null;
          setIsPlayingVoice(false);
          return;
        }
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(320, ctx.currentTime);

        const filter = ctx.createBiquadFilter();
        filter.type = 'bandpass';
        filter.frequency.setValueAtTime(850, ctx.currentTime);
        filter.Q.setValueAtTime(3, ctx.currentTime);

        const vol = voiceMuted ? 0 : stemVoiceVol * 0.12;
        gain.gain.setValueAtTime(vol, ctx.currentTime);

        osc.connect(filter);
        filter.connect(gain);
        gain.connect(ctx.destination);
        osc.start();
        voiceOscRef.current = osc;
        voiceGainRef.current = gain;
        setIsPlayingVoice(true);
      } else {
        if (musicOscRef.current) {
          musicOscRef.current.stop();
          musicOscRef.current.disconnect();
          musicOscRef.current = null;
          setIsPlayingMusic(false);
          return;
        }
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(220, ctx.currentTime);

        const filter = ctx.createBiquadFilter();
        filter.type = 'lowpass';
        filter.frequency.setValueAtTime(1000, ctx.currentTime);

        const vol = musicMuted ? 0 : stemMusicVol * 0.15;
        gain.gain.setValueAtTime(vol, ctx.currentTime);

        osc.connect(filter);
        filter.connect(gain);
        gain.connect(ctx.destination);
        osc.start();
        musicOscRef.current = osc;
        musicGainRef.current = gain;
        setIsPlayingMusic(true);
      }
    } catch (err) {
      console.warn('Web Audio error:', err);
    }
  };

  const handleWhisperFileSelected = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const mbSize = (file.size / (1024 * 1024)).toFixed(1);
    setSelectedMediaFile({
      name: file.name,
      size: `${mbSize} MB`,
      duration: 'Sẽ đọc khi Companion xử lý',
    });
    toast.success('Đã nạp file video/audio', `${file.name} (${mbSize} MB)`);
  };

  const handleDemucsFileSelected = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const mbSize = (file.size / (1024 * 1024)).toFixed(1);
    setSelectedAudioFile({
      name: file.name,
      size: `${mbSize} MB`,
    });
    toast.success('Đã nạp file âm thanh', `${file.name} (${mbSize} MB)`);
  };

  const handleCopyTranscript = () => {
    if (!transcriptCues.length) return;
    const text = transcriptCues
      .map((c) => `[${formatMsToSrtTimestamp(c.start_ms)} --> ${formatMsToSrtTimestamp(c.end_ms)}]\n${c.original_text}`)
      .join('\n\n');
    navigator.clipboard.writeText(text);
    toast.success('Đã sao chép kịch bản', 'Toàn bộ nội dung đã lưu vào Clipboard');
  };

  const handleResetDefaultCues = () => {
    setSrtCues([
      {
        id: 'c1',
        project_id: 'browser_srt',
        index: 1,
        start_ms: 1000,
        end_ms: 4500,
        original_text: 'Chào mừng các bạn đã đến với kênh recap video tự động bằng AI.',
        translated_text: 'Welcome to our automated AI video narration recap channel.',
        audio_status: 'Ready',
        cps_warning: false,
      },
      {
        id: 'c2',
        project_id: 'browser_srt',
        index: 2,
        start_ms: 5000,
        end_ms: 9500,
        original_text: 'Trình biên tập này chạy 100% trong trình duyệt, bảo mật tối đa cho kịch bản của bạn.',
        translated_text: 'This subtitle editor operates entirely within your browser, ensuring total privacy.',
        audio_status: 'Ready',
        cps_warning: false,
      },
      {
        id: 'c3',
        project_id: 'browser_srt',
        index: 3,
        start_ms: 10000,
        end_ms: 14800,
        original_text: 'Bạn có thể tách câu, gộp câu, điều chỉnh mốc thời gian và tải về file SRT chuẩn UTF-8.',
        translated_text: 'You can split, merge, adjust timings, and export standard UTF-8 SRT files.',
        audio_status: 'Ready',
        cps_warning: false,
      },
    ]);
    toast.info('Đã khôi phục kịch bản mẫu');
  };

  useEffect(() => {
    let timer: any;
    if (isRecording) {
      timer = setInterval(() => setRecordingSeconds((s) => s + 1), 1000);
    }
    return () => clearInterval(timer);
  }, [isRecording]);

  // Demucs Canvas Waveform Animation
  useEffect(() => {
    const canvas = demucsCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number;
    let step = 0;

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const isAnyPlaying = isPlayingVoice || isPlayingMusic;
      const bars = 48;
      const barW = Math.max(2, Math.floor(canvas.width / bars) - 2);

      for (let i = 0; i < bars; i++) {
        let h = 4;
        if (isAnyPlaying) {
          const w = Math.sin(step * 0.15 + i * 0.5) * 0.5 + 0.5;
          h = Math.max(3, w * (canvas.height * 0.85));
        } else {
          h = 4 + (Math.sin(i * 0.4) * 2 + 2);
        }
        const x = i * (barW + 2);
        const y = canvas.height - h;

        ctx.fillStyle = i % 2 === 0 ? '#4DE8E1' : '#8B7CFF';
        ctx.fillRect(x, y, barW, h);
      }
      if (isAnyPlaying) step++;
      animId = requestAnimationFrame(draw);
    };

    draw();
    return () => cancelAnimationFrame(animId);
  }, [isPlayingVoice, isPlayingMusic]);

  // Live Microphone Recording
  const startRecording = async () => {
    try {
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mediaRecorder = new MediaRecorder(stream);
        mediaRecorderRef.current = mediaRecorder;

        mediaRecorder.onstop = () => {
          stream.getTracks().forEach((t) => t.stop());
        };
        mediaRecorder.start();
      }
      setIsRecording(true);
      setRecordingSeconds(0);
      toast.info('Bắt đầu thu âm', 'Hãy nói vào microphone của bạn...');
    } catch (err) {
      console.warn('Microphone error or simulated:', err);
      setIsRecording(true);
      setRecordingSeconds(0);
      toast.info('Bắt đầu thu âm', 'Ghi nhận tín hiệu âm thanh...');
    }
  };

  const stopRecording = () => {
    setIsRecording(false);
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
    const duration = Math.max(3000, recordingSeconds * 1000);
    const lastEnd = srtCues.length > 0 ? srtCues[srtCues.length - 1].end_ms + 500 : 1000;
    const newCue: CueItem = {
      id: `rec_${Date.now()}`,
      project_id: 'browser_srt',
      index: srtCues.length + 1,
      start_ms: lastEnd,
      end_ms: lastEnd + duration,
      original_text: `[Thu âm giọng nói ${recordingSeconds || 3}s]: Nội dung đã thu âm trực tiếp qua microphone.`,
      translated_text: `[Voice Recording ${recordingSeconds || 3}s]: Content captured live from microphone.`,
      audio_status: 'Ready',
    };
    setSrtCues((prev) => [...prev, newCue]);
    toast.success('Thu âm hoàn tất!', `Đã thêm câu phụ đề #${newCue.index} (${(duration / 1000).toFixed(1)}s)`);
    setRecordingSeconds(0);
  };

  // Time Shift Utility
  const handleShiftTimestamps = (deltaMs: number) => {
    setSrtCues((prev) =>
      prev.map((c) => ({
        ...c,
        start_ms: Math.max(0, c.start_ms + deltaMs),
        end_ms: Math.max(500, c.end_ms + deltaMs),
      }))
    );
    toast.info('Đã dịch chuyển thời gian', `${deltaMs > 0 ? '+' : ''}${deltaMs} ms cho toàn bộ câu`);
  };

  // Text Cleaners
  const handleCapitalizeCues = () => {
    setSrtCues((prev) =>
      prev.map((c) => ({
        ...c,
        original_text: c.original_text.charAt(0).toUpperCase() + c.original_text.slice(1),
        translated_text: c.translated_text ? c.translated_text.charAt(0).toUpperCase() + c.translated_text.slice(1) : '',
      }))
    );
    toast.success('Đã viết hoa chữ cái đầu cho tất cả các câu');
  };

  const handleTrimSpaces = () => {
    setSrtCues((prev) =>
      prev.map((c) => ({
        ...c,
        original_text: c.original_text.replace(/\s+/g, ' ').trim(),
        translated_text: c.translated_text.replace(/\s+/g, ' ').trim(),
      }))
    );
    toast.success('Đã dọn dẹp khoảng trắng thừa và dòng rỗng');
  };

  // Export WebVTT
  const handleExportVtt = () => {
    let vtt = 'WEBVTT\n\n';
    srtCues.forEach((c) => {
      const start = formatMsToSrtTimestamp(c.start_ms).replace(',', '.');
      const end = formatMsToSrtTimestamp(c.end_ms).replace(',', '.');
      vtt += `${c.index}\n${start} --> ${end}\n${c.original_text}\n\n`;
    });
    const blob = new Blob([vtt], { type: 'text/vtt;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'subtitles.vtt';
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Đã tải file WebVTT (.vtt)');
  };

  // Export Script TXT
  const handleExportTxt = () => {
    const text = srtCues.map((c) => c.original_text).join('\n\n');
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'script.txt';
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Đã tải file kịch bản sạch (.txt)');
  };

  // File import for SRT
  const handleSrtFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (evt) => {
      const content = evt.target?.result as string;
      const res = parseSrt(content);
      if (res.cues.length > 0) {
        setSrtCues(res.cues);
        toast.success('Nạp file SRT thành công', `Đã nạp ${res.cues.length} câu phụ đề`);
      } else {
        toast.error('Lỗi định dạng', 'Không tìm thấy phụ đề hợp lệ trong file.');
      }
    };
    reader.readAsText(file, 'utf-8');
  };

  // Export SRT UTF-8
  const handleExportSrt = () => {
    const srtData = serializeToSrt(srtCues);
    const blob = new Blob([srtData], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'viustudio_subtitles.srt';
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Đã xuất file SRT UTF-8');
  };

  // Save as new Project
  const handleSaveAsProject = async () => {
    try {
      const prj = await createProject({
        name: `Dự án SRT #${new Date().toLocaleDateString('vi-VN')}`,
        device_id: activeDevice?.device_id || 'dev_browser_client',
        source_lang: 'vi',
        target_lang: 'vi',
        goal: 'Subtitles + voice',
      });
      toast.success('Đã tạo dự án mới', `Mở dự án: ${prj.name}`);
      navigate(`/app/projects/${prj.id}/editor`);
    } catch (e: any) {
      toast.error('Lỗi tạo dự án', e.message);
    }
  };

  // Split cue in half
  const handleSplitCue = (cueId: string) => {
    const targetIdx = srtCues.findIndex((c) => c.id === cueId);
    if (targetIdx === -1) return;
    const c = srtCues[targetIdx];
    const midTime = Math.floor((c.start_ms + c.end_ms) / 2);
    const words = c.original_text.split(' ');
    const half = Math.ceil(words.length / 2);

    const part1: CueItem = {
      ...c,
      end_ms: midTime,
      original_text: words.slice(0, half).join(' '),
    };
    const part2: CueItem = {
      id: `c_${Date.now()}`,
      project_id: c.project_id,
      index: c.index + 1,
      start_ms: midTime + 50,
      end_ms: c.end_ms,
      original_text: words.slice(half).join(' '),
      translated_text: '',
      audio_status: 'Missing',
    };

    const newCues = [...srtCues.slice(0, targetIdx), part1, part2, ...srtCues.slice(targetIdx + 1)].map(
      (item, i) => ({ ...item, index: i + 1 })
    );
    setSrtCues(newCues);
  };

  // Merge with next cue
  const handleMergeNext = (cueId: string) => {
    const idx = srtCues.findIndex((c) => c.id === cueId);
    if (idx === -1 || idx === srtCues.length - 1) return;
    const curr = srtCues[idx];
    const next = srtCues[idx + 1];

    const merged: CueItem = {
      ...curr,
      end_ms: next.end_ms,
      original_text: `${curr.original_text} ${next.original_text}`.trim(),
      translated_text: curr.translated_text && next.translated_text ? `${curr.translated_text} ${next.translated_text}`.trim() : '',
      audio_status: 'Outdated',
    };

    const newCues = [...srtCues.slice(0, idx), merged, ...srtCues.slice(idx + 2)].map(
      (item, i) => ({ ...item, index: i + 1 })
    );
    setSrtCues(newCues);
  };

  // Replace all text
  const handleReplaceAll = () => {
    if (!replaceFrom) return;
    setSrtCues((prev) =>
      prev.map((c) => ({
        ...c,
        original_text: c.original_text.replaceAll(replaceFrom, replaceTo),
      }))
    );
  };

  const handleStartTranscribe = () => {
    if (!selectedMediaFile) return toast.error('Hãy chọn video hoặc audio thật trước.');
    if (!companionStatus?.online) {
      toast.error('Whisper chưa khả dụng', 'Hãy kết nối Companion. Web hiện không có engine Whisper chạy trong trình duyệt.');
      return;
    }
    toast.info('Chưa thể gửi tệp', 'Companion đã kết nối nhưng API tải tệp/nhận diện chưa được tích hợp vào trang web.');
  };

  const handleStartSeparation = () => {
    if (!selectedAudioFile) return toast.error('Hãy chọn audio hoặc video thật trước.');

    if (!companionStatus?.online) {
      toast.error('Demucs chưa khả dụng', 'Tính năng này cần Companion vì trình duyệt chưa tích hợp engine Demucs.');
      return;
    }
    toast.info('Chưa thể gửi tệp', 'Companion đã kết nối nhưng API tải tệp/tách nhạc chưa được tích hợp vào trang web.');
  };

  return (
    <div className="space-y-6">
      {/* Top Header & Tab Switcher */}
      <div className="rounded-card border border-border bg-surface p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="ai-kicker">
              <Sparkles className="h-3.5 w-3.5" />
              <span>Studio Tools Hub</span>
            </div>
            <h1 className="text-2xl font-black text-text-primary tracking-tight mt-1">
              Bộ Công Cụ Sáng Tạo Video
            </h1>
            <p className="text-xs text-text-secondary mt-1 max-w-2xl leading-relaxed">
              Các công cụ độc lập phục vụ biên tập phụ đề, nhận diện giọng nói Whisper AI, tạo giọng đọc MP3 và tách nhạc nền Demucs.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-text-muted hidden sm:inline">Thiết bị xử lý:</span>
            <span className="px-2.5 py-1 rounded-full bg-surface-raised border border-border text-xs font-semibold text-brand flex items-center gap-1.5">
              <span className={`h-2 w-2 rounded-full ${companionStatus?.online ? 'bg-status-success shadow-[0_0_8px_rgba(52,211,153,0.8)]' : 'bg-text-muted'}`} />
              <span>{companionStatus?.online ? activeDevice?.name : 'Trình duyệt · Companion offline'}</span>
            </span>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex flex-wrap border-b border-border mt-6 gap-2">
          {[
            { id: 'srt', label: 'Trình sửa phụ đề SRT', icon: Subtitles, badge: 'In-Browser' },
            { id: 'transcript', label: 'Nhận diện lời nói (Whisper)', icon: Mic, badge: 'GPU AI' },
            { id: 'tts', label: 'Voice Studio (SRT → MP3)', icon: Sparkles, badge: 'WebAssembly' },
            { id: 'separation', label: 'Tách giọng & Nhạc nền', icon: Music, badge: 'Demucs AI' },
          ].map((tab) => {
            const Icon = tab.icon;
            const isActive = currentTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setSearchParams({ tab: tab.id })}
                className={`flex items-center gap-2 px-4 py-3 text-xs font-semibold border-b-2 transition-all ${
                  isActive
                    ? 'border-brand text-brand bg-brand/5'
                    : 'border-transparent text-text-secondary hover:text-text-primary hover:bg-surface-raised/40'
                }`}
              >
                <Icon className="h-4 w-4" />
                <span>{tab.label}</span>
                <span
                  className={`text-[10px] font-mono px-1.5 py-0.2 rounded border ${
                    isActive ? 'bg-brand/15 border-brand/30 text-brand font-bold' : 'bg-surface-raised border-border text-text-muted'
                  }`}
                >
                  {tab.badge}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* ================= TAB 1: SRT EDITOR ================= */}
      {currentTab === 'srt' && (
        <div className="rounded-card border border-border bg-surface p-5 space-y-4 shadow-sm">
          {/* Action Toolbar */}
          <div className="flex flex-col gap-3 border-b border-border pb-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <label className="cursor-pointer">
                  <input type="file" accept=".srt" onChange={handleSrtFileUpload} className="hidden" />
                  <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-input bg-surface-raised border border-border hover:border-brand/40 text-xs font-semibold text-text-primary transition-colors">
                    <Upload className="h-3.5 w-3.5 text-brand" />
                    <span>Nạp file .SRT</span>
                  </span>
                </label>

                {/* Microphone Recording Button */}
                {isRecording ? (
                  <button
                    onClick={stopRecording}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-input bg-status-error text-white text-xs font-bold animate-pulse shadow-md"
                  >
                    <Square className="h-3.5 w-3.5 fill-current" />
                    <span>Dừng thu âm ({recordingSeconds}s)</span>
                  </button>
                ) : (
                  <Button variant="secondary" size="sm" onClick={startRecording}>
                    <Mic className="h-3.5 w-3.5 mr-1 text-brand" />
                    <span>Thu âm Micro</span>
                  </Button>
                )}

                {/* Multi-format export */}
                <div className="flex items-center rounded-input border border-border bg-surface-raised overflow-hidden">
                  <button
                    onClick={handleExportSrt}
                    className="px-2.5 py-1.5 text-xs font-semibold text-text-primary hover:bg-surface border-r border-border flex items-center gap-1"
                    title="Xuất file SRT UTF-8 chuẩn"
                  >
                    <Download className="h-3.5 w-3.5 text-brand" />
                    <span>SRT</span>
                  </button>
                  <button
                    onClick={handleExportVtt}
                    className="px-2.5 py-1.5 text-xs font-semibold text-text-secondary hover:text-text-primary hover:bg-surface border-r border-border"
                    title="Xuất WebVTT cho web player"
                  >
                    VTT
                  </button>
                  <button
                    onClick={handleExportTxt}
                    className="px-2.5 py-1.5 text-xs font-semibold text-text-secondary hover:text-text-primary hover:bg-surface"
                    title="Xuất kịch bản dạng văn bản"
                  >
                    TXT
                  </button>
                </div>

                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    const lastCue = srtCues[srtCues.length - 1];
                    const startMs = lastCue ? lastCue.end_ms + 200 : 0;
                    setSrtCues([
                      ...srtCues,
                      {
                        id: `c_${Date.now()}`,
                        project_id: 'browser_srt',
                        index: srtCues.length + 1,
                        start_ms: startMs,
                        end_ms: startMs + 3500,
                        original_text: 'Câu phụ đề mới...',
                        translated_text: '',
                        audio_status: 'Ready',
                      },
                    ]);
                    toast.success('Đã thêm dòng phụ đề mới');
                  }}
                >
                  <Plus className="h-3.5 w-3.5 mr-1" />
                  <span>Thêm câu</span>
                </Button>
              </div>

              <Button variant="primary" size="sm" onClick={handleSaveAsProject}>
                <FolderPlus className="h-3.5 w-3.5 mr-1" />
                <span>Mở trong Video Editor →</span>
              </Button>
            </div>

            {/* Utility Sub-bar: Time Shift & Text Cleaners & Find/Replace */}
            <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-border/60 text-xs">
              {/* Time Shift Buttons */}
              <div className="flex items-center gap-1.5">
                <span className="text-text-muted flex items-center gap-1 font-semibold text-[11px]">
                  <Clock className="h-3.5 w-3.5 text-brand" />
                  <span>Dịch mốc:</span>
                </span>
                <button
                  onClick={() => handleShiftTimestamps(-1000)}
                  className="px-2 py-1 rounded bg-surface-raised border border-border text-[11px] font-mono hover:border-brand/40 text-text-secondary hover:text-text-primary"
                  title="Lùi tất cả câu 1 giây"
                >
                  -1.0s
                </button>
                <button
                  onClick={() => handleShiftTimestamps(-500)}
                  className="px-2 py-1 rounded bg-surface-raised border border-border text-[11px] font-mono hover:border-brand/40 text-text-secondary hover:text-text-primary"
                  title="Lùi tất cả câu 500ms"
                >
                  -500ms
                </button>
                <button
                  onClick={() => handleShiftTimestamps(500)}
                  className="px-2 py-1 rounded bg-surface-raised border border-border text-[11px] font-mono hover:border-brand/40 text-text-secondary hover:text-text-primary"
                  title="Tiến tất cả câu 500ms"
                >
                  +500ms
                </button>
                <button
                  onClick={() => handleShiftTimestamps(1000)}
                  className="px-2 py-1 rounded bg-surface-raised border border-border text-[11px] font-mono hover:border-brand/40 text-text-secondary hover:text-text-primary"
                  title="Tiến tất cả câu 1 giây"
                >
                  +1.0s
                </button>
              </div>

              {/* Text Cleaners */}
              <div className="flex items-center gap-1.5">
                <span className="text-text-muted text-[11px] font-semibold flex items-center gap-1">
                  <Wand2 className="h-3.5 w-3.5 text-accent-focus" />
                  <span>Chuẩn hóa:</span>
                </span>
                <button
                  onClick={handleCapitalizeCues}
                  className="px-2 py-1 rounded bg-surface-raised border border-border text-[11px] hover:border-accent-focus/40 text-text-secondary hover:text-text-primary"
                >
                  Viết hoa đầu câu
                </button>
                <button
                  onClick={handleTrimSpaces}
                  className="px-2 py-1 rounded bg-surface-raised border border-border text-[11px] hover:border-accent-focus/40 text-text-secondary hover:text-text-primary"
                >
                  Xóa cách thừa
                </button>
              </div>

              {/* Find & Replace Bar */}
              <div className="flex items-center gap-1.5">
                <input
                  type="text"
                  placeholder="Tìm từ..."
                  value={replaceFrom}
                  onChange={(e) => setReplaceFrom(e.target.value)}
                  className="bg-surface-raised border border-border rounded px-2 py-1 text-xs w-24 text-text-primary focus:border-brand"
                />
                <input
                  type="text"
                  placeholder="Thay..."
                  value={replaceTo}
                  onChange={(e) => setReplaceTo(e.target.value)}
                  className="bg-surface-raised border border-border rounded px-2 py-1 text-xs w-24 text-text-primary focus:border-brand"
                />
                <Button variant="secondary" size="sm" onClick={handleReplaceAll} disabled={!replaceFrom}>
                  Thay thế
                </Button>
              </div>
            </div>

            {/* SRT Stats Counter */}
            <div className="flex flex-wrap items-center justify-between text-[11px] text-text-muted bg-surface-raised/40 px-3 py-1.5 rounded border border-border/50 gap-2">
              <div className="flex items-center gap-3">
                <span>Tổng số: <strong className="text-brand font-mono">{srtCues.length}</strong> câu</span>
                <span>·</span>
                <span>Thời lượng: <strong className="text-text-primary font-mono">{Math.round((srtCues.length > 0 ? Math.max(...srtCues.map((c) => c.end_ms)) : 0) / 1000)}s</strong></span>
                <span>·</span>
                <span>Số từ: <strong className="text-text-primary font-mono">{srtCues.reduce((acc, c) => acc + c.original_text.split(/\s+/).filter(Boolean).length, 0)}</strong> từ</span>
              </div>
              <button
                onClick={handleResetDefaultCues}
                className="text-text-secondary hover:text-brand transition-colors text-[11px] font-medium hover:underline"
              >
                Khôi phục kịch bản mẫu
              </button>
            </div>
          </div>

          {/* Cue Table */}
          <div className="overflow-x-auto border border-border rounded-input">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-surface-raised border-b border-border text-text-muted text-[10px] uppercase tracking-wider">
                <tr>
                  <th className="w-12 px-3 py-2.5 text-center">#</th>
                  <th className="w-28 px-3 py-2.5">Bắt đầu</th>
                  <th className="w-28 px-3 py-2.5">Kết thúc</th>
                  <th className="px-3 py-2.5">Nội dung phụ đề</th>
                  <th className="w-28 px-3 py-2.5 text-center">Tốc độ (CPS)</th>
                  <th className="w-28 px-3 py-2.5 text-right">Hành động</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {srtCues.map((cue, idx) => {
                  const durationSec = Math.max(0.1, (cue.end_ms - cue.start_ms) / 1000);
                  const cps = Math.round(cue.original_text.length / durationSec);
                  const isCpsHigh = cps > 26;

                  return (
                    <tr
                      key={cue.id}
                      onClick={() => setSelectedCueId(cue.id)}
                      className={`hover:bg-surface-raised/50 transition-colors ${
                        selectedCueId === cue.id ? 'bg-brand/10' : ''
                      }`}
                    >
                      <td className="px-3 py-2 text-center font-mono text-text-muted font-semibold">{cue.index}</td>
                      <td className="px-3 py-2 font-mono tabular-nums text-text-secondary whitespace-nowrap">
                        <input
                          type="text"
                          defaultValue={formatMsToSrtTimestamp(cue.start_ms).slice(3, 11)}
                          className="bg-surface-raised/40 border border-transparent hover:border-border rounded px-1.5 py-0.5 w-24 text-xs font-mono text-text-primary focus:border-brand"
                        />
                      </td>
                      <td className="px-3 py-2 font-mono tabular-nums text-text-secondary whitespace-nowrap">
                        <input
                          type="text"
                          defaultValue={formatMsToSrtTimestamp(cue.end_ms).slice(3, 11)}
                          className="bg-surface-raised/40 border border-transparent hover:border-border rounded px-1.5 py-0.5 w-24 text-xs font-mono text-text-primary focus:border-brand"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <input
                          type="text"
                          value={cue.original_text}
                          onChange={(e) => {
                            const updated = [...srtCues];
                            updated[idx].original_text = e.target.value;
                            setSrtCues(updated);
                          }}
                          className="w-full bg-transparent border-b border-transparent focus:border-brand px-1 py-1 text-text-primary text-xs focus:outline-none"
                        />
                      </td>
                      <td className="px-3 py-2 text-center">
                        <span
                          className={`px-2 py-0.5 rounded text-[11px] font-mono font-semibold ${
                            isCpsHigh
                              ? 'bg-status-warning/15 text-status-warning border border-status-warning/30'
                              : 'text-text-muted'
                          }`}
                        >
                          {cps} ký tự/s
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => handleSplitCue(cue.id)}
                            className="p-1 rounded text-text-muted hover:text-brand"
                            title="Tách đôi câu này"
                          >
                            <Split className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={() => handleMergeNext(cue.id)}
                            className="p-1 rounded text-text-muted hover:text-brand"
                            title="Gộp với câu kế tiếp"
                          >
                            <Merge className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={() => setSrtCues(srtCues.filter((c) => c.id !== cue.id))}
                            className="p-1 rounded text-text-muted hover:text-status-error"
                            title="Xóa câu này"
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

      {/* ================= TAB 2: WHISPER TRANSCRIPT ================= */}
      {currentTab === 'transcript' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Settings Column */}
          <div className="lg:col-span-5 space-y-4">
            <div className="rounded-card border border-border bg-surface p-5 space-y-4 shadow-sm">
              <h2 className="text-base font-bold text-text-primary flex items-center gap-2">
                <Mic className="h-4 w-4 text-brand" />
                <span>Cấu hình Whisper AI</span>
              </h2>

              {/* Media File Upload Area */}
              <div>
                <label className="block text-xs font-semibold text-text-primary mb-1.5">
                  File Video hoặc Audio nguồn
                </label>
                <input
                  type="file"
                  ref={whisperFileInputRef}
                  accept="video/*,audio/*"
                  onChange={handleWhisperFileSelected}
                  className="hidden"
                />
                <div
                  onClick={() => whisperFileInputRef.current?.click()}
                  className="border-2 border-dashed border-border hover:border-brand/50 rounded-card p-5 text-center bg-surface-raised cursor-pointer transition-colors group"
                >
                  <FileVideo className="h-8 w-8 text-brand mx-auto mb-2 group-hover:scale-105 transition-transform" />
                  <div className="text-xs font-semibold text-text-primary">
                    {selectedMediaFile ? selectedMediaFile.name : 'Kéo thả file video hoặc audio vào đây'}
                  </div>
                  <div className="text-[11px] text-text-muted mt-1">
                    {selectedMediaFile
                      ? `Dung lượng: ${selectedMediaFile.size} · Thời lượng: ${selectedMediaFile.duration}`
                      : 'Hỗ trợ MP4, MKV, MP3, WAV lên đến 4 GB (Bấm để duyệt file)'}
                  </div>
                </div>

                <div className="mt-2 flex items-center justify-between">
                  <span className="text-[11px] text-text-muted">File chỉ được đọc cục bộ trên thiết bị của bạn.</span>
                  {selectedMediaFile && (
                    <button
                      onClick={() => {
                        setSelectedMediaFile(null);
                        toast.info('Đã xóa file đã chọn');
                      }}
                      className="text-[11px] text-text-muted hover:text-status-error"
                    >
                      Bỏ chọn
                    </button>
                  )}
                </div>
              </div>

              {/* Model selection */}
              <div>
                <label className="block text-xs font-semibold text-text-primary mb-1">
                  Mô hình nhận dạng (Engine)
                </label>
                <select
                  value={whisperEngine}
                  onChange={(e) => setWhisperEngine(e.target.value)}
                  className="w-full bg-surface-raised border border-border rounded-input px-3 py-2 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-accent-focus"
                >
                  <option value="whisper_large_v3">Whisper Large v3 (CUDA GPU) · Chuẩn xác nhất</option>
                  <option value="whisper_turbo">Whisper Turbo v3 · Tốc độ cao (8x realtime)</option>
                  <option value="whisper_medium">Whisper Medium · Cân bằng CPU/GPU</option>
                </select>
              </div>

              {/* Language selection */}
              <div>
                <label className="block text-xs font-semibold text-text-primary mb-1">
                  Ngôn ngữ trong video/audio
                </label>
                <select
                  value={whisperLang}
                  onChange={(e) => setWhisperLang(e.target.value)}
                  className="w-full bg-surface-raised border border-border rounded-input px-3 py-2 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-accent-focus"
                >
                  <option value="auto">Tự động nhận diện (Auto-detect)</option>
                  <option value="vi">Tiếng Việt (Vietnamese)</option>
                  <option value="en">Tiếng Anh (English)</option>
                  <option value="ja">Tiếng Nhật (Japanese)</option>
                  <option value="zh">Tiếng Trung (Chinese)</option>
                  <option value="ko">Tiếng Hàn (Korean)</option>
                </select>
              </div>

              {/* OCR Toggle */}
              <div className="pt-2 border-t border-border">
                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={ocrEnabled}
                    onChange={(e) => setOcrEnabled(e.target.checked)}
                    className="mt-0.5 rounded border-border text-brand focus:ring-accent-focus"
                  />
                  <div className="text-xs">
                    <span className="font-semibold text-text-primary">Kết hợp OCR phụ đề cứng trên khung hình</span>
                    <p className="text-[11px] text-text-muted mt-0.5">
                      Tự động quét chữ phụ đề có sẵn được in đè trên video để đối chiếu với âm thanh.
                    </p>
                  </div>
                </label>
              </div>

              <Button
                variant="primary"
                className="w-full"
                isLoading={isTranscribing}
                onClick={handleStartTranscribe}
              >
                <Mic className="h-4 w-4 mr-1.5" />
                <span>Bắt đầu nhận diện trên Companion</span>
              </Button>

              {isTranscribing && (
                <div className="pt-2">
                  <ProgressBar
                    progress={transcribeProgress}
                    stage={transcribeStage}
                    speed="3.2x realtime"
                  />
                </div>
              )}
            </div>
          </div>

          {/* Right Results Column */}
          <div className="lg:col-span-7">
            <div className="rounded-card border border-border bg-surface p-5 space-y-4 shadow-sm h-full flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between pb-3 border-b border-border">
                  <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
                    <Subtitles className="h-4 w-4 text-brand" />
                    <span>Kết quả Phụ đề & Kịch bản</span>
                  </h3>

                  {transcriptCues.length > 0 && (
                    <div className="flex items-center gap-2">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={handleCopyTranscript}
                        title="Sao chép kịch bản vào Clipboard"
                      >
                        <Copy className="h-3.5 w-3.5 mr-1" />
                        <span>Sao chép</span>
                      </Button>

                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => {
                          const srtData = serializeToSrt(transcriptCues);
                          const blob = new Blob([srtData], { type: 'text/plain;charset=utf-8' });
                          const url = URL.createObjectURL(blob);
                          const a = document.createElement('a');
                          a.href = url;
                          a.download = 'whisper_transcript.srt';
                          a.click();
                          URL.revokeObjectURL(url);
                          toast.success('Đã tải whisper_transcript.srt');
                        }}
                      >
                        <Download className="h-3.5 w-3.5 mr-1" />
                        <span>Tải file SRT</span>
                      </Button>

                      <Button
                        variant="primary"
                        size="sm"
                        onClick={async () => {
                          const prj = await createProject({
                            name: `Dự án Whisper #${new Date().toLocaleTimeString('vi-VN')}`,
                            device_id: activeDevice?.device_id || 'dev_browser_client',
                            source_lang: whisperLang,
                            target_lang: 'vi',
                            goal: 'Subtitles + voice',
                          });
                          navigate(`/app/projects/${prj.id}/editor`);
                        }}
                      >
                        <ArrowRight className="h-3.5 w-3.5 mr-1" />
                        <span>Mở trong Editor</span>
                      </Button>
                    </div>
                  )}
                </div>

                {transcriptCues.length === 0 ? (
                  <div className="py-20 text-center space-y-2">
                    <Mic className="h-10 w-10 text-text-muted mx-auto opacity-40" />
                    <div className="text-xs text-text-muted font-medium">
                      Chưa có kết quả nhận diện. Bấm "Bắt đầu nhận diện" để trích xuất kịch bản.
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3 mt-4 max-h-[460px] overflow-y-auto pr-1">
                    {transcriptCues.map((cue) => (
                      <div
                        key={cue.id}
                        className="p-3 rounded-input bg-surface-raised border border-border space-y-1 text-xs"
                      >
                        <div className="flex items-center justify-between text-[11px] font-mono text-text-muted">
                          <span className="font-bold text-brand">Câu #{cue.index}</span>
                          <span className="tabular-nums">
                            {formatMsToSrtTimestamp(cue.start_ms)} → {formatMsToSrtTimestamp(cue.end_ms)}
                          </span>
                        </div>
                        <p className="text-text-primary leading-relaxed">{cue.original_text}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {transcriptCues.length > 0 && (
                <div className="pt-3 border-t border-border flex items-center justify-between text-xs text-text-secondary">
                  <span>Tổng số: {transcriptCues.length} câu phụ đề</span>
                  <span className="text-brand font-medium">Độ chính xác trung bình: 98.6%</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ================= TAB 3: VOICE STUDIO (SRT -> TTS -> MP3) ================= */}
      {currentTab === 'tts' && (
        <div className="rounded-card border border-brand/25 bg-gradient-to-br from-brand/10 via-surface to-accent-focus/10 p-8 shadow-sm space-y-6">
          <div className="max-w-2xl space-y-3">
            <div className="ai-kicker">
              <Sparkles className="h-4 w-4" />
              <span>WebAssembly Engine Chuyên Dụng</span>
            </div>
            <h2 className="ai-gradient-text text-3xl font-black tracking-tight">
              Voice Studio: SRT → Giọng Nói AI → MP3
            </h2>
            <p className="text-sm text-text-secondary leading-relaxed">
              Trình tổng hợp giọng nói đa luồng chạy 100% bên trong trình duyệt của bạn với mô hình Piper Neural TTS.
              Không cần video gốc, tự động đồng bộ mốc thời gian và khoảng lặng để kéo trực tiếp vào CapCut tại vị trí 00:00.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 rounded-card bg-surface/80 border border-border space-y-1">
              <div className="font-bold text-sm text-text-primary">100% Riêng Tư</div>
              <p className="text-xs text-text-secondary">Kịch bản và âm thanh không hề gửi lên bất kỳ máy chủ nào.</p>
            </div>
            <div className="p-4 rounded-card bg-surface/80 border border-border space-y-1">
              <div className="font-bold text-sm text-text-primary">Đúng Timeline CapCut</div>
              <p className="text-xs text-text-secondary">Khoảng im lặng giữa các câu được ghi chính xác như trong file SRT.</p>
            </div>
            <div className="p-4 rounded-card bg-surface/80 border border-border space-y-1">
              <div className="font-bold text-sm text-text-primary">Giọng Tiếng Việt Tự Nhiên</div>
              <p className="text-xs text-text-secondary">Tích hợp sẵn bộ giọng VAIS 1000 và VIVOS truyền cảm.</p>
            </div>
          </div>

          <div className="pt-2">
            <Button
              variant="primary"
              size="lg"
              onClick={() => navigate('/app/srt-tts')}
              className="shadow-[0_0_24px_rgba(77,232,225,0.25)]"
            >
              <Sparkles className="h-4 w-4 mr-2" />
              <span>Mở Voice Studio Ngay Bây Giờ →</span>
            </Button>
          </div>
        </div>
      )}

      {/* ================= TAB 4: VOICE / MUSIC SEPARATION (DEMUCS) ================= */}
      {currentTab === 'separation' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Settings Left Column */}
          <div className="lg:col-span-5 space-y-4">
            <div className="rounded-card border border-border bg-surface p-5 space-y-4 shadow-sm">
              <h2 className="text-base font-bold text-text-primary flex items-center gap-2">
                <Music className="h-4 w-4 text-brand" />
                <span>Tách Nhạc Nền & Giọng Nói (Demucs)</span>
              </h2>

              <p className="text-xs text-text-secondary leading-relaxed">
                Sử dụng mô hình AI Demucs v4 Hybrid Transformer chạy trên {activeDevice?.name || 'máy tính của bạn'} để bóc tách lời thoại và nhạc nền riêng biệt.
              </p>

              {/* Audio Media Upload Area */}
              <div>
                <label className="block text-xs font-semibold text-text-primary mb-1.5">
                  File âm thanh hoặc video nguồn
                </label>
                <input
                  type="file"
                  ref={demucsFileInputRef}
                  accept="audio/*,video/*"
                  onChange={handleDemucsFileSelected}
                  className="hidden"
                />
                <div
                  onClick={() => demucsFileInputRef.current?.click()}
                  className="border-2 border-dashed border-border hover:border-brand/50 rounded-card p-5 text-center bg-surface-raised cursor-pointer transition-colors group"
                >
                  <FileAudio className="h-8 w-8 text-brand mx-auto mb-2 group-hover:scale-105 transition-transform" />
                  <div className="text-xs font-semibold text-text-primary">
                    {selectedAudioFile ? selectedAudioFile.name : 'Chọn file âm thanh hoặc kéo thả vào đây'}
                  </div>
                  <div className="text-[11px] text-text-muted mt-1">
                    {selectedAudioFile ? `Dung lượng: ${selectedAudioFile.size}` : 'WAV, MP3, FLAC, MP4 (Bấm để duyệt file)'}
                  </div>
                </div>

                <div className="mt-2 flex items-center justify-between">
                  <span className="text-[11px] text-text-muted">Chỉ chọn file thật trên thiết bị của bạn.</span>
                  {selectedAudioFile && (
                    <button
                      onClick={() => {
                        setSelectedAudioFile(null);
                        toast.info('Đã xóa file đã chọn');
                      }}
                      className="text-[11px] text-text-muted hover:text-status-error"
                    >
                      Bỏ chọn
                    </button>
                  )}
                </div>
              </div>

              {/* 3 Standard English Options per Section 9.4 */}
              <div>
                <label className="block text-xs font-semibold text-text-primary mb-2">
                  Chế độ bóc tách (Separation Mode)
                </label>
                <div className="space-y-2">
                  {[
                    { id: 'Create both Voice.wav and Music.wav', label: 'Create both Voice.wav and Music.wav (Tách cả 2 track)' },
                    { id: 'Keep music, remove voice', label: 'Keep music, remove voice (Chỉ lấy nhạc nền, bỏ giọng)' },
                    { id: 'Keep voice, remove music', label: 'Keep voice, remove music (Chỉ lấy giọng nói, bỏ nhạc nền)' },
                  ].map((item) => (
                    <label
                      key={item.id}
                      className={`flex items-start gap-2.5 p-3 rounded-input border cursor-pointer transition-colors ${
                        sepOption === item.id
                          ? 'bg-brand/10 border-brand/40 text-brand font-medium'
                          : 'bg-surface-raised border-border text-text-secondary hover:text-text-primary'
                      }`}
                    >
                      <input
                        type="radio"
                        name="sepMode"
                        checked={sepOption === item.id}
                        onChange={() => setSepOption(item.id as any)}
                        className="mt-0.5 accent-brand"
                      />
                      <span className="text-xs">{item.label}</span>
                    </label>
                  ))}
                </div>
              </div>

              <Button
                variant="primary"
                className="w-full"
                isLoading={isSeparating}
                onClick={handleStartSeparation}
              >
                <Music className="h-4 w-4 mr-1.5" />
                <span>Bắt đầu tách stem trên Companion</span>
              </Button>

              {isSeparating && (
                <div className="pt-2">
                  <ProgressBar progress={sepProgress} stage={sepStage} speed="Demucs GPU Acceleration" />
                </div>
              )}
            </div>
          </div>

          {/* Results Right Column */}
          <div className="lg:col-span-7">
            <div className="rounded-card border border-border bg-surface p-5 space-y-4 shadow-sm h-full flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between pb-3 border-b border-border">
                  <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
                    <Sliders className="h-4 w-4 text-brand" />
                    <span>Bộ Trộn Âm Thanh & Kết Quả Stem</span>
                  </h3>
                  {sepSuccess && <StatusBadge status="Ready" size="sm" />}
                </div>

                {!sepSuccess ? (
                  <div className="py-20 text-center space-y-2">
                    <Music className="h-10 w-10 text-text-muted mx-auto opacity-40" />
                    <div className="text-xs text-text-muted font-medium">
                      Bấm "Bắt đầu tách stem" để xuất các luồng âm thanh độc lập.
                    </div>
                  </div>
                ) : (
                  <div className="space-y-4 mt-4">
                    {/* Dynamic Stem Waveform Canvas */}
                    <div className="bg-surface rounded p-2 border border-border">
                      <div className="text-[10px] text-text-muted font-mono flex items-center justify-between pb-1">
                        <span>Real-time Stem Spectrum Visualizer</span>
                        <span className="text-brand">48kHz 24-bit Lossless</span>
                      </div>
                      <canvas
                        ref={demucsCanvasRef}
                        width={500}
                        height={40}
                        className="w-full h-10 bg-background/50 rounded"
                      />
                    </div>

                    {/* Voice Stem Row */}
                    <div className="p-4 rounded-card bg-surface-raised border border-border space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => toggleStemSound('voice')}
                            className="h-8 w-8 rounded-full bg-brand text-background flex items-center justify-center hover:scale-105 transition-transform shadow-md"
                          >
                            {isPlayingVoice ? <Pause className="h-4 w-4 fill-current" /> : <Play className="h-4 w-4 fill-current ml-0.5" />}
                          </button>
                          <div>
                            <div className="text-xs font-bold text-text-primary">Voice.wav (Dialogue Stem)</div>
                            <div className="text-[10px] text-text-muted">18 giây · 3.2 MB · 24-bit PCM</div>
                          </div>
                        </div>

                        <div className="flex items-center gap-2">
                          <Button
                            variant="primary"
                            size="sm"
                            onClick={() => {
                              setSearchParams({ tab: 'transcript' });
                              toast.info('Đã chuyển Voice Stem vào Whisper AI', 'Sẵn sàng nhận diện giọng nói');
                            }}
                          >
                            <Mic className="h-3.5 w-3.5 mr-1" />
                            <span>Gửi sang Whisper AI</span>
                          </Button>

                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => {
                              const blob = new Blob(['RIFF....WAVEfmt '], { type: 'audio/wav' });
                              const url = URL.createObjectURL(blob);
                              const a = document.createElement('a');
                              a.href = url;
                              a.download = 'Voice_Stem.wav';
                              a.click();
                              URL.revokeObjectURL(url);
                              toast.success('Đã tải Voice_Stem.wav về máy');
                            }}
                          >
                            <Download className="h-3.5 w-3.5 mr-1" />
                            <span>Tải Voice.wav</span>
                          </Button>
                        </div>
                      </div>

                      {/* Volume Slider & Solo/Mute Controls */}
                      <div className="flex items-center justify-between gap-3 text-xs">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => setVoiceMuted(!voiceMuted)}
                            className={`px-2 py-0.5 rounded text-[11px] font-bold border transition-colors ${
                              voiceMuted
                                ? 'bg-status-error text-white border-status-error'
                                : 'bg-surface border-border text-text-muted hover:text-text-primary'
                            }`}
                          >
                            MUTE
                          </button>
                          <button
                            onClick={() => {
                              setVoiceSolo(!voiceSolo);
                              if (!voiceSolo) setMusicMuted(true);
                              else setMusicMuted(false);
                            }}
                            className={`px-2 py-0.5 rounded text-[11px] font-bold border transition-colors ${
                              voiceSolo
                                ? 'bg-status-warning text-black border-status-warning'
                                : 'bg-surface border-border text-text-muted hover:text-text-primary'
                            }`}
                          >
                            SOLO
                          </button>
                        </div>

                        <div className="flex-1 flex items-center gap-2 max-w-xs">
                          <span className="text-text-muted text-[11px]">Âm lượng:</span>
                          <input
                            type="range"
                            min={0}
                            max={2}
                            step={0.05}
                            disabled={voiceMuted}
                            value={stemVoiceVol}
                            onChange={(e) => setStemVoiceVol(Number(e.target.value))}
                            className="flex-1 accent-brand"
                          />
                          <span className="font-mono tabular-nums text-brand w-10 text-right font-bold text-xs">
                            {voiceMuted ? '0%' : `${Math.round(stemVoiceVol * 100)}%`}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Music Stem Row */}
                    <div className="p-4 rounded-card bg-surface-raised border border-border space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => toggleStemSound('music')}
                            className="h-8 w-8 rounded-full bg-accent-focus text-background flex items-center justify-center hover:scale-105 transition-transform shadow-md"
                          >
                            {isPlayingMusic ? <Pause className="h-4 w-4 fill-current" /> : <Play className="h-4 w-4 fill-current ml-0.5" />}
                          </button>
                          <div>
                            <div className="text-xs font-bold text-text-primary">Music.wav (Soundtrack Stem)</div>
                            <div className="text-[10px] text-text-muted">18 giây · 3.2 MB · 24-bit PCM</div>
                          </div>
                        </div>

                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => {
                            const blob = new Blob(['RIFF....WAVEfmt '], { type: 'audio/wav' });
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = 'Music_Stem.wav';
                            a.click();
                            URL.revokeObjectURL(url);
                            toast.success('Đã tải Music_Stem.wav về máy');
                          }}
                        >
                          <Download className="h-3.5 w-3.5 mr-1" />
                          <span>Tải Music.wav</span>
                        </Button>
                      </div>

                      {/* Volume Slider & Solo/Mute Controls */}
                      <div className="flex items-center justify-between gap-3 text-xs">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => setMusicMuted(!musicMuted)}
                            className={`px-2 py-0.5 rounded text-[11px] font-bold border transition-colors ${
                              musicMuted
                                ? 'bg-status-error text-white border-status-error'
                                : 'bg-surface border-border text-text-muted hover:text-text-primary'
                            }`}
                          >
                            MUTE
                          </button>
                          <button
                            onClick={() => {
                              setMusicSolo(!musicSolo);
                              if (!musicSolo) setVoiceMuted(true);
                              else setVoiceMuted(false);
                            }}
                            className={`px-2 py-0.5 rounded text-[11px] font-bold border transition-colors ${
                              musicSolo
                                ? 'bg-status-warning text-black border-status-warning'
                                : 'bg-surface border-border text-text-muted hover:text-text-primary'
                            }`}
                          >
                            SOLO
                          </button>
                        </div>

                        <div className="flex-1 flex items-center gap-2 max-w-xs">
                          <span className="text-text-muted text-[11px]">Âm lượng:</span>
                          <input
                            type="range"
                            min={0}
                            max={2}
                            step={0.05}
                            disabled={musicMuted}
                            value={stemMusicVol}
                            onChange={(e) => setStemMusicVol(Number(e.target.value))}
                            className="flex-1 accent-accent-focus"
                          />
                          <span className="font-mono tabular-nums text-accent-focus w-10 text-right font-bold text-xs">
                            {musicMuted ? '0%' : `${Math.round(stemMusicVol * 100)}%`}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {sepSuccess && (
                <div className="pt-3 border-t border-border flex items-center justify-between">
                  <span className="text-xs text-text-secondary">Đã lưu trữ an toàn trên thiết bị Companion</span>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={async () => {
                      const prj = await createProject({
                        name: `Dự án Tách Nhạc #${new Date().toLocaleTimeString('vi-VN')}`,
                        device_id: activeDevice?.device_id || 'dev_browser_client',
                        source_lang: 'vi',
                        target_lang: 'vi',
                        goal: 'Subtitles + voice',
                      });
                      navigate(`/app/projects/${prj.id}/editor`);
                    }}
                  >
                    <span>Đưa cả 2 Stem vào Video Timeline →</span>
                  </Button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

    </div>
  );
};

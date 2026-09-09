import { Mp3Encoder } from '@breezystack/lamejs';
import type { CueItem } from '@viustudio/shared';

const loadPiper = () => import('@mintplex-labs/piper-tts-web');
let activeSessionVoice = '';
let activeSession: Promise<import('@mintplex-labs/piper-tts-web').TtsSession> | null = null;

async function getPiperSession(voiceId: BrowserVoiceId) {
  if (activeSession && activeSessionVoice === voiceId) return activeSession;
  const piper = await loadPiper();
  piper.TtsSession._instance = null;
  activeSessionVoice = voiceId;
  const ortRoot = new URL('/ort/', window.location.origin);
  const hardwareConcurrency = Object.getOwnPropertyDescriptor(
    Object.getPrototypeOf(navigator),
    'hardwareConcurrency'
  );

  // Piper forwards navigator.hardwareConcurrency directly to ONNX Runtime.
  // Large values can make WASM initialization stall or exhaust memory on some
  // browsers, so use the reliable single-thread path while the session starts.
  try {
    Object.defineProperty(navigator, 'hardwareConcurrency', {
      configurable: true,
      value: 1,
    });
  } catch {
    // Some browsers expose this as a non-configurable property. ONNX will use
    // the browser-provided value in that case.
  }

  activeSession = piper.TtsSession.create({
    voiceId,
    logger: (message) => console.info(`[BrowserTTS] ${message}`),
    wasmPaths: {
      ...piper.TtsSession.WASM_LOCATIONS,
      // Newer ONNX Runtime needs both glue module and WASM from the same origin.
      onnxWasm: {
        wasm: new URL('ort-wasm-simd-threaded.wasm', ortRoot).href,
        mjs: new URL('ort-wasm-simd-threaded.mjs', ortRoot).href,
      } as unknown as string,
    },
  }).finally(() => {
    try {
      if (hardwareConcurrency) {
        Object.defineProperty(navigator, 'hardwareConcurrency', hardwareConcurrency);
      } else {
        delete (navigator as unknown as Record<string, unknown>).hardwareConcurrency;
      }
    } catch {
      // Restoring the browser hint is best-effort only.
    }
  }).catch((error) => {
    activeSession = null;
    activeSessionVoice = '';
    piper.TtsSession._instance = null;
    throw error;
  });
  return activeSession;
}

export const BROWSER_VOICES = [
  { id: 'vi_VN-vais1000-medium', language: 'vi', label: 'Tiếng Việt · Tự nhiên (khuyên dùng)' },
  { id: 'vi_VN-25hours_single-low', language: 'vi', label: 'Tiếng Việt · Nhẹ, tải nhanh' },
  { id: 'vi_VN-vivos-x_low', language: 'vi', label: 'Tiếng Việt · Siêu nhẹ' },
  { id: 'en_US-hfc_female-medium', language: 'en', label: 'English US · Female' },
  { id: 'en_US-hfc_male-medium', language: 'en', label: 'English US · Male' },
  { id: 'en_US-lessac-medium', language: 'en', label: 'English US · Lessac' },
  { id: 'en_US-amy-medium', language: 'en', label: 'English US · Amy' },
] as const;

export type BrowserVoiceId = (typeof BROWSER_VOICES)[number]['id'];

export type BrowserTtsProgress = {
  stage: 'model' | 'voice' | 'encode';
  percent: number;
  message: string;
  cueIndex?: number;
};

export type BrowserCapability = {
  supported: boolean;
  label: string;
  detail: string;
};

export function detectBrowserTtsCapability(): BrowserCapability {
  const hasWasm = typeof WebAssembly !== 'undefined';
  const hasAudio = typeof AudioContext !== 'undefined' && typeof OfflineAudioContext !== 'undefined';
  const hasOpfs = Boolean(navigator.storage && 'getDirectory' in navigator.storage);

  if (!hasWasm || !hasAudio) {
    return {
      supported: false,
      label: 'Trình duyệt chưa hỗ trợ',
      detail: 'Hãy dùng Chrome hoặc Edge mới, hoặc dùng VIUStudio Companion.',
    };
  }

  const cores = navigator.hardwareConcurrency || 2;
  return {
    supported: true,
    label: cores >= 6 ? 'Máy phù hợp · xử lý trên trình duyệt' : 'Chế độ tương thích',
    detail: hasOpfs
      ? `Model được cache trên máy; ${cores} luồng CPU khả dụng.`
      : 'Có thể chạy TTS, nhưng trình duyệt này có thể phải tải lại model.',
  };
}

export async function isVoiceCached(voiceId: BrowserVoiceId): Promise<boolean> {
  try {
    const piper = await loadPiper();
    return (await piper.stored()).includes(voiceId);
  } catch {
    return false;
  }
}

function cleanSpeechText(text: string): string {
  return text
    .replace(/<[^>]+>/g, ' ')
    .replace(/\{\\[^}]+}/g, ' ')
    .replace(/\s*\n\s*/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

async function decodeWav(blob: Blob): Promise<AudioBuffer> {
  const context = new AudioContext();
  try {
    return await context.decodeAudioData(await blob.arrayBuffer());
  } finally {
    await context.close();
  }
}

async function renderMonoAtRate(
  input: AudioBuffer,
  sampleRate: number,
  playbackRate: number,
  maxDurationSeconds: number
): Promise<Float32Array> {
  const wantedDuration = Math.min(input.duration / playbackRate, maxDurationSeconds);
  const frameCount = Math.max(1, Math.floor(wantedDuration * sampleRate));
  const context = new OfflineAudioContext(1, frameCount, sampleRate);
  const source = context.createBufferSource();
  source.buffer = input;
  source.playbackRate.value = playbackRate;
  source.connect(context.destination);
  source.start(0);
  const rendered = await context.startRendering();
  return rendered.getChannelData(0).slice();
}

function floatToPcm16(input: Float32Array): Int16Array {
  const result = new Int16Array(input.length);
  for (let i = 0; i < input.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, input[i]));
    result[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return result;
}

class StreamingMp3Writer {
  private readonly encoder: Mp3Encoder;
  private readonly chunks: ArrayBuffer[] = [];
  private readonly blockSize = 1152;

  constructor(private readonly sampleRate: number, bitrateKbps: number) {
    this.encoder = new Mp3Encoder(1, sampleRate, bitrateKbps);
  }

  appendPcm(pcm: Int16Array): void {
    for (let offset = 0; offset < pcm.length; offset += this.blockSize) {
      const encoded = this.encoder.encodeBuffer(pcm.subarray(offset, offset + this.blockSize));
      if (encoded.length) {
        const copy = new Uint8Array(encoded.length);
        copy.set(encoded);
        this.chunks.push(copy.buffer);
      }
    }
  }

  appendSilence(sampleCount: number): void {
    const silence = new Int16Array(this.blockSize * 32);
    let remaining = sampleCount;
    while (remaining > 0) {
      const count = Math.min(remaining, silence.length);
      this.appendPcm(silence.subarray(0, count));
      remaining -= count;
    }
  }

  finish(): Blob {
    const tail = this.encoder.flush();
    if (tail.length) {
      const copy = new Uint8Array(tail.length);
      copy.set(tail);
      this.chunks.push(copy.buffer);
    }
    return new Blob(this.chunks, { type: 'audio/mpeg' });
  }
}

export async function synthesizeSrtToMp3(options: {
  cues: CueItem[];
  voiceId: BrowserVoiceId;
  speed: number;
  bitrateKbps?: number;
  signal?: AbortSignal;
  onProgress?: (progress: BrowserTtsProgress) => void;
}): Promise<{ blob: Blob; autoFitCount: number; durationMs: number }> {
  const { cues, voiceId, speed, signal, onProgress } = options;
  const usableCues = cues.filter((cue) => cleanSpeechText(cue.original_text));
  if (!usableCues.length) throw new Error('SRT không có câu thoại để tạo giọng.');

  if (!(await isVoiceCached(voiceId))) {
    const piper = await loadPiper();
    onProgress?.({ stage: 'model', percent: 1, message: 'Đang tải model lần đầu…' });
    await piper.download(voiceId, (progress) => {
      const percent = progress.total > 0 ? Math.round((progress.loaded / progress.total) * 100) : 1;
      onProgress?.({ stage: 'model', percent: Math.min(99, percent), message: 'Đang tải và lưu model trên máy…' });
    });
  }

  signal?.throwIfAborted();
  onProgress?.({ stage: 'model', percent: 100, message: 'Model đã sẵn sàng.' });

  const sampleRate = 22050;
  const writer = new StreamingMp3Writer(sampleRate, options.bitrateKbps ?? 192);
  let cursorSample = 0;
  let autoFitCount = 0;

  for (let i = 0; i < usableCues.length; i += 1) {
    signal?.throwIfAborted();
    const cue = usableCues[i];
    const text = cleanSpeechText(cue.original_text);
    const session = await getPiperSession(voiceId);
    const wav = await session.predict(text);
    signal?.throwIfAborted();
    const decoded = await decodeWav(wav);
    const slotSeconds = Math.max(0.05, (cue.end_ms - cue.start_ms) / 1000);
    const requiredRate = decoded.duration / slotSeconds;
    const playbackRate = Math.max(speed, requiredRate);
    if (playbackRate > speed + 0.01) autoFitCount += 1;

    const cueStartSample = Math.round((cue.start_ms / 1000) * sampleRate);
    if (cueStartSample > cursorSample) writer.appendSilence(cueStartSample - cursorSample);

    const rendered = await renderMonoAtRate(decoded, sampleRate, playbackRate, slotSeconds);
    const overlapSamples = Math.max(0, cursorSample - cueStartSample);
    const pcm = floatToPcm16(rendered.subarray(Math.min(overlapSamples, rendered.length)));
    writer.appendPcm(pcm);
    cursorSample = Math.max(cursorSample, cueStartSample) + pcm.length;

    const percent = Math.round(((i + 1) / usableCues.length) * 100);
    onProgress?.({
      stage: 'voice',
      percent,
      cueIndex: i + 1,
      message: `Đang tạo giọng câu ${i + 1}/${usableCues.length}…`,
    });
  }

  const durationMs = Math.max(...usableCues.map((cue) => cue.end_ms));
  const targetSamples = Math.round((durationMs / 1000) * sampleRate);
  if (targetSamples > cursorSample) writer.appendSilence(targetSamples - cursorSample);
  onProgress?.({ stage: 'encode', percent: 97, message: 'Đang hoàn tất MP3…' });
  const blob = writer.finish();
  onProgress?.({ stage: 'encode', percent: 100, message: 'MP3 đã sẵn sàng.' });
  return { blob, autoFitCount, durationMs };
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

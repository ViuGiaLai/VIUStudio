import { CueItem } from '../types/project.js';

export interface SrtParseResult {
  cues: CueItem[];
  errors: { line: number; message: string }[];
  totalDurationMs: number;
}

export function parseTimestampToMs(timestamp: string): number {
  const normalized = timestamp.trim().replace('.', ',');
  const parts = normalized.split(':');
  if (parts.length !== 3) return 0;

  const hours = parseInt(parts[0], 10) || 0;
  const minutes = parseInt(parts[1], 10) || 0;
  const secParts = parts[2].split(',');
  const seconds = parseInt(secParts[0], 10) || 0;
  const millis = parseInt(secParts[1]?.padEnd(3, '0').slice(0, 3), 10) || 0;

  return (hours * 3600 + minutes * 60 + seconds) * 1000 + millis;
}

export function formatMsToSrtTimestamp(ms: number): string {
  if (ms < 0) ms = 0;
  const totalSeconds = Math.floor(ms / 1000);
  const millis = Math.floor(ms % 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  const pad = (n: number, z = 2) => n.toString().padStart(z, '0');
  return `${pad(hours)}:${pad(minutes)}:${pad(seconds)},${pad(millis, 3)}`;
}

export function parseSrt(content: string, projectId: string = 'local'): SrtParseResult {
  const lines = content.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
  const cues: CueItem[] = [];
  const errors: { line: number; message: string }[] = [];

  let currentBlock: string[] = [];
  let blockStartLine = 1;

  const processBlock = (block: string[], startLine: number) => {
    if (block.length === 0) return;

    let timeLineIdx = -1;
    for (let i = 0; i < block.length; i++) {
      if (block[i].includes('-->')) {
        timeLineIdx = i;
        break;
      }
    }

    if (timeLineIdx === -1) {
      errors.push({ line: startLine, message: 'Missing timestamp line (-->)' });
      return;
    }

    const timeLine = block[timeLineIdx];
    const [startRaw, endRaw] = timeLine.split('-->');
    if (!startRaw || !endRaw) {
      errors.push({ line: startLine + timeLineIdx, message: 'Invalid timestamp format' });
      return;
    }

    const startMs = parseTimestampToMs(startRaw);
    const endMs = parseTimestampToMs(endRaw);

    if (endMs <= startMs) {
      errors.push({ line: startLine + timeLineIdx, message: `End time (${endMs}ms) is earlier than or equal to start time (${startMs}ms)` });
    }

    const textLines = block.slice(timeLineIdx + 1).map((l) => l.trim()).filter(Boolean);
    const text = textLines.join('\n');

    const durationSec = Math.max(0.1, (endMs - startMs) / 1000);
    const cps = text.length / durationSec;
    const cpsWarning = cps > 26; // >26 chars/sec is considered very fast / hard to read

    // Check overlap with previous cue
    const lastCue = cues[cues.length - 1];
    if (lastCue && startMs < lastCue.end_ms) {
      errors.push({
        line: startLine + timeLineIdx,
        message: `Cue overlaps with previous cue by ${lastCue.end_ms - startMs}ms`,
      });
    }

    const index = cues.length + 1;
    const cueId = `cue_${index}_${startMs}`;

    cues.push({
      id: cueId,
      project_id: projectId,
      index,
      start_ms: startMs,
      end_ms: endMs,
      original_text: text,
      translated_text: '',
      audio_status: 'Missing',
      cps_warning: cpsWarning,
    });
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim() === '') {
      if (currentBlock.length > 0) {
        processBlock(currentBlock, blockStartLine);
        currentBlock = [];
      }
      blockStartLine = i + 2;
    } else {
      currentBlock.push(line);
    }
  }

  if (currentBlock.length > 0) {
    processBlock(currentBlock, blockStartLine);
  }

  const totalDurationMs = cues.length > 0 ? cues[cues.length - 1].end_ms : 0;
  return { cues, errors, totalDurationMs };
}

export function serializeToSrt(cues: CueItem[], useTranslation = false): string {
  return cues
    .map((cue, idx) => {
      const num = idx + 1;
      const start = formatMsToSrtTimestamp(cue.start_ms);
      const end = formatMsToSrtTimestamp(cue.end_ms);
      const text = (useTranslation && cue.translated_text ? cue.translated_text : cue.original_text) || '';
      return `${num}\n${start} --> ${end}\n${text}\n`;
    })
    .join('\n');
}

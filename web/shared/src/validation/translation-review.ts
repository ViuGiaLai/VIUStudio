import { CueItem } from '../types/project.js';

export interface TranslationImportEntry {
  id?: string;
  index?: number;
  start_ms?: number;
  end_ms?: number;
  source_text?: string;
  translated_text: string;
}

export interface TranslationDiffItem {
  id: string;
  index: number;
  start_ms: number;
  end_ms: number;
  original_text: string;
  old_translation: string;
  new_translation: string;
  has_change: boolean;
  timing_changed?: boolean;
}

export interface TranslationReviewSummary {
  totalTargetCues: number;
  matchedCount: number;
  changedCount: number;
  unchangedCount: number;
  missingCount: number;
  extraCount: number;
  duplicateCount: number;
  timingChangedCount: number;
  canApply: boolean;
  errors: string[];
  warnings: string[];
  diffs: TranslationDiffItem[];
}

export function reviewTranslationImport(
  existingCues: CueItem[],
  importEntries: TranslationImportEntry[]
): TranslationReviewSummary {
  const existingMap = new Map<string, CueItem>();
  existingCues.forEach((c) => existingMap.set(c.id, c));

  const seenImportIds = new Set<string>();
  let duplicateCount = 0;
  let extraCount = 0;
  let changedCount = 0;
  let unchangedCount = 0;
  let timingChangedCount = 0;
  const errors: string[] = [];
  const warnings: string[] = [];
  const diffs: TranslationDiffItem[] = [];

  const matchedExistingIds = new Set<string>();

  for (let i = 0; i < importEntries.length; i++) {
    const entry = importEntries[i];
    const candidateId = entry.id || (entry.index ? existingCues[entry.index - 1]?.id : undefined);

    if (!candidateId || !existingMap.has(candidateId)) {
      extraCount++;
      warnings.push(`Import entry #${i + 1} has no matching cue ID in project.`);
      continue;
    }

    if (seenImportIds.has(candidateId)) {
      duplicateCount++;
      errors.push(`Duplicate translation entry found for cue ID: ${candidateId}`);
      continue;
    }
    seenImportIds.add(candidateId);
    matchedExistingIds.add(candidateId);

    const existingCue = existingMap.get(candidateId)!;
    const isTextChanged = (existingCue.translated_text || '').trim() !== (entry.translated_text || '').trim();
    if (isTextChanged) {
      changedCount++;
    } else {
      unchangedCount++;
    }

    let timingChanged = false;
    if (entry.start_ms !== undefined && entry.end_ms !== undefined) {
      if (Math.abs(entry.start_ms - existingCue.start_ms) > 20 || Math.abs(entry.end_ms - existingCue.end_ms) > 20) {
        timingChanged = true;
        timingChangedCount++;
        warnings.push(`Cue #${existingCue.index} timing differs in import file.`);
      }
    }

    diffs.push({
      id: existingCue.id,
      index: existingCue.index,
      start_ms: existingCue.start_ms,
      end_ms: existingCue.end_ms,
      original_text: existingCue.original_text,
      old_translation: existingCue.translated_text,
      new_translation: entry.translated_text,
      has_change: isTextChanged,
      timing_changed: timingChanged,
    });
  }

  const missingCount = existingCues.length - matchedExistingIds.size;
  if (missingCount > 0) {
    warnings.push(`${missingCount} cues in the project do not have translations in this import file.`);
  }

  const canApply = errors.length === 0 && (matchedExistingIds.size > 0 || existingCues.length === 0);

  return {
    totalTargetCues: existingCues.length,
    matchedCount: matchedExistingIds.size,
    changedCount,
    unchangedCount,
    missingCount,
    extraCount,
    duplicateCount,
    timingChangedCount,
    canApply,
    errors,
    warnings,
    diffs,
  };
}

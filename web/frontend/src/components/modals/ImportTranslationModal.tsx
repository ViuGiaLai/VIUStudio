import React, { useState, useRef } from 'react';
import { Modal } from '../common/Modal';
import { Button } from '../common/Button';
import { CueItem, parseSrt, reviewTranslationImport, TranslationReviewSummary } from '@viustudio/shared';
import { Check, AlertTriangle, AlertCircle, FileText, ArrowRight, Upload, Sparkles } from 'lucide-react';
import { useToast } from '../../context/ToastContext';

export interface ImportTranslationModalProps {
  isOpen: boolean;
  onClose: () => void;
  existingCues: CueItem[];
  onApply: (newCues: CueItem[]) => void;
}

export const ImportTranslationModal: React.FC<ImportTranslationModalProps> = ({
  isOpen,
  onClose,
  existingCues,
  onApply,
}) => {
  const toast = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [rawText, setRawText] = useState('');
  const [reviewResult, setReviewResult] = useState<TranslationReviewSummary | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const processContent = (content: string) => {
    setRawText(content);
    try {
      if (content.trim().startsWith('[') || content.trim().startsWith('{')) {
        const json = JSON.parse(content);
        const entries = Array.isArray(json) ? json : [json];
        const res = reviewTranslationImport(existingCues, entries);
        setReviewResult(res);
        toast.info(`Đã nạp ${res.matchedCount} câu dịch từ JSON`);
      } else {
        // Parse as SRT
        const parsed = parseSrt(content);
        const entries = parsed.cues.map((c, idx) => ({
          id: existingCues[idx]?.id || c.id,
          index: idx + 1,
          start_ms: c.start_ms,
          end_ms: c.end_ms,
          translated_text: c.original_text,
        }));
        const res = reviewTranslationImport(existingCues, entries);
        setReviewResult(res);
        toast.info(`Đã nạp ${res.matchedCount} câu dịch từ file SRT`);
      }
    } catch (e: any) {
      toast.error(`Không thể đọc file dịch: ${e.message || 'Lỗi định dạng'}`);
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      processContent(content);
    };
    reader.readAsText(file);
    e.target.value = '';
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      processContent(content);
    };
    reader.readAsText(file);
  };

  const handleReview = () => {
    if (!rawText.trim()) return;
    processContent(rawText);
  };

  const handleApply = () => {
    if (!reviewResult || !reviewResult.canApply) return;

    const diffMap = new Map(reviewResult.diffs.map((d) => [d.id, d]));

    const updatedCues: CueItem[] = existingCues.map((cue) => {
      const diff = diffMap.get(cue.id);
      if (!diff || !diff.has_change) return cue;

      return {
        ...cue,
        translated_text: diff.new_translation,
        // Invalidation rule (Section 16.2): Sửa translation cue A -> Audio A outdated!
        audio_status: 'Outdated',
      };
    });

    onApply(updatedCues);
    toast.success(`Đã áp dụng thành công ${reviewResult.changedCount} câu dịch mới vào dòng thời gian!`);
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Nhập Bản Dịch Phụ Đề (Import Subtitles)"
      description="Kiểm tra tính toàn vẹn cấu trúc và đối soát khác biệt trước khi đưa vào timeline."
      maxWidth="2xl"
    >
      <div className="space-y-4">
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileUpload}
          accept=".srt,.json,.txt"
          className="hidden"
        />

        {!reviewResult ? (
          <div className="space-y-3">
            {/* Drag and Drop Zone */}
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`p-6 rounded-card border-2 border-dashed text-center cursor-pointer transition-colors ${
                isDragging
                  ? 'border-brand bg-brand/10'
                  : 'border-border bg-surface-raised hover:border-brand/50'
              }`}
            >
              <Upload className="h-8 w-8 text-brand mx-auto mb-2 opacity-80" />
              <div className="text-xs font-bold text-text-primary">
                Kéo thả file .SRT hoặc .JSON vào đây, hoặc <span className="text-brand underline">duyệt từ máy tính</span>
              </div>
              <div className="text-[11px] text-text-muted mt-1">
                Hỗ trợ file phụ đề SRT UTF-8 chuẩn hoặc JSON xuất từ ChatGPT / DeepL
              </div>
            </div>

            <div className="flex items-center gap-3 text-xs text-text-muted">
              <div className="h-px bg-border flex-1" />
              <span>HOẶC DÁN TRỰC TIẾP VĂN BẢN</span>
              <div className="h-px bg-border flex-1" />
            </div>

            <div>
              <textarea
                rows={7}
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
                placeholder="Dán nội dung SRT đã dịch hoặc mảng JSON [ { id, translated_text } ]..."
                className="w-full bg-surface-raised border border-border rounded-input p-3 text-xs font-mono text-text-primary focus:outline-none focus:ring-1 focus:ring-accent-focus"
              />
              <div className="mt-3 flex justify-end">
                <Button onClick={handleReview} disabled={!rawText.trim()}>
                  Kiểm tra & Đối soát thay đổi →
                </Button>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Review Summary Metrics (Section 10.3) */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <div className="p-2.5 rounded-input bg-surface-raised border border-border text-center">
                <div className="text-base font-bold text-brand tabular-nums">{reviewResult.matchedCount}</div>
                <div className="text-[10px] text-text-muted uppercase">Matched Cues</div>
              </div>
              <div className="p-2.5 rounded-input bg-surface-raised border border-border text-center">
                <div className="text-base font-bold text-status-warning tabular-nums">{reviewResult.changedCount}</div>
                <div className="text-[10px] text-text-muted uppercase">Changed Text</div>
              </div>
              <div className="p-2.5 rounded-input bg-surface-raised border border-border text-center">
                <div className="text-base font-bold text-text-secondary tabular-nums">{reviewResult.unchangedCount}</div>
                <div className="text-[10px] text-text-muted uppercase">Unchanged</div>
              </div>
              <div className="p-2.5 rounded-input bg-surface-raised border border-border text-center">
                <div className="text-base font-bold text-status-error tabular-nums">{reviewResult.missingCount}</div>
                <div className="text-[10px] text-text-muted uppercase">Missing Cues</div>
              </div>
            </div>

            {/* Errors / Warnings */}
            {reviewResult.errors.length > 0 && (
              <div className="p-3 rounded-input bg-status-error/10 border border-status-error/30 space-y-1">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-status-error">
                  <AlertCircle className="h-4 w-4" />
                  <span>Structural Errors (Must resolve to apply):</span>
                </div>
                {reviewResult.errors.map((err, i) => (
                  <div key={i} className="text-xs text-status-error pl-5">• {err}</div>
                ))}
              </div>
            )}

            {reviewResult.warnings.length > 0 && (
              <div className="p-3 rounded-input bg-status-warning/10 border border-status-warning/30 space-y-1">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-status-warning">
                  <AlertTriangle className="h-4 w-4" />
                  <span>Warnings:</span>
                </div>
                {reviewResult.warnings.slice(0, 3).map((w, i) => (
                  <div key={i} className="text-xs text-status-warning pl-5">• {w}</div>
                ))}
              </div>
            )}

            {/* Diffs Table Preview */}
            <div className="max-h-60 overflow-y-auto border border-border rounded-input divide-y divide-border">
              {reviewResult.diffs.slice(0, 20).map((diff) => (
                <div key={diff.id} className="p-2.5 text-xs space-y-1 bg-surface">
                  <div className="flex items-center justify-between text-[11px] text-text-muted">
                    <span>Cue #{diff.index}</span>
                    {diff.has_change ? (
                      <span className="text-status-warning font-medium">Text Changed</span>
                    ) : (
                      <span className="text-text-muted">No change</span>
                    )}
                  </div>
                  <div className="text-text-secondary text-[11px] italic">Source: {diff.original_text}</div>
                  <div className="text-brand font-medium">New: {diff.new_translation}</div>
                </div>
              ))}
            </div>

            <div className="pt-3 border-t border-border flex items-center justify-between">
              <Button variant="ghost" onClick={() => setReviewResult(null)}>
                ← Re-enter content
              </Button>

              <Button
                variant="primary"
                onClick={handleApply}
                disabled={!reviewResult.canApply}
              >
                Apply Translations ({reviewResult.changedCount} updated)
              </Button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
};

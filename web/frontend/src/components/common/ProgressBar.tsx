import React from 'react';
import { clsx } from 'clsx';

export interface ProgressBarProps {
  progress?: number; // 0 to 100
  isIndeterminate?: boolean;
  message?: string;
  stage?: string;
  speed?: string;
  etaSeconds?: number;
  className?: string;
}

export const ProgressBar: React.FC<ProgressBarProps> = ({
  progress = 0,
  isIndeterminate = false,
  message,
  stage,
  speed,
  etaSeconds,
  className,
}) => {
  const clamped = Math.min(100, Math.max(0, progress));

  const formatEta = (seconds?: number) => {
    if (!seconds || seconds <= 0) return '';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `· ETA ${m > 0 ? `${m}m ` : ''}${s}s`;
  };

  return (
    <div className={clsx('w-full space-y-1.5', className)}>
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-text-primary truncate">
          {stage ? `${stage} — ` : ''}
          {message || 'Processing...'}
        </span>
        <span className="text-text-secondary tabular-nums whitespace-nowrap ml-2">
          {speed ? `${speed} ` : ''}
          {formatEta(etaSeconds)}{' '}
          {!isIndeterminate && <span className="font-semibold text-text-primary">{clamped.toFixed(1)}%</span>}
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-surface-raised border border-border">
        {isIndeterminate ? (
          <div className="h-full w-1/3 rounded-full bg-brand animate-[pulse_1.5s_ease-in-out_infinite]" />
        ) : (
          <div
            className="h-full rounded-full bg-brand transition-all duration-300 ease-out"
            style={{ width: `${clamped}%` }}
          />
        )}
      </div>
    </div>
  );
};

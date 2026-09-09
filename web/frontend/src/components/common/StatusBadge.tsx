import React from 'react';
import { clsx } from 'clsx';

export interface StatusBadgeProps {
  status: string;
  className?: string;
  size?: 'sm' | 'md';
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, className, size = 'md' }) => {
  let colorStyle = 'bg-slate-800/80 text-slate-300 border-slate-700';
  let dotColor = 'bg-slate-400';

  const s = status.toLowerCase();

  if (s === 'ready' || s === 'completed') {
    colorStyle = 'bg-status-success/10 text-status-success border-status-success/30';
    dotColor = 'bg-status-success';
  } else if (
    s === 'busy' ||
    s === 'running' ||
    s === 'downloading' ||
    s === 'installing' ||
    s === 'preparing' ||
    s === 'finalizing'
  ) {
    colorStyle = 'bg-status-warning/10 text-status-warning border-status-warning/30';
    dotColor = 'bg-status-warning animate-pulse';
  } else if (s === 'failed' || s === 'error' || s === 'incompatible') {
    colorStyle = 'bg-status-error/10 text-status-error border-status-error/30';
    dotColor = 'bg-status-error';
  } else if (s === 'offline' || s === 'cancelled' || s === 'not installed' || s === 'interrupted') {
    colorStyle = 'bg-surface-raised text-text-secondary border-border';
    dotColor = 'bg-text-muted';
  } else if (s === 'coming soon') {
    colorStyle = 'bg-accent-focus/10 text-accent-focus border-accent-focus/30';
    dotColor = 'bg-accent-focus';
  }

  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs font-medium';

  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full border',
        sizeClasses,
        colorStyle,
        className
      )}
    >
      <span className={clsx('h-1.5 w-1.5 rounded-full', dotColor)} />
      <span>{status}</span>
    </span>
  );
};

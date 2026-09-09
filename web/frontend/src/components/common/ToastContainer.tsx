import React from 'react';
import { useToast, ToastItem } from '../../context/ToastContext';
import { CheckCircle2, AlertTriangle, AlertCircle, Info, X } from 'lucide-react';

export const ToastContainer: React.FC = () => {
  const { toasts, removeToast } = useToast();

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2 pointer-events-none max-w-sm w-full">
      {toasts.map((toast) => (
        <ToastCard key={toast.id} toast={toast} onClose={() => removeToast(toast.id)} />
      ))}
    </div>
  );
};

const ToastCard: React.FC<{ toast: ToastItem; onClose: () => void }> = ({ toast, onClose }) => {
  const getIcon = () => {
    switch (toast.type) {
      case 'success':
        return <CheckCircle2 className="h-5 w-5 text-status-success shrink-0" />;
      case 'error':
        return <AlertCircle className="h-5 w-5 text-status-error shrink-0" />;
      case 'warning':
        return <AlertTriangle className="h-5 w-5 text-status-warning shrink-0" />;
      case 'info':
      default:
        return <Info className="h-5 w-5 text-brand shrink-0" />;
    }
  };

  const getBorderColor = () => {
    switch (toast.type) {
      case 'success':
        return 'border-status-success/30 shadow-[0_0_20px_rgba(52,211,153,0.15)]';
      case 'error':
        return 'border-status-error/30 shadow-[0_0_20px_rgba(248,113,113,0.15)]';
      case 'warning':
        return 'border-status-warning/30 shadow-[0_0_20px_rgba(251,191,36,0.15)]';
      case 'info':
      default:
        return 'border-brand/30 shadow-[0_0_20px_rgba(77,232,225,0.15)]';
    }
  };

  return (
    <div
      className={`pointer-events-auto flex items-start gap-3 p-4 rounded-card bg-[#0e1628]/95 backdrop-blur-md border ${getBorderColor()} text-text-primary transition-all duration-300 animate-in fade-in slide-in-from-bottom-2`}
    >
      {getIcon()}
      <div className="flex-1 min-w-0">
        <h4 className="text-xs font-bold text-text-primary">{toast.title}</h4>
        {toast.message && (
          <p className="text-[11px] text-text-secondary mt-0.5 leading-relaxed">{toast.message}</p>
        )}
        {toast.action && (
          <button
            onClick={() => {
              toast.action?.onClick();
              onClose();
            }}
            className="mt-2 text-[11px] font-semibold text-brand hover:underline flex items-center gap-1"
          >
            {toast.action.label}
          </button>
        )}
      </div>
      <button
        onClick={onClose}
        className="text-text-muted hover:text-text-primary transition-colors p-1 -mr-1 -mt-1 rounded hover:bg-surface-raised"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
};

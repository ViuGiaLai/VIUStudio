import React, { createContext, useContext, useState, useCallback } from 'react';

export type ToastType = 'success' | 'error' | 'info' | 'warning';

export interface ToastItem {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
  duration?: number;
  action?: {
    label: string;
    onClick: () => void;
  };
}

interface ToastContextValue {
  toasts: ToastItem[];
  showToast: (toast: Omit<ToastItem, 'id'>) => string;
  removeToast: (id: string) => void;
  success: (title: string, message?: string, action?: ToastItem['action']) => string;
  error: (title: string, message?: string, action?: ToastItem['action']) => string;
  info: (title: string, message?: string, action?: ToastItem['action']) => string;
  warning: (title: string, message?: string, action?: ToastItem['action']) => string;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback(
    ({ type, title, message, duration = 4000, action }: Omit<ToastItem, 'id'>) => {
      const id = 'toast_' + Math.random().toString(36).substring(2, 9);
      const newToast: ToastItem = { id, type, title, message, duration, action };

      setToasts((prev) => [...prev.slice(-4), newToast]); // Keep up to 5 toasts

      if (duration > 0) {
        setTimeout(() => {
          removeToast(id);
        }, duration);
      }

      return id;
    },
    [removeToast]
  );

  const success = useCallback(
    (title: string, message?: string, action?: ToastItem['action']) =>
      showToast({ type: 'success', title, message, action }),
    [showToast]
  );

  const error = useCallback(
    (title: string, message?: string, action?: ToastItem['action']) =>
      showToast({ type: 'error', title, message, action }),
    [showToast]
  );

  const info = useCallback(
    (title: string, message?: string, action?: ToastItem['action']) =>
      showToast({ type: 'info', title, message, action }),
    [showToast]
  );

  const warning = useCallback(
    (title: string, message?: string, action?: ToastItem['action']) =>
      showToast({ type: 'warning', title, message, action }),
    [showToast]
  );

  return (
    <ToastContext.Provider
      value={{ toasts, showToast, removeToast, success, error, info, warning }}
    >
      {children}
    </ToastContext.Provider>
  );
};

export const useToast = () => {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return ctx;
};

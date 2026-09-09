import React, { useState, useEffect } from 'react';
import { Laptop, Copy, Check, RefreshCw, AlertCircle, ExternalLink, ShieldCheck } from 'lucide-react';
import { Modal } from '../common/Modal';
import { Button } from '../common/Button';
import { api } from '../../services/api';
import { useAppStore } from '../../stores/useAppStore';
import { useToast } from '../../context/ToastContext';

export interface PairDeviceModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const PairDeviceModal: React.FC<PairDeviceModalProps> = ({ isOpen, onClose }) => {
  const { refreshDevices } = useAppStore();
  const toast = useToast();
  const [code, setCode] = useState<string>('');
  const [timeLeft, setTimeLeft] = useState<number>(600); // 10 minutes in seconds
  const [copied, setCopied] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const fetchPairingCode = async () => {
    setIsLoading(true);
    try {
      const res = await api.createPairingCode();
      setCode(res.code);
      setTimeLeft(600);
      toast.info('Đã tạo mã xác thực ghép nối mới');
    } catch (e) {
      // Generate fallback local code
      const c = Math.floor(100000 + Math.random() * 900000).toString();
      setCode(c);
      setTimeLeft(600);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchPairingCode();
    }
  }, [isOpen]);

  // Countdown timer
  useEffect(() => {
    if (!isOpen || timeLeft <= 0) return;
    const timer = setInterval(() => {
      setTimeLeft((prev) => prev - 1);
    }, 1000);
    return () => clearInterval(timer);
  }, [isOpen, timeLeft]);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    toast.success('Đã sao chép mã ghép nối vào khay nhớ tạm');
    setTimeout(() => setCopied(false), 2000);
  };

  const minutes = Math.floor(timeLeft / 60);
  const seconds = timeLeft % 60;
  const timeFormatted = `${minutes}:${seconds.toString().padStart(2, '0')}`;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Ghép Nối Companion Với Máy Tính"
      description="Kết nối máy tính cá nhân để tăng tốc xử lý Whisper AI, Demucs và Render GPU cục bộ."
      maxWidth="md"
    >
      <div className="space-y-5">
        {/* Step instructions */}
        <div className="rounded-input bg-surface-raised border border-border p-3.5 space-y-2.5 text-xs">
          <div className="flex items-start gap-2 text-text-primary">
            <span className="h-5 w-5 rounded-full bg-brand/20 text-brand font-bold flex items-center justify-center shrink-0 text-xs">1</span>
            <span>Khởi chạy ứng dụng <strong>VIUStudio Companion</strong> trên máy tính của bạn.</span>
          </div>
          <div className="flex items-start gap-2 text-text-primary">
            <span className="h-5 w-5 rounded-full bg-brand/20 text-brand font-bold flex items-center justify-center shrink-0 text-xs">2</span>
            <span>Bấm vào nút <strong>Kết Nối Với Web</strong> và nhập mã xác thực gồm 6 chữ số bên dưới:</span>
          </div>
        </div>

        {/* 6-Digit Code Display */}
        <div className="flex flex-col items-center justify-center py-5 bg-background/50 rounded-card border border-border space-y-1">
          <span className="text-[11px] text-text-muted font-bold tracking-wider uppercase">MÃ XÁC THỰC GHÉP NỐI</span>
          <div className="text-3xl font-black tracking-widest text-brand font-mono tabular-nums">
            {code ? `${code.slice(0, 3)} ${code.slice(3, 6)}` : '------'}
          </div>
          <div className="flex items-center gap-2 pt-1 text-xs text-text-secondary">
            <span>Mã có hiệu lực trong:</span>
            <span className="font-semibold text-text-primary font-mono tabular-nums">{timeFormatted}</span>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-3">
          <Button
            variant="secondary"
            className="flex-1"
            onClick={handleCopy}
            disabled={!code}
          >
            {copied ? <Check className="h-4 w-4 text-status-success mr-1.5" /> : <Copy className="h-4 w-4 mr-1.5" />}
            <span>{copied ? 'Đã sao chép mã' : 'Sao chép mã 6 số'}</span>
          </Button>

          <Button
            variant="ghost"
            onClick={fetchPairingCode}
            isLoading={isLoading}
            title="Tạo mã mới"
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>

        {/* Companion deep link and troubleshooting */}
        <div className="border-t border-border pt-3 flex items-center justify-between text-xs text-text-secondary">
          <a
            href="viustudio://pair"
            className="inline-flex items-center gap-1 text-brand hover:underline font-medium"
          >
            <span>Mở Companion App</span>
            <ExternalLink className="h-3 w-3" />
          </a>

          <a
            href="/help#pairing"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-text-muted hover:text-text-primary"
          >
            <AlertCircle className="h-3 w-3" />
            <span>Hướng dẫn khắc phục lỗi</span>
          </a>
        </div>
      </div>
    </Modal>
  );
};


import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, AudioLines, ShieldCheck, UserRound, Sparkles, LogOut } from 'lucide-react';
import { PublicLayout } from '../../components/layout/PublicLayout';
import { useAppStore } from '../../stores/useAppStore';

export const SignInPage: React.FC = () => {
  const { user, authReady, isCloudEnabled, signInWithGoogle, signOut } = useAppStore();
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [authError, setAuthError] = useState('');

  const handleGoogleSignIn = async () => {
    setIsLoggingIn(true);
    setAuthError('');
    try {
      await signInWithGoogle();
    } catch (cause) {
      setAuthError(cause instanceof Error ? cause.message : 'Không thể mở đăng nhập Google.');
    } finally {
      setIsLoggingIn(false);
    }
  };

  return (
    <PublicLayout>
      <section className="account-layout">
        <div className="account-copy">
          <div className="studio-eyebrow">
            <span /> KHÔNG GIAN SÁNG TẠO
          </div>
          <h1>
            Sẵn sàng cho
            <br />
            <span className="ai-gradient-text">giọng kể tiếp theo.</span>
          </h1>
          <p>
            Bắt đầu với một file phụ đề hoặc dự án video của bạn. Bạn có thể sử dụng ngay Voice Studio
            trên trình duyệt hoặc mở toàn bộ không gian làm việc.
          </p>
          <div className="account-feature">
            <ShieldCheck className="h-5 w-5 text-brand shrink-0" />
            <span>Xử lý an toàn trên máy tính cá nhân. Không tải video lớn lên đám mây.</span>
          </div>
        </div>

        <div className="account-card">
          <span className="account-icon">
            <UserRound size={26} />
          </span>
          <h2>{user ? `Xin chào, ${user.name}` : 'Chào mừng đến VIUStudio'}</h2>
          <p>{user ? 'Dự án và cài đặt của bạn có thể đồng bộ an toàn.' : 'Chọn cách bạn muốn bắt đầu làm việc.'}</p>

          {user ? (
            <div className="space-y-2">
              <Link to="/app" className="studio-link-primary w-full text-center block">Mở không gian làm việc</Link>
              <button onClick={() => void signOut()} className="studio-link-secondary w-full cursor-pointer flex items-center justify-center gap-2">
                <LogOut size={16} /> Đăng xuất
              </button>
            </div>
          ) : (
            <button
              onClick={handleGoogleSignIn}
              disabled={isLoggingIn || !authReady || !isCloudEnabled}
              className="studio-link-primary w-full cursor-pointer flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Sparkles size={18} />
              <span>{isLoggingIn ? 'Đang chuyển đến Google...' : 'Đăng nhập với Google'}</span>
            </button>
          )}

          {authError && <p className="mt-3 text-xs text-status-error" role="alert">{authError}</p>}
          {!isCloudEnabled && <p className="mt-3 text-xs text-status-warning">Đăng nhập đám mây chưa được cấu hình. Chế độ khách vẫn dùng được.</p>}

          <div className="account-divider">
            <span>{user ? 'CÔNG CỤ NHANH' : 'CÔNG CỤ MIỄN PHÍ KHÔNG ĐỌC DỮ LIỆU TÀI KHOẢN'}</span>
          </div>

          <div className="space-y-2 mt-4">
            <Link to="/voice-studio" className="studio-link-secondary w-full text-center block border-brand/40 text-brand">
              <AudioLines size={16} className="inline mr-1.5" />
              Mở Voice Studio (SRT → MP3)
            </Link>
          </div>

          <div className="mt-4 text-center">
            <Link to="/help" className="back-link">
              Hướng dẫn & Câu hỏi thường gặp <ArrowUpRight size={15} />
            </Link>
          </div>
        </div>
      </section>
    </PublicLayout>
  );
};

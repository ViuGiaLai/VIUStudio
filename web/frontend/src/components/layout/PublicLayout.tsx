import React from 'react';
import { Link, NavLink } from 'react-router-dom';
import { ArrowLeft, ArrowUpRight, AudioLines } from 'lucide-react';

export const PublicLayout: React.FC<{children: React.ReactNode; back?: boolean}> = ({children, back = true}) => (
  <div className="public-site">
    <a href="#page-content" className="skip-link">Bỏ qua điều hướng</a>
    <header className="public-header">
      <Link to="/" className="studio-brand" aria-label="VIUStudio — Trang chủ"><span className="brand-symbol"><AudioLines size={23}/></span><span>VIU<span className="text-text-secondary">Studio</span><small>VOICE & MEDIA WORKSPACE</small></span></Link>
      <nav aria-label="Điều hướng chính"><NavLink to="/tools">Công cụ</NavLink><NavLink to="/help">Hướng dẫn</NavLink><NavLink to="/download">Desktop</NavLink></nav>
      <Link to="/voice-studio" className="studio-link-primary">Mở Voice Studio <ArrowUpRight size={17}/></Link>
    </header>
    <main id="page-content" className="public-content">
      {back && <Link to="/" className="back-link"><ArrowLeft size={16}/> Về trang chủ</Link>}
      {children}
    </main>
    <footer className="public-footer"><span>VIUStudio · Không gian sáng tạo của bạn.</span><div><Link to="/help">Trợ giúp</Link><Link to="/sign-in">Tài khoản</Link><Link to="/voice-studio">SRT → MP3</Link></div></footer>
  </div>
);

import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  FolderKanban,
  Wrench,
  ListTodo,
  Laptop,
  Cpu,
  Settings,
  HelpCircle,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  FileAudio,
  Radio,
} from 'lucide-react';
import { clsx } from 'clsx';
import { useAppStore } from '../../stores/useAppStore';

export interface SidebarProps {
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isCollapsed, onToggleCollapse }) => {
  const { activeJobs, projects, activeDevice } = useAppStore();
  const runningJobsCount = activeJobs.filter((j) =>
    ['Queued', 'Waiting for device', 'Preparing', 'Running'].includes(j.state)
  ).length;

  const studioTools = [
    { name: 'Voice Studio', to: '/app/srt-tts', icon: FileAudio, tag: 'WASM' },
    { name: 'Bộ công cụ AI', to: '/app/tools', icon: Wrench, tag: 'Tools' },
  ];

  const workspaceItems = [
    { name: 'Tổng quan', to: '/app', icon: LayoutDashboard, exact: true },
    { name: 'Dự án', to: '/app/projects', icon: FolderKanban, badge: projects.length },
    { name: 'Tác vụ', to: '/app/tasks', icon: ListTodo, badge: runningJobsCount > 0 ? runningJobsCount : undefined, pulse: runningJobsCount > 0 },
  ];

  const systemItems = [
    { name: 'Thiết bị Companion', to: '/app/devices', icon: Laptop },
    { name: 'Model & Giọng đọc', to: '/app/resources', icon: Cpu },
  ];

  const bottomItems = [
    { name: 'Cài đặt & Privacy', to: '/app/settings', icon: Settings },
    { name: 'Hướng dẫn', to: '/app/help', icon: HelpCircle },
  ];

  return (
    <aside
      className={clsx(
        'h-screen flex flex-col justify-between border-r border-border/70 bg-surface/85 backdrop-blur-2xl transition-all duration-200 sticky top-0 z-40 shadow-[12px_0_40px_rgba(0,0,0,.22)] select-none',
        isCollapsed ? 'w-16' : 'w-60'
      )}
    >
      {/* Brand Header */}
      <div className="flex flex-col min-h-0">
        <div className="h-[62px] border-b border-border/70 flex items-center justify-between px-3.5">
          <NavLink to="/" className="flex items-center gap-2.5 overflow-hidden group">
            <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-brand via-cyan-400 to-accent-focus flex items-center justify-center text-background font-black text-sm shrink-0 shadow-[0_0_24px_rgba(77,232,225,.35)] group-hover:scale-105 transition-transform">
              <Sparkles className="h-4 w-4 fill-current text-slate-950" />
            </div>
            {!isCollapsed && (
              <div className="flex flex-col">
                <span className="font-extrabold text-base tracking-tight text-text-primary whitespace-nowrap">
                  VIUStudio
                </span>
                <span className="text-[9px] font-mono tracking-widest text-brand uppercase font-bold">
                  Recap Studio
                </span>
              </div>
            )}
          </NavLink>
          <button
            onClick={onToggleCollapse}
            className="p-1 rounded-input text-text-muted hover:text-text-primary hover:bg-surface-raised transition-colors"
            title={isCollapsed ? 'Mở rộng sidebar' : 'Thu gọn sidebar'}
          >
            {isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          </button>
        </div>

        {/* Navigation list */}
        <div className="p-2 space-y-4 overflow-y-auto flex-1">
          {/* Section: Studio Creation Tools */}
          <div>
            {!isCollapsed && (
              <div className="px-2.5 mb-1.5 text-[10px] font-bold uppercase tracking-wider text-text-muted">
                Studio Tools
              </div>
            )}
            <nav className="space-y-1">
              {studioTools.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    key={item.to}
                    title={item.name}
                    aria-label={item.name}
                    to={item.to}
                    className={({ isActive }) =>
                      clsx(
                        'flex items-center gap-3 px-3 py-2 rounded-input text-xs font-semibold transition-all group relative',
                        isActive
                          ? 'bg-gradient-to-r from-brand/20 to-accent-focus/10 text-brand border border-brand/30 shadow-[0_0_20px_rgba(77,232,225,.1)]'
                          : 'text-text-secondary hover:text-text-primary hover:bg-surface-raised'
                      )
                    }
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    {!isCollapsed && <span className="truncate">{item.name}</span>}
                    {!isCollapsed && item.tag && (
                      <span className="ml-auto text-[9px] font-mono font-bold px-1.5 py-0.2 rounded bg-brand/10 border border-brand/20 text-brand">
                        {item.tag}
                      </span>
                    )}
                  </NavLink>
                );
              })}
            </nav>
          </div>

          {/* Section: Workspace */}
          <div>
            {!isCollapsed && (
              <div className="px-2.5 mb-1.5 text-[10px] font-bold uppercase tracking-wider text-text-muted">
                Workspace
              </div>
            )}
            <nav className="space-y-1">
              {workspaceItems.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    key={item.to}
                    title={item.name}
                    aria-label={item.name}
                    to={item.to}
                    end={item.exact}
                    className={({ isActive }) =>
                      clsx(
                        'flex items-center gap-3 px-3 py-2 rounded-input text-xs font-semibold transition-all group relative',
                        isActive
                          ? 'bg-gradient-to-r from-brand/20 to-accent-focus/10 text-brand border border-brand/30 shadow-[0_0_20px_rgba(77,232,225,.1)]'
                          : 'text-text-secondary hover:text-text-primary hover:bg-surface-raised'
                      )
                    }
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    {!isCollapsed && <span className="truncate">{item.name}</span>}
                    {item.badge !== undefined && (
                      <span
                        className={clsx(
                          'ml-auto rounded-full font-bold text-[10px] px-1.5 py-0.2 tabular-nums',
                          item.pulse
                            ? 'bg-status-warning/20 text-status-warning border border-status-warning/40 animate-pulse'
                            : 'bg-surface-raised border border-border text-text-muted',
                          isCollapsed && 'absolute right-1.5 top-1.5 h-2 w-2 p-0 rounded-full bg-brand'
                        )}
                      >
                        {!isCollapsed && item.badge}
                      </span>
                    )}
                  </NavLink>
                );
              })}
            </nav>
          </div>

          {/* Section: System & Devices */}
          <div>
            {!isCollapsed && (
              <div className="px-2.5 mb-1.5 text-[10px] font-bold uppercase tracking-wider text-text-muted">
                Hệ thống
              </div>
            )}
            <nav className="space-y-1">
              {systemItems.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    key={item.to}
                    title={item.name}
                    aria-label={item.name}
                    to={item.to}
                    className={({ isActive }) =>
                      clsx(
                        'flex items-center gap-3 px-3 py-2 rounded-input text-xs font-semibold transition-all group relative',
                        isActive
                          ? 'bg-gradient-to-r from-brand/20 to-accent-focus/10 text-brand border border-brand/30'
                          : 'text-text-secondary hover:text-text-primary hover:bg-surface-raised'
                      )
                    }
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    {!isCollapsed && <span className="truncate">{item.name}</span>}
                  </NavLink>
                );
              })}
            </nav>
          </div>
        </div>
      </div>

      {/* Bottom Section */}
      <div className="p-2 border-t border-border/70 space-y-2 shrink-0">
        {/* Companion Status Pill */}
        {!isCollapsed && (
          <div className="px-3 py-2 rounded-input bg-surface-raised/70 border border-border/60 text-[11px] flex items-center justify-between">
            <div className="flex items-center gap-1.5 truncate">
              <Radio
                className={clsx(
                  'h-3 w-3 shrink-0',
                  activeDevice?.ready_state === 'Ready' ? 'text-status-success animate-pulse' : 'text-text-muted'
                )}
              />
              <span className="truncate text-text-secondary">
                {activeDevice ? activeDevice.name.split('(')[0] : 'Companion'}
              </span>
            </div>
            <span className="text-[10px] text-brand font-mono font-medium">
              {activeDevice?.ready_state || 'Off'}
            </span>
          </div>
        )}

        <div className="space-y-1">
          {bottomItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                title={item.name}
                aria-label={item.name}
                to={item.to}
                className={({ isActive }) =>
                  clsx(
                    'flex items-center gap-3 px-3 py-2 rounded-input text-xs font-semibold transition-colors',
                    isActive
                      ? 'bg-brand/10 text-brand border border-brand/20'
                      : 'text-text-secondary hover:text-text-primary hover:bg-surface-raised'
                  )
                }
              >
                <Icon className="h-4 w-4 shrink-0" />
                {!isCollapsed && <span className="truncate">{item.name}</span>}
              </NavLink>
            );
          })}
        </div>
      </div>
    </aside>
  );
};

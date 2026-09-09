import React, { useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { PairDeviceModal } from '../modals/PairDeviceModal';
import { CreateProjectModal } from '../modals/CreateProjectModal';
import { useAppStore } from '../../stores/useAppStore';
import { ArrowRight } from 'lucide-react';

export const AppShell: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { activeJobs } = useAppStore();
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(() => window.innerWidth < 1024);
  const [isPairModalOpen, setIsPairModalOpen] = useState<boolean>(false);
  const [isCreateProjectModalOpen, setIsCreateProjectModalOpen] = useState<boolean>(false);

  const isEditor = location.pathname.includes('/editor');

  // Active running job for the bottom status bar
  const runningJob = activeJobs.find((j) =>
    ['Queued', 'Waiting for device', 'Preparing', 'Running'].includes(j.state)
  );

  return (
    <div className="ai-shell flex min-h-screen bg-background text-text-primary">
      {/* Sidebar */}
      <Sidebar
        isCollapsed={isSidebarCollapsed}
        onToggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
      />

      {/* Main content column */}
      <div className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden">
        <TopBar
          onOpenPairModal={() => setIsPairModalOpen(true)}
          onOpenCreateProject={() => setIsCreateProjectModalOpen(true)}
        />

        <main className="flex-1 flex flex-col overflow-y-auto min-h-0 bg-background/50">
          <div className={isEditor ? 'w-full h-full flex flex-col' : 'max-w-[1480px] w-full mx-auto p-4 md:p-6 flex-1'}>
            <Outlet />
          </div>
        </main>

        {/* Bottom Task Banner (Specification Section 5.1 & 11.2) */}
        {runningJob && runningJob.progress && (
          <div className="h-11 border-t border-border/80 bg-surface-raised/90 backdrop-blur-md px-6 flex items-center justify-between shrink-0 z-30 shadow-lg select-none">
            <div className="flex items-center gap-3 text-xs">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-brand"></span>
              </span>
              <span className="font-bold text-brand uppercase tracking-wider text-[11px]">
                {runningJob.type}
              </span>
              <span className="text-text-muted">·</span>
              <span className="text-text-primary font-medium truncate max-w-[300px] md:max-w-md">
                {runningJob.progress.stage || runningJob.progress.message}
              </span>
              <span className="text-text-secondary tabular-nums font-mono">
                {runningJob.progress.current}%
              </span>
              {runningJob.progress.speed && (
                <span className="hidden sm:inline text-text-muted text-[11px]">
                  ({runningJob.progress.speed})
                </span>
              )}
            </div>

            <button
              onClick={() => navigate(`/app/tasks/${runningJob.id}`)}
              className="inline-flex items-center gap-1 text-xs font-semibold text-brand hover:underline"
            >
              <span>Chi tiết tác vụ</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </div>

      {/* Pairing Modal */}
      <PairDeviceModal
        isOpen={isPairModalOpen}
        onClose={() => setIsPairModalOpen(false)}
      />

      {/* Global Create Project Modal */}
      <CreateProjectModal
        isOpen={isCreateProjectModalOpen}
        onClose={() => setIsCreateProjectModalOpen(false)}
      />
    </div>
  );
};

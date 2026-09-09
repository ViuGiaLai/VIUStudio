import React from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { useAppStore } from './stores/useAppStore';
import { PublicLayout } from './components/layout/PublicLayout';

const lazyPage = <T extends Record<string, React.ComponentType<any>>>(
  loader: () => Promise<T>,
  exportName: keyof T,
) => React.lazy(async () => ({ default: (await loader())[exportName] }));

const LandingPage = lazyPage(() => import('./pages/public/LandingPage'), 'LandingPage');
const PublicToolsPage = lazyPage(() => import('./pages/public/PublicToolsPage'), 'PublicToolsPage');
const DownloadPage = lazyPage(() => import('./pages/public/DownloadPage'), 'DownloadPage');
const HelpPage = lazyPage(() => import('./pages/public/HelpPage'), 'HelpPage');
const SignInPage = lazyPage(() => import('./pages/public/SignInPage'), 'SignInPage');
const OverviewPage = lazyPage(() => import('./pages/app/OverviewPage'), 'OverviewPage');
const ProjectsPage = lazyPage(() => import('./pages/app/ProjectsPage'), 'ProjectsPage');
const EditorPage = lazyPage(() => import('./pages/app/EditorPage'), 'EditorPage');
const ToolsHubPage = lazyPage(() => import('./pages/app/ToolsHubPage'), 'ToolsHubPage');
const SrtTtsPage = lazyPage(() => import('./pages/app/SrtTtsPage'), 'SrtTtsPage');
const TasksPage = lazyPage(() => import('./pages/app/TasksPage'), 'TasksPage');
const TaskDetailPage = lazyPage(() => import('./pages/app/TaskDetailPage'), 'TaskDetailPage');
const DevicesPage = lazyPage(() => import('./pages/app/DevicesPage'), 'DevicesPage');
const ResourcesPage = lazyPage(() => import('./pages/app/ResourcesPage'), 'ResourcesPage');
const SettingsPage = lazyPage(() => import('./pages/app/SettingsPage'), 'SettingsPage');

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, authReady } = useAppStore();
  const location = useLocation();
  if (!authReady) {
    return <div className="min-h-screen grid place-items-center bg-bg text-xs text-text-secondary">Đang kiểm tra phiên đăng nhập…</div>;
  }
  if (!user) return <Navigate to="/sign-in" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
};

import { ToastProvider } from './context/ToastContext';
import { ToastContainer } from './components/common/ToastContainer';

export const App: React.FC = () => {
  return (
    <ToastProvider>
      <React.Suspense fallback={<div className="min-h-screen grid place-items-center bg-bg text-xs text-text-secondary">Đang tải VIUStudio…</div>}>
      <Routes>
      {/* Public Landing & Marketing */}
      <Route path="/" element={<LandingPage />} />
      <Route path="/tools" element={<PublicToolsPage />} />
      <Route path="/download" element={<DownloadPage />} />
      <Route path="/help" element={<HelpPage />} />
      <Route path="/sign-in" element={<SignInPage />} />
      <Route path="/voice-studio" element={<PublicLayout><SrtTtsPage /></PublicLayout>} />

      {/* Toàn bộ /app được bảo vệ trước khi AppShell/sidebar có thể render. */}
      <Route path="/app" element={<ProtectedRoute><AppShell /></ProtectedRoute>}>
        <Route index element={<OverviewPage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="projects/:projectId/editor" element={<EditorPage />} />
        <Route path="tools" element={<ToolsHubPage />} />
        <Route path="srt-tts" element={<SrtTtsPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="tasks/:jobId" element={<TaskDetailPage />} />
        <Route path="devices" element={<DevicesPage />} />
        <Route path="resources" element={<ResourcesPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="help" element={<Navigate to="/help" replace />} />
      </Route>

      {/* Catch-all fallback */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
      </React.Suspense>
    <ToastContainer />
    </ToastProvider>
  );
};

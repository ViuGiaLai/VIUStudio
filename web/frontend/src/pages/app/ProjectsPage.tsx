import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  FolderKanban,
  Plus,
  Search,
  LayoutGrid,
  List,
  MoreVertical,
  Laptop,
  Copy,
  Trash2,
  Clock,
  Sparkles,
  Film,
  Layers,
  ArrowUpRight,
  ExternalLink,
  Upload,
  Download,
  CheckSquare,
  Square,
  ArrowUpDown,
  Filter,
  FileCode,
} from 'lucide-react';
import { useAppStore } from '../../stores/useAppStore';
import { Button } from '../../components/common/Button';
import { CreateProjectModal } from '../../components/modals/CreateProjectModal';
import { useToast } from '../../context/ToastContext';

export const ProjectsPage: React.FC = () => {
  const navigate = useNavigate();
  const {
    projects,
    duplicateProject,
    deleteProject,
    createProject,
    activeDevice,
    loadSampleDemoProject,
  } = useAppStore();
  const toast = useToast();

  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [searchQuery, setSearchQuery] = useState('');
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);

  // Filter & Sort & Batch
  const [statusFilter, setStatusFilter] = useState<'all' | 'ready' | 'in_progress'>('all');
  const [sortBy, setSortBy] = useState<'newest' | 'oldest' | 'name' | 'duration'>('newest');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  // Filter logic
  let filteredProjects = projects.filter((p) => {
    const matchesSearch = p.name.toLowerCase().includes(searchQuery.toLowerCase());
    if (!matchesSearch) return false;
    if (statusFilter === 'ready') return p.sync_status === 'Synced';
    if (statusFilter === 'in_progress') return p.sync_status === 'Draft saved in browser' || p.sync_status === 'Saved locally';
    return true;
  });

  // Sort logic
  filteredProjects = [...filteredProjects].sort((a, b) => {
    if (sortBy === 'newest') return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
    if (sortBy === 'oldest') return new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime();
    if (sortBy === 'name') return a.name.localeCompare(b.name);
    if (sortBy === 'duration') return (b.duration_ms || 0) - (a.duration_ms || 0);
    return 0;
  });

  const handleDuplicate = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setActiveMenuId(null);
    try {
      await duplicateProject(id);
      toast.success('Đã nhân bản dự án');
    } catch (err: any) {
      toast.error('Nhân bản thất bại', err.message);
    }
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setActiveMenuId(null);
    if (confirm('Bạn có chắc chắn muốn xóa dự án này?')) {
      try {
        await deleteProject(id);
        toast.info('Đã xóa dự án thành công');
      } catch (err: any) {
        toast.error('Xóa thất bại', err.message);
      }
    }
  };

  // Import Project JSON
  const handleImportProject = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (evt) => {
      try {
        const data = JSON.parse(evt.target?.result as string);
        if (data && data.name) {
          createProject({
            name: data.name + ' (Nhập)',
            device_id: data.device_id || activeDevice?.device_id || 'dev_browser_client',
            source_lang: data.languages?.source_lang || 'vi',
            target_lang: data.languages?.target_lang || 'vi',
            goal: data.goal || 'Subtitles + voice',
          });
          toast.success('Nhập dự án thành công', `Đã tạo: ${data.name}`);
        } else {
          toast.error('Lỗi tệp JSON', 'File JSON không chứa cấu trúc dự án hợp lệ');
        }
      } catch (err: any) {
        toast.error('Lỗi đọc file', err.message);
      }
    };
    reader.readAsText(file);
  };

  // Export Project JSON
  const handleExportProjectJson = (prj: any, e: React.MouseEvent) => {
    e.stopPropagation();
    const jsonStr = JSON.stringify(prj, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${prj.name.replace(/\s+/g, '_')}_backup.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Đã xuất file dự án (.json)');
  };

  // Batch Delete
  const handleBatchDelete = async () => {
    if (selectedIds.length === 0) return;
    if (confirm(`Bạn có chắc muốn xóa ${selectedIds.length} dự án đã chọn?`)) {
      for (const id of selectedIds) {
        await deleteProject(id);
      }
      setSelectedIds([]);
      toast.info(`Đã xóa ${selectedIds.length} dự án đã chọn`);
    }
  };

  const toggleSelectProject = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]));
  };

  const toggleSelectAll = () => {
    if (selectedIds.length === filteredProjects.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(filteredProjects.map((p) => p.id));
    }
  };

  const formatDuration = (ms?: number) => {
    if (!ms) return '00:45';
    const totalSec = Math.round(ms / 1000);
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-black text-text-primary tracking-tight">Dự Án Recap Video</h1>
          <p className="text-xs text-text-secondary mt-1">
            Quản lý các quy trình timeline, kịch bản phụ đề và file xuất video của bạn.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Import JSON Project */}
          <label className="cursor-pointer">
            <input type="file" accept=".json" onChange={handleImportProject} className="hidden" />
            <span className="inline-flex items-center gap-1.5 px-3 py-2 rounded-input bg-surface border border-border hover:border-brand/40 text-xs font-semibold text-text-primary transition-colors">
              <Upload className="h-4 w-4 text-brand" />
              <span>Nhập JSON</span>
            </span>
          </label>

          <Button variant="primary" onClick={() => setIsCreateModalOpen(true)}>
            <Plus className="h-4 w-4 mr-1.5" />
            <span>Tạo Dự Án Mới</span>
          </Button>
        </div>
      </div>

      {/* Filter and View Bar */}
      <div className="flex flex-col gap-3 bg-surface p-3 rounded-card border border-border shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" />
            <input
              type="text"
              placeholder="Lọc dự án theo tên..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-surface-raised border border-border rounded-input pl-9 pr-4 py-2 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-brand"
            />
          </div>

          <div className="flex items-center gap-3">
            {/* Sort Dropdown */}
            <div className="flex items-center gap-1.5 text-xs text-text-muted">
              <ArrowUpDown className="h-3.5 w-3.5" />
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as any)}
                className="bg-surface-raised border border-border rounded-input px-2.5 py-1.5 text-xs text-text-primary focus:outline-none focus:border-brand"
              >
                <option value="newest">Mới nhất</option>
                <option value="oldest">Cũ nhất</option>
                <option value="name">Tên A-Z</option>
                <option value="duration">Thời lượng</option>
              </select>
            </div>

            {/* Grid / List View Toggle */}
            <div className="flex items-center gap-1 border-l border-border pl-2">
              <button
                onClick={() => setViewMode('grid')}
                className={`p-1.5 rounded-input border transition-colors ${
                  viewMode === 'grid'
                    ? 'bg-brand/15 border-brand/40 text-brand'
                    : 'border-border text-text-muted hover:text-text-primary'
                }`}
                title="Dạng lưới"
              >
                <LayoutGrid className="h-4 w-4" />
              </button>
              <button
                onClick={() => setViewMode('list')}
                className={`p-1.5 rounded-input border transition-colors ${
                  viewMode === 'list'
                    ? 'bg-brand/15 border-brand/40 text-brand'
                    : 'border-border text-text-muted hover:text-text-primary'
                }`}
                title="Dạng danh sách"
              >
                <List className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Sub filter status chips and batch delete */}
        <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-border/60 text-xs">
          <div className="flex items-center gap-1.5">
            <Filter className="h-3 w-3 text-text-muted" />
            {[
              { id: 'all', label: 'Tất cả' },
              { id: 'ready', label: 'Đã sẵn sàng' },
              { id: 'in_progress', label: 'Đang xử lý' },
            ].map((st) => (
              <button
                key={st.id}
                onClick={() => setStatusFilter(st.id as any)}
                className={`px-2.5 py-1 rounded-full text-[11px] font-semibold transition-colors ${
                  statusFilter === st.id
                    ? 'bg-brand/15 text-brand border border-brand/30'
                    : 'text-text-muted hover:text-text-primary'
                }`}
              >
                {st.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            {filteredProjects.length > 0 && (
              <button
                onClick={toggleSelectAll}
                className="text-[11px] text-text-muted hover:text-text-primary flex items-center gap-1"
              >
                {selectedIds.length === filteredProjects.length ? (
                  <CheckSquare className="h-3.5 w-3.5 text-brand" />
                ) : (
                  <Square className="h-3.5 w-3.5" />
                )}
                <span>Chọn tất cả ({filteredProjects.length})</span>
              </button>
            )}

            {selectedIds.length > 0 && (
              <Button variant="danger" size="sm" onClick={handleBatchDelete}>
                <Trash2 className="h-3 w-3 mr-1" />
                <span>Xóa {selectedIds.length} dự án</span>
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Projects Display */}
      {filteredProjects.length === 0 ? (
        <div className="rounded-card border border-border bg-surface p-12 text-center space-y-3">
          <FolderKanban className="h-12 w-12 text-text-muted mx-auto opacity-50" />
          <h3 className="text-sm font-bold text-text-primary">
            {searchQuery ? 'Không tìm thấy dự án phù hợp' : 'Chưa có dự án nào trong không gian làm việc'}
          </h3>
          <p className="text-xs text-text-secondary max-w-sm mx-auto">
            {searchQuery
              ? 'Không có dự án nào khớp với từ khóa tìm kiếm.'
              : 'Bắt đầu sáng tạo bằng cách bấm "Tạo Dự Án Mới" hoặc nạp dự án demo mẫu để thử nghiệm ngay.'}
          </p>
          <div className="pt-2 flex items-center justify-center gap-3">
            <Button variant="primary" size="sm" onClick={() => setIsCreateModalOpen(true)}>
              <Plus className="h-3.5 w-3.5 mr-1" />
              <span>Tạo Dự Án Mới</span>
            </Button>
            {!searchQuery && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  loadSampleDemoProject();
                  toast.success('Đã nạp dự án mẫu', 'Dự án demo đã được nạp thành công!');
                }}
              >
                <FileCode className="h-3.5 w-3.5 mr-1 text-brand" />
                <span>Nạp Dự Án Mẫu</span>
              </Button>
            )}
          </div>
        </div>
      ) : viewMode === 'grid' ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredProjects.map((prj) => (
            <div
              key={prj.id}
              onClick={() => navigate(`/app/projects/${prj.id}/editor`)}
              className="rounded-card border border-border bg-surface hover:border-brand/40 transition-all cursor-pointer shadow-sm group flex flex-col justify-between overflow-hidden relative"
            >
              {/* Thumbnail header */}
              <div className="h-32 bg-gradient-to-br from-surface-raised via-slate-900 to-indigo-950/70 relative p-4 flex flex-col justify-between border-b border-border/80">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <button
                      onClick={(e) => toggleSelectProject(prj.id, e)}
                      className="p-1 rounded bg-background/60 hover:bg-surface-raised text-text-muted hover:text-brand transition-colors"
                      title="Chọn dự án"
                    >
                      {selectedIds.includes(prj.id) ? (
                        <CheckSquare className="h-3.5 w-3.5 text-brand" />
                      ) : (
                        <Square className="h-3.5 w-3.5" />
                      )}
                    </button>
                    <span className="bg-background/80 backdrop-blur-md border border-border/70 px-2 py-0.5 rounded-full text-[10px] font-mono font-bold text-brand uppercase tracking-wider">
                      {prj.languages.source_lang.toUpperCase()} → {prj.languages.target_lang.toUpperCase()}
                    </span>
                  </div>

                  <div className="relative">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setActiveMenuId(activeMenuId === prj.id ? null : prj.id);
                      }}
                      className="p-1 rounded bg-background/60 hover:bg-surface-raised text-text-muted hover:text-text-primary"
                    >
                      <MoreVertical className="h-4 w-4" />
                    </button>

                    {activeMenuId === prj.id && (
                      <div className="absolute right-0 mt-1 w-44 rounded-card border border-border bg-surface-raised p-1 shadow-2xl z-30 animate-in fade-in zoom-in-95 duration-100">
                        <button
                          onClick={(e) => handleDuplicate(prj.id, e)}
                          className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:bg-surface rounded-input"
                        >
                          <Copy className="h-3.5 w-3.5" />
                          <span>Nhân bản</span>
                        </button>
                        <button
                          onClick={(e) => handleExportProjectJson(prj, e)}
                          className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:bg-surface rounded-input"
                        >
                          <Download className="h-3.5 w-3.5 text-brand" />
                          <span>Xuất JSON sao lưu</span>
                        </button>
                        <button
                          onClick={(e) => handleDelete(prj.id, e)}
                          className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-status-error hover:bg-status-error/10 rounded-input"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          <span>Xóa dự án</span>
                        </button>
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex items-center justify-between text-white/80">
                  <div className="flex items-center gap-1.5">
                    <Film className="h-5 w-5 text-brand opacity-80" />
                    <span className="text-[11px] font-mono font-medium">{formatDuration(prj.duration_ms)}</span>
                  </div>
                  <span className="text-[10px] bg-black/60 px-2 py-0.5 rounded backdrop-blur-sm text-text-muted">
                    Rev #{prj.revision}
                  </span>
                </div>
              </div>

              {/* Card Body */}
              <div className="p-4 space-y-3 flex-1 flex flex-col justify-between">
                <div>
                  <h3 className="text-sm font-bold text-text-primary group-hover:text-brand transition-colors line-clamp-1">
                    {prj.name}
                  </h3>
                  <div className="text-xs text-text-secondary mt-1 flex items-center gap-1.5">
                    <Laptop className="h-3.5 w-3.5 text-text-muted" />
                    <span className="truncate">{prj.device_name || 'Thiết bị chưa xác định'}</span>
                  </div>
                </div>

                <div className="pt-3 border-t border-border flex items-center justify-between text-[11px] text-text-muted">
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    <span>{new Date(prj.updated_at).toLocaleDateString('vi-VN')}</span>
                  </span>
                  <span className="text-brand font-semibold group-hover:underline flex items-center gap-0.5">
                    <span>Mở Editor</span>
                    <ArrowUpRight className="h-3.5 w-3.5" />
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        /* List Mode */
        <div className="rounded-card border border-border bg-surface overflow-hidden shadow-sm">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-border bg-surface-raised text-text-muted uppercase text-[10px] tracking-wider">
              <tr>
                <th className="w-10 px-4 py-3"></th>
                <th className="px-4 py-3">Tên Dự Án</th>
                <th className="px-4 py-3">Ngôn Ngữ</th>
                <th className="px-4 py-3">Thời Lượng</th>
                <th className="px-4 py-3">Thiết Bị</th>
                <th className="px-4 py-3">Đồng Bộ</th>
                <th className="px-4 py-3">Cập Nhật</th>
                <th className="px-4 py-3 text-right">Tác Vụ</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filteredProjects.map((prj) => (
                <tr
                  key={prj.id}
                  onClick={() => navigate(`/app/projects/${prj.id}/editor`)}
                  className={`hover:bg-surface-raised/60 cursor-pointer transition-colors ${
                    selectedIds.includes(prj.id) ? 'bg-brand/5' : ''
                  }`}
                >
                  <td className="px-4 py-3" onClick={(e) => toggleSelectProject(prj.id, e)}>
                    {selectedIds.includes(prj.id) ? (
                      <CheckSquare className="h-4 w-4 text-brand" />
                    ) : (
                      <Square className="h-4 w-4 text-text-muted" />
                    )}
                  </td>
                  <td className="px-4 py-3 font-semibold text-text-primary">
                    <div className="flex items-center gap-2">
                      <FolderKanban className="h-4 w-4 text-brand" />
                      <span>{prj.name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-text-secondary font-mono text-[11px]">
                    {prj.languages.source_lang.toUpperCase()} → {prj.languages.target_lang.toUpperCase()}
                  </td>
                  <td className="px-4 py-3 font-mono text-text-muted tabular-nums">
                    {formatDuration(prj.duration_ms)}
                  </td>
                  <td className="px-4 py-3 text-text-secondary">{prj.device_name || 'Thiết bị chưa xác định'}</td>
                  <td className="px-4 py-3 text-text-muted">{prj.sync_status}</td>
                  <td className="px-4 py-3 text-text-muted">
                    {new Date(prj.updated_at).toLocaleDateString('vi-VN')}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={(e) => handleExportProjectJson(prj, e)}
                        className="p-1 rounded text-text-muted hover:text-brand"
                        title="Xuất JSON sao lưu"
                      >
                        <Download className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={(e) => handleDuplicate(prj.id, e)}
                        className="p-1 rounded text-text-muted hover:text-brand"
                        title="Nhân bản"
                      >
                        <Copy className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={(e) => handleDelete(prj.id, e)}
                        className="p-1 rounded text-text-muted hover:text-status-error"
                        title="Xóa dự án"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create Modal */}
      <CreateProjectModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
      />
    </div>
  );
};

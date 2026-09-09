import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import {
  UserProfile,
  UserSettings,
  DeviceCapability,
  Project,
  CueItem,
  Job,
  ModelResource,
  CreateProjectRequest,
  CreateJobRequest,
} from '@viustudio/shared';
import { api } from '../services/api';
import { supabase, supabaseConfigured } from '../lib/supabase';
import {
  deleteCloudProject,
  loadCloudWorkspace,
  profileFromAuthUser,
  saveCloudProject,
  saveCloudSettings,
  signInWithGoogle,
  signOutCloud,
} from '../services/cloudStore';
import {
  detectRealClientHardware,
  probeCompanionDaemon,
  CompanionStatus,
  BrowserStorageInfo,
  getBrowserStorageEstimate,
  clearRealBrowserStorage,
} from '../services/hardware';

/**
 * Generate real device capability object from actual client browser environment
 */
export function getRealBrowserDevice(): DeviceCapability {
  const hw = detectRealClientHardware();
  return {
    device_id: 'dev_browser_client',
    name: `Trình Duyệt Web (${hw.os})`,
    protocol_version: '1.0',
    companion_version: 'WebAssembly Studio 2.4',
    ready_state: 'Ready',
    last_seen_at: new Date().toISOString(),
    hardware: {
      os: hw.os,
      cpu_name: hw.cpu_name,
      cpu_cores: hw.cpu_cores,
      gpu_name: hw.gpu_name,
      has_gpu_acceleration: hw.has_gpu_acceleration,
      total_memory_bytes: hw.total_memory_bytes,
      available_memory_bytes: Math.round(hw.total_memory_bytes * 0.7),
    },
    engines: ['piper_wasm', 'web_audio', 'srt_builder'],
    languages: ['vi', 'en', 'auto'],
    encoders: ['browser_recorder', 'mp3_lame'],
    supported_actions: ['tts', 'srt_edit', 'mp3_export'],
    active_jobs_count: 0,
  };
}

// Keep export for backwards compatibility
export const DEFAULT_DEVICES: DeviceCapability[] = [getRealBrowserDevice()];
export const DEFAULT_PROJECT_CUES: Record<string, CueItem[]> = {};
export const DEFAULT_PROJECTS: Project[] = [];
export const DEFAULT_JOBS: Job[] = [];
export const DEFAULT_RESOURCES: ModelResource[] = [
  {
    id: 'res_whisper_base',
    name: 'Whisper Base (142 MB)',
    category: 'speech_recognition',
    engine: 'whisper',
    is_integrated: true,
    description: 'Cân bằng độ chính xác và tốc độ (142 MB). Khuyên dùng cho audio 1–2 phút trên điện thoại 6GB+ RAM. Với file dài hơn, nên kết nối PC Companion để tránh quá tải bộ nhớ trình duyệt.',
    languages: ['vi', 'en', 'auto'],
    status: 'Not installed',
    download_size_bytes: 142000000,
  },
  {
    id: 'res_whisper_tiny',
    name: 'Whisper Tiny (75 MB)',
    category: 'speech_recognition',
    engine: 'whisper',
    is_integrated: true,
    description: 'Mô hình siêu nhẹ (75 MB). Tối ưu cho audio ngắn (< 3 phút) trên mobile hoặc thiết bị cấu hình thấp nhằm tiết kiệm pin và tránh tràn heap WASM.',
    languages: ['vi', 'en', 'auto'],
    status: 'Not installed',
    download_size_bytes: 75000000,
  },
  {
    id: 'res_piper_vais',
    name: 'Piper TTS: Tiếng Việt VAIS 1000',
    category: 'tts',
    engine: 'piper',
    is_integrated: true,
    description: 'Giọng đọc nơ-ron tiếng Việt tự nhiên, chạy 100% bằng WebAssembly trong trình duyệt (Mobile & PC).',
    languages: ['vi'],
    status: 'Ready',
    download_size_bytes: 65000000,
    installed_size_bytes: 65000000,
  },
  {
    id: 'res_piper_vivos',
    name: 'Piper TTS: Tiếng Việt VIVOS',
    category: 'tts',
    engine: 'piper',
    is_integrated: true,
    description: 'Giọng đọc tiếng Việt truyền cảm, phát âm rõ ràng cho bản tin và tóm tắt phim.',
    languages: ['vi'],
    status: 'Ready',
    download_size_bytes: 58000000,
    installed_size_bytes: 58000000,
  },
  {
    id: 'res_whisper_turbo',
    name: 'Whisper Turbo v3 (PC GPU)',
    category: 'speech_recognition',
    engine: 'whisper',
    is_integrated: true,
    description: 'Mô hình nhận diện tốc độ cao (8x realtime). Yêu cầu PC Companion Daemon.',
    languages: ['vi', 'en', 'ja'],
    status: 'Not installed',
    download_size_bytes: 1600000000,
  },
  {
    id: 'res_whisper_large',
    name: 'Whisper Large v3 (PC Pro)',
    category: 'speech_recognition',
    engine: 'whisper',
    is_integrated: true,
    description: 'Độ chính xác cao nhất cho kịch bản chuyên nghiệp. Cần PC có 4GB+ VRAM.',
    languages: ['all'],
    status: 'Not installed',
    download_size_bytes: 2900000000,
  },
  {
    id: 'res_demucs_v4',
    name: 'Demucs v4 Hybrid Transformer (1.1 GB)',
    category: 'separation',
    engine: 'demucs',
    is_integrated: true,
    description: 'Mô hình Demucs v4 tách giọng/nhạc nền chất lượng cao. Khối lượng tính toán lớn, yêu cầu PC Companion Daemon (chạy local trên GPU/CPU máy tính) để tránh treo hoặc nóng máy trên thiết bị di động.',
    languages: ['all'],
    status: 'Not installed',
    download_size_bytes: 1100000000,
  },
];

interface AppContextType {
  user: UserProfile | null;
  authReady: boolean;
  isCloudEnabled: boolean;
  settings: UserSettings | null;
  devices: DeviceCapability[];
  activeDevice: DeviceCapability | null;
  projects: Project[];
  projectCues: Record<string, CueItem[]>;
  activeProject: (Project & { cues: CueItem[] }) | null;
  activeJobs: Job[];
  resources: ModelResource[];
  companionStatus: CompanionStatus | null;
  browserStorage: BrowserStorageInfo;
  isLoading: boolean;
  error: string | null;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
  setActiveDevice: (dev: DeviceCapability) => void;
  probeCompanion: () => Promise<CompanionStatus>;
  refreshDevices: () => Promise<void>;
  refreshProjects: () => Promise<void>;
  refreshJobs: () => Promise<void>;
  refreshResources: () => Promise<void>;
  updateSettings: (newSettings: Partial<UserSettings>) => Promise<void>;
  refreshBrowserStorage: () => Promise<void>;
  clearBrowserStorage: () => Promise<void>;
  loadProject: (id: string) => Promise<void>;
  createProject: (req: CreateProjectRequest) => Promise<Project>;
  duplicateProject: (id: string) => Promise<Project>;
  deleteProject: (id: string) => Promise<void>;
  updateActiveProjectCues: (cues: CueItem[]) => void;
  saveActiveProject: () => Promise<void>;
  createJob: (req: CreateJobRequest) => Promise<Job>;
  cancelJob: (id: string) => Promise<void>;
  installResource: (resourceId: string) => Promise<void>;
  uninstallResource: (resourceId: string) => Promise<void>;
  loadSampleDemoProject: () => void;
  restoreBackup: (data: { projects: Project[]; cues: Record<string, CueItem[]>; settings?: UserSettings }) => Promise<void>;
}

const AppContext = createContext<AppContextType | null>(null);

// Local storage keys
const LS_PROJECTS = 'viustudio_projects';
const LS_CUES = 'viustudio_cues_map';
const LS_DEVICES = 'viustudio_devices';
const LS_JOBS = 'viustudio_jobs';
const LS_RESOURCES = 'viustudio_resources';
const LS_SETTINGS = 'viustudio_settings';

const readStored = <T,>(key: string, fallback: T): T => {
  try {
    const value = localStorage.getItem(key);
    return value ? JSON.parse(value) as T : fallback;
  } catch {
    return fallback;
  }
};

export const AppProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [authReady, setAuthReady] = useState(!supabaseConfigured);
  const sessionEpoch = useRef(0);

  const [settings, setSettings] = useState<UserSettings | null>(() => {
    try {
      const saved = localStorage.getItem(`${LS_SETTINGS}:guest`);
      if (saved) return JSON.parse(saved);
    } catch {}
    return {
      user_id: 'guest',
      preferences: {
        default_source_lang: 'auto',
        default_target_lang: 'vi',
        export_preset: 'Balanced',
        export_bitrate_kbps: 2800,
        theme: 'dark',
        density: 'comfortable',
        preferred_device_id: 'dev_browser_client',
      },
      sync: {
        sync_subtitles_enabled: false,
        sync_metadata_enabled: true,
        last_synced_at: new Date().toISOString(),
      },
      cache_quota_gb: 5,
    };
  });

  // Base real client browser device
  const [devices, setDevices] = useState<DeviceCapability[]>(() => {
    const browserDev = getRealBrowserDevice();
    try {
      const saved = localStorage.getItem(LS_DEVICES);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) {
          // If old mock devices were saved, purge them
          const onlyFakeDefaults = parsed.every((d: any) =>
            ['dev_local_pc', 'dev_mac_m2'].includes(d.device_id)
          );
          if (onlyFakeDefaults) {
            localStorage.removeItem(LS_DEVICES);
            return [browserDev];
          }
          return parsed;
        }
      }
    } catch {}
    return [browserDev];
  });

  const [activeDevice, setActiveDevice] = useState<DeviceCapability | null>(() => {
    return devices[0] || null;
  });

  // Real projects list (starts clean/empty instead of fake hardcoded ocean/anime mock data)
  const [projects, setProjects] = useState<Project[]>(() => {
    try {
      const saved = localStorage.getItem(`${LS_PROJECTS}:guest`);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed)) {
          // If only old fake mock projects were saved, purge them
          const onlyFakeDefaults = parsed.every((p: any) =>
            ['prj_ocean_01', 'prj_anime_02', 'prj_ai_03'].includes(p.id)
          );
          if (onlyFakeDefaults) {
            localStorage.removeItem(LS_PROJECTS);
            return [];
          }
          return parsed;
        }
      }
    } catch {}
    return [];
  });

  const [cuesMap, setCuesMap] = useState<Record<string, CueItem[]>>(() => {
    try {
      const saved = localStorage.getItem(`${LS_CUES}:guest`);
      if (saved) return JSON.parse(saved);
    } catch {}
    return {};
  });

  const [activeProject, setActiveProject] = useState<(Project & { cues: CueItem[] }) | null>(null);

  // Real active jobs (starts empty instead of fake hardcoded running timer)
  const [activeJobs, setActiveJobs] = useState<Job[]>(() => {
    try {
      const saved = localStorage.getItem(`${LS_JOBS}:guest`);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed)) {
          const onlyFake = parsed.every((j: any) => j.id === 'job_render_881');
          if (onlyFake) {
            localStorage.removeItem(LS_JOBS);
            return [];
          }
          return parsed;
        }
      }
    } catch {}
    return [];
  });

  const [resources, setResources] = useState<ModelResource[]>(() => {
    try {
      const saved = localStorage.getItem(LS_RESOURCES);
      if (saved) return JSON.parse(saved);
    } catch {}
    return DEFAULT_RESOURCES;
  });

  const [companionStatus, setCompanionStatus] = useState<CompanionStatus | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const [browserStorage, setBrowserStorage] = useState<BrowserStorageInfo>({
    usageBytes: 0,
    quotaBytes: 0,
    usageMb: 0,
    quotaMb: 0,
    isSupported: false,
  });

  const refreshBrowserStorage = useCallback(async () => {
    const est = await getBrowserStorageEstimate();
    setBrowserStorage(est);
  }, []);

  const clearBrowserStorage = useCallback(async () => {
    await clearRealBrowserStorage();
    await refreshBrowserStorage();
  }, [refreshBrowserStorage]);

  useEffect(() => {
    void refreshBrowserStorage();
  }, [refreshBrowserStorage]);

  useEffect(() => {
    if (!supabase) return;
    let active = true;

    const applySession = async (authUser: Parameters<typeof profileFromAuthUser>[0] | null) => {
      if (!active) return;
      const epoch = ++sessionEpoch.current;
      setAuthReady(false);
      const owner = authUser?.id || 'guest';
      const localCues = readStored<Record<string, CueItem[]>>(`${LS_CUES}:${owner}`, {});
      setProjects(readStored(`${LS_PROJECTS}:${owner}`, []));
      setCuesMap(localCues);
      setSettings(readStored(`${LS_SETTINGS}:${owner}`, {
        user_id: owner,
        preferences: { default_source_lang: 'auto', default_target_lang: 'vi', export_preset: 'Balanced', export_bitrate_kbps: 2800, theme: 'dark', density: 'comfortable', preferred_device_id: 'dev_browser_client' },
        sync: { sync_subtitles_enabled: false, sync_metadata_enabled: true },
        cache_quota_gb: 5,
      }));
      if (!authUser) {
        setUser(null);
        setActiveProject(null);
        setProjects(readStored(`${LS_PROJECTS}:guest`, []));
        setCuesMap(readStored(`${LS_CUES}:guest`, {}));
        setActiveJobs(readStored(`${LS_JOBS}:guest`, []));
        setAuthReady(true);
        return;
      }

      const profile = profileFromAuthUser(authUser);
      setUser(profile);
      setActiveProject(null);
      setActiveJobs(readStored(`${LS_JOBS}:${profile.id}`, []));
      try {
        const cloud = await loadCloudWorkspace(profile.id);
        if (!active || epoch !== sessionEpoch.current) return;
        setProjects(cloud.projects);
        setCuesMap({ ...localCues, ...cloud.cues });
        if (cloud.settings) {
          setSettings(cloud.settings);
        } else {
          setSettings((previous) => previous ? { ...previous, user_id: profile.id } : null);
        }
        setError(null);
      } catch (cause) {
        if (active && epoch === sessionEpoch.current) setError(cause instanceof Error ? cause.message : 'Không thể đồng bộ dữ liệu Supabase.');
      } finally {
        if (active && epoch === sessionEpoch.current) setAuthReady(true);
      }
    };

    void supabase.auth.getSession().then(({ data, error: sessionError }) => {
      if (sessionError && active) setError(sessionError.message);
      return applySession(data.session?.user || null);
    });

    const { data: listener } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === 'INITIAL_SESSION' || event === 'TOKEN_REFRESHED') return;
      window.setTimeout(() => void applySession(session?.user || null), 0);
    });

    return () => {
      active = false;
      listener.subscription.unsubscribe();
    };
  }, []);

  const handleSignInWithGoogle = async () => {
    setError(null);
    await signInWithGoogle();
  };

  const handleSignOut = async () => {
    const signedOutUserId = user?.id;
    await signOutCloud();
    ++sessionEpoch.current;
    if (signedOutUserId) {
      localStorage.removeItem(`${LS_PROJECTS}:${signedOutUserId}`);
      localStorage.removeItem(`${LS_CUES}:${signedOutUserId}`);
      localStorage.removeItem(`${LS_JOBS}:${signedOutUserId}`);
      localStorage.removeItem(`${LS_SETTINGS}:${signedOutUserId}`);
    }
    setUser(null);
    setActiveProject(null);
    setProjects(readStored(`${LS_PROJECTS}:guest`, []));
    setCuesMap(readStored(`${LS_CUES}:guest`, {}));
    setActiveJobs(readStored(`${LS_JOBS}:guest`, []));
    setSettings(readStored(`${LS_SETTINGS}:guest`, {
      user_id: 'guest',
      preferences: {
        default_source_lang: 'auto', default_target_lang: 'vi', export_preset: 'Balanced',
        export_bitrate_kbps: 2800, theme: 'dark', density: 'comfortable', preferred_device_id: 'dev_browser_client',
      },
      sync: { sync_subtitles_enabled: false, sync_metadata_enabled: false },
      cache_quota_gb: 5,
    }));
  };

  // Real Companion Probe Function
  const probeCompanion = useCallback(async (): Promise<CompanionStatus> => {
    const status = await probeCompanionDaemon();
    setCompanionStatus(status);
    const hw = detectRealClientHardware();

    if (status.online) {
      const compDev: DeviceCapability = {
        device_id: 'dev_companion_pc',
        name: `Companion Cục Bộ (${status.profile || 'Port 8765'})`,
        protocol_version: '1.0',
        companion_version: status.service || 'viustudio-remote-api',
        ready_state: 'Ready',
        last_seen_at: status.timestamp,
        hardware: {
          os: hw.os,
          cpu_name: hw.cpu_name,
          cpu_cores: hw.cpu_cores,
          gpu_name: hw.gpu_name,
          has_gpu_acceleration: hw.has_gpu_acceleration,
        },
        engines: ['whisper', 'demucs', 'piper', 'ffmpeg'],
        languages: ['vi', 'en', 'ja', 'zh', 'auto'],
        encoders: ['libx264', 'nvenc'],
        supported_actions: ['transcribe', 'tts', 'separation', 'export'],
        active_jobs_count: 0,
      };

      setDevices((prev) => {
        const remaining = prev.filter((d) => d.device_id !== 'dev_companion_pc');
        return [compDev, ...remaining];
      });
      setActiveDevice(compDev);
    } else {
      setDevices((prev) =>
        prev.map((d) =>
          d.device_id === 'dev_companion_pc' ? { ...d, ready_state: 'Offline' } : d
        )
      );
      const browserDev = getRealBrowserDevice();
      setActiveDevice(browserDev);
    }
    return status;
  }, []);

  // Periodic companion probe
  useEffect(() => {
    void probeCompanion();
    const interval = setInterval(() => void probeCompanion(), 12000);
    return () => clearInterval(interval);
  }, [probeCompanion]);

  // Sync state changes to localStorage
  useEffect(() => {
    if (!authReady) return;
    try {
      localStorage.setItem(`${LS_PROJECTS}:${user?.id || 'guest'}`, JSON.stringify(projects));
    } catch {}
  }, [projects, user?.id, authReady]);

  useEffect(() => {
    if (!authReady) return;
    try {
      localStorage.setItem(`${LS_CUES}:${user?.id || 'guest'}`, JSON.stringify(cuesMap));
    } catch {}
  }, [cuesMap, user?.id, authReady]);

  useEffect(() => {
    try {
      localStorage.setItem(LS_DEVICES, JSON.stringify(devices));
    } catch {}
  }, [devices]);

  useEffect(() => {
    if (!authReady) return;
    try {
      localStorage.setItem(`${LS_JOBS}:${user?.id || 'guest'}`, JSON.stringify(activeJobs));
    } catch {}
  }, [activeJobs, user?.id, authReady]);

  useEffect(() => {
    try {
      localStorage.setItem(LS_RESOURCES, JSON.stringify(resources));
    } catch {}
  }, [resources]);

  useEffect(() => {
    if (settings && authReady) {
      try {
        localStorage.setItem(`${LS_SETTINGS}:${user?.id || 'guest'}`, JSON.stringify(settings));
      } catch {}
    }
  }, [settings, user?.id, authReady]);

  const refreshDevices = async () => {
    try {
      const devs = await api.getDevices();
      if (devs && devs.length > 0) {
        setDevices(devs);
        if (!activeDevice) setActiveDevice(devs[0]);
      } else {
        await probeCompanion();
      }
    } catch {
      await probeCompanion();
    }
  };

  const refreshProjects = async () => {
    const epoch = sessionEpoch.current;
    if (user && supabase) {
      try {
        const cloud = await loadCloudWorkspace(user.id);
        if (epoch !== sessionEpoch.current) return;
        setProjects(cloud.projects);
        setCuesMap((local) => ({ ...local, ...cloud.cues }));
        if (cloud.settings) setSettings(cloud.settings);
        setError(null);
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : 'Không thể tải dự án từ Supabase.');
      }
      return;
    }
    // Guest workspace remains local; never fall back to a server's project list.
  };

  const refreshJobs = async () => {
    try {
      const jbs = await api.getJobs();
      if (jbs && jbs.length > 0) {
        setActiveJobs(jbs);
      }
    } catch {}
  };

  const refreshResources = async () => {
    try {
      const res = await api.getResources(activeDevice?.device_id);
      if (res && res.length > 0) {
        setResources(res);
      }
    } catch {}
  };

  const updateSettings = async (newSettings: Partial<UserSettings>) => {
    if (!settings) return;
    const updated = { ...settings, ...newSettings, user_id: user?.id || 'guest' };
    setSettings(updated);
    if (user && supabase) {
      try {
        await saveCloudSettings(updated);
        setError(null);
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : 'Không thể đồng bộ cài đặt.');
        throw cause;
      }
    }
  };

  const loadProject = async (id: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const localPrj = projects.find((p) => p.id === id);
      const localCues = cuesMap[id] || [];

      if (localPrj) {
        setActiveProject({
          ...localPrj,
          cues: localCues,
        });
      } else {
        setActiveProject(null);
        setError('Không tìm thấy dự án này. Dữ liệu giả sẽ không được tự động tạo.');
      }
    } catch (e: any) {
      setError(e instanceof Error ? e.message : 'Không thể mở dự án.');
    } finally {
      setIsLoading(false);
    }
  };

  const createProject = async (req: CreateProjectRequest): Promise<Project> => {
    const newId = `prj_${crypto.randomUUID()}`;
    const starterCues: CueItem[] = [];

    const newPrj: Project = {
      id: newId,
      owner_id: user?.id || 'guest',
      name: req.name || `Dự án Recap ${new Date().toLocaleDateString('vi-VN')}`,
      revision: 1,
      generation: 1,
      device_id: req.device_id || activeDevice?.device_id || 'dev_browser_client',
      device_name: activeDevice?.name || 'Trình duyệt Web',
      languages: {
        source_lang: req.source_lang || settings?.preferences.default_source_lang || 'auto',
        target_lang: req.target_lang || settings?.preferences.default_target_lang || 'vi',
      },
      goal: req.goal || 'Subtitles + voice',
      duration_ms: 0,
      sync_status: 'Saved locally',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      tracks: [
        { id: 't1', name: 'V1 Video', kind: 'video', volume: 1.0, muted: false, solo: false, locked: false },
        { id: 't2', name: 'Original Audio', kind: 'original_audio', volume: 0.3, muted: false, solo: false, locked: false },
        { id: 't3', name: 'Dub Voice', kind: 'dub', volume: 1.25, muted: false, solo: false, locked: false },
        { id: 't4', name: 'Music Stem', kind: 'music', volume: 0.45, muted: false, solo: false, locked: false },
        { id: 't5', name: 'Subtitles', kind: 'subtitles', volume: 1.0, muted: false, solo: false, locked: false },
      ],
      audio_mix: {
        preset: 'Dialogue Focused',
        voice_volume: 1.25,
        music_volume: 0.45,
        original_volume: 0.3,
      },
    };

    setProjects((prev) => [newPrj, ...prev]);
    setCuesMap((prev) => ({ ...prev, [newId]: starterCues }));
    if (user && supabase) {
      try {
        await saveCloudProject({ ...newPrj, sync_status: 'Synced' }, starterCues, settings?.sync.sync_subtitles_enabled);
        setProjects((prev) => prev.map((item) => item.id === newId ? { ...item, sync_status: 'Synced' } : item));
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : 'Dự án đã lưu cục bộ nhưng chưa đồng bộ được.');
      }
    }
    return newPrj;
  };

  const duplicateProject = async (id: string): Promise<Project> => {
    const orig = projects.find((p) => p.id === id);
    if (!orig) throw new Error('Project not found');

    const newId = `prj_${crypto.randomUUID()}`;
    const cloned: Project = {
      ...orig,
      id: newId,
      owner_id: user?.id || 'guest',
      name: `${orig.name} (Bản sao)`,
      revision: 1,
      sync_status: 'Saved locally',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    const origCues = cuesMap[id] || [];
    const clonedCues = origCues.map((c) => ({ ...c, id: `c_${Date.now()}_${c.index}`, project_id: newId }));

    setProjects((prev) => [cloned, ...prev]);
    setCuesMap((prev) => ({ ...prev, [newId]: clonedCues }));

    if (user && supabase) {
      try {
        await saveCloudProject({ ...cloned, sync_status: 'Synced' }, clonedCues, settings?.sync.sync_subtitles_enabled);
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : 'Bản sao đã lưu cục bộ nhưng chưa đồng bộ được.');
      }
    }
    return cloned;
  };

  const deleteProject = async (id: string): Promise<void> => {
    setProjects((prev) => prev.filter((p) => p.id !== id));
    setCuesMap((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
    if (activeProject?.id === id) {
      setActiveProject(null);
    }
    if (user && supabase) {
      try {
        await deleteCloudProject(id);
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : 'Không thể xóa dự án trên đám mây.');
        await refreshProjects();
      }
    }
  };

  const updateActiveProjectCues = (cues: CueItem[]) => {
    if (!activeProject) return;
    const updated = {
      ...activeProject,
      cues,
      sync_status: 'Saved locally' as const,
      updated_at: new Date().toISOString(),
    };
    setActiveProject(updated);
    setCuesMap((prev) => ({ ...prev, [activeProject.id]: cues }));
  };

  const saveActiveProject = async () => {
    if (!activeProject) return;
    const updatedProject = {
      ...activeProject,
      owner_id: user?.id || 'guest',
      revision: activeProject.revision + 1,
      updated_at: new Date().toISOString(),
      sync_status: (user && supabase ? 'Synced' : 'Saved locally') as Project['sync_status'],
    };

    if (user && supabase) {
      try {
        await saveCloudProject(updatedProject, activeProject.cues, settings?.sync.sync_subtitles_enabled);
        setError(null);
      } catch (cause) {
        updatedProject.sync_status = 'Saved locally';
        setError(cause instanceof Error ? cause.message : 'Đã lưu cục bộ nhưng chưa đồng bộ được.');
      }
    }
    setActiveProject(updatedProject);

    setProjects((prev) =>
      prev.map((p) =>
        p.id === activeProject.id
          ? updatedProject
          : p
      )
    );
  };

  const createJob = async (req: CreateJobRequest): Promise<Job> => {
    if (!companionStatus?.online || activeDevice?.device_id !== 'dev_companion_pc') {
      throw new Error('Tác vụ này cần VIUStudio Companion đang kết nối. Voice Studio SRT → MP3 vẫn chạy trực tiếp trong trình duyệt.');
    }

    const apiJob = await api.createJob(req);
    if (apiJob && apiJob.id) {
      setActiveJobs((prev) => [apiJob, ...prev]);
      return apiJob;
    }

    throw new Error('Companion không trả về mã tác vụ hợp lệ.');
  };

  const cancelJob = async (id: string): Promise<void> => {
    setActiveJobs((prev) =>
      prev.map((j) => (j.id === id ? { ...j, state: 'Cancelled' as const, progress: undefined } : j))
    );
    api.cancelJob(id).catch(() => {});
  };

  const installResource = async (resourceId: string): Promise<void> => {
    const resource = resources.find((item) => item.id === resourceId);
    if (!resource) throw new Error('Không tìm thấy model được chọn.');
    if (resource.engine === 'piper') {
      throw new Error('Giọng Piper WebAssembly được tải và lưu cache tự động khi bạn tạo TTS; không cần cài thủ công.');
    }
    if (!companionStatus?.online || activeDevice?.device_id !== 'dev_companion_pc') {
      throw new Error('Hãy kết nối VIUStudio Companion trước khi cài model máy tính.');
    }
    setResources((prev) =>
      prev.map((r) =>
        r.id === resourceId ? { ...r, status: 'Downloading' as const } : r
      )
    );

    try {
      const installed = await api.installResource(activeDevice.device_id, resourceId);
      setResources((prev) => prev.map((item) => item.id === resourceId ? installed : item));
    } catch (cause) {
      setResources((prev) => prev.map((item) => item.id === resourceId ? { ...item, status: 'Not installed' } : item));
      throw cause;
    }
  };

  const uninstallResource = async (resourceId: string): Promise<void> => {
    setResources((prev) =>
      prev.map((item) =>
        item.id === resourceId ? { ...item, status: 'Not installed' as const } : item
      )
    );
  };

  // Explicit user-triggered sample project loader (optional on-demand demo, never forced!)
  const loadSampleDemoProject = () => {
    const sampleId = `prj_demo_${Date.now().toString(36)}`;
    const samplePrj: Project = {
      id: sampleId,
      owner_id: user?.id || 'guest',
      name: 'Dự Án Mẫu: Video Recap Phim Hoạt Hình',
      revision: 1,
      generation: 1,
      device_id: activeDevice?.device_id || 'dev_browser_client',
      device_name: activeDevice?.name || 'Trình duyệt Web',
      languages: { source_lang: 'en', target_lang: 'vi' },
      goal: 'Subtitles + voice',
      duration_ms: 22000,
      sync_status: 'Saved locally',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      tracks: [
        { id: 't1', name: 'V1 Video', kind: 'video', volume: 1.0, muted: false, solo: false, locked: false },
        { id: 't2', name: 'Original Audio', kind: 'original_audio', volume: 0.3, muted: false, solo: false, locked: false },
        { id: 't3', name: 'Dub Voice (Piper VN)', kind: 'dub', volume: 1.2, muted: false, solo: false, locked: false },
        { id: 't4', name: 'Music Stem', kind: 'music', volume: 0.5, muted: false, solo: false, locked: false },
        { id: 't5', name: 'Subtitles', kind: 'subtitles', volume: 1.0, muted: false, solo: false, locked: false },
      ],
      audio_mix: {
        preset: 'Dialogue Focused',
        voice_volume: 1.2,
        music_volume: 0.5,
        original_volume: 0.3,
      },
      export_settings: {
        output_name: 'Sample_Recap_Video.mp4',
        resolution: '1080p',
        fps: 30,
        preset: 'Balanced',
        video_bitrate_kbps: 2800,
        bitrate_mode: 'Auto',
        burn_subtitles: true,
        audio_tracks: ['t3', 't4'],
      },
    };

    const sampleCues: CueItem[] = [
      {
        id: `sc_${Date.now()}_1`,
        project_id: sampleId,
        index: 1,
        start_ms: 1000,
        end_ms: 5500,
        original_text: 'Chào mừng các bạn đến với bản tóm tắt phim tự động bằng AI.',
        translated_text: 'Welcome to our automated AI movie recap breakdown.',
        audio_status: 'Ready',
      },
      {
        id: `sc_${Date.now()}_2`,
        project_id: sampleId,
        index: 2,
        start_ms: 6000,
        end_ms: 11500,
        original_text: 'Toàn bộ giọng nói được tạo trực tiếp trên máy của bạn với Piper TTS.',
        translated_text: 'All narration voices are rendered locally using Piper TTS.',
        audio_status: 'Ready',
      },
      {
        id: `sc_${Date.now()}_3`,
        project_id: sampleId,
        index: 3,
        start_ms: 12000,
        end_ms: 18000,
        original_text: 'Bạn có thể chỉnh sửa câu thoại, mốc thời gian và xuất video thành phẩm.',
        translated_text: 'You can adjust subtitles, timing cues, and export the final video.',
        audio_status: 'Ready',
      },
    ];

    setProjects((prev) => [samplePrj, ...prev]);
    setCuesMap((prev) => ({ ...prev, [sampleId]: sampleCues }));
  };

  const restoreBackup = async (data: { projects: Project[]; cues: Record<string, CueItem[]>; settings?: UserSettings }) => {
    const ownerId = user?.id || 'guest';
    const restoredProjects = data.projects.map((project) => ({
      ...project,
      owner_id: ownerId,
      sync_status: (user && supabase ? 'Synced' : 'Saved locally') as Project['sync_status'],
      updated_at: new Date().toISOString(),
    }));
    setProjects(restoredProjects);
    setCuesMap(data.cues || {});
    if (data.settings) {
      const restoredSettings = { ...data.settings, user_id: ownerId };
      setSettings(restoredSettings);
      if (user && supabase) await saveCloudSettings(restoredSettings);
    }
    if (user && supabase) {
      await Promise.all(restoredProjects.map((project) => saveCloudProject(project, data.cues?.[project.id] || [], settings?.sync.sync_subtitles_enabled)));
    }
  };

  return (
    <AppContext.Provider
      value={{
        user,
        authReady,
        isCloudEnabled: supabaseConfigured,
        settings,
        devices,
        activeDevice,
        projects,
        projectCues: cuesMap,
        activeProject,
        activeJobs,
        resources,
        companionStatus,
        browserStorage,
        isLoading,
        error,
        signInWithGoogle: handleSignInWithGoogle,
        signOut: handleSignOut,
        setActiveDevice,
        probeCompanion,
        refreshDevices,
        refreshProjects,
        refreshJobs,
        refreshResources,
        updateSettings,
        refreshBrowserStorage,
        clearBrowserStorage,
        loadProject,
        createProject,
        duplicateProject,
        deleteProject,
        updateActiveProjectCues,
        saveActiveProject,
        createJob,
        cancelJob,
        installResource,
        uninstallResource,
        loadSampleDemoProject,
        restoreBackup,
      }}
    >
      {children}
    </AppContext.Provider>
  );
};

export const useAppStore = () => {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useAppStore must be used within AppProvider');
  return ctx;
};

import {
  Project,
  CueItem,
  DeviceCapability,
  Job,
  UserProfile,
  UserSettings,
  ModelResource,
} from '@viustudio/shared';

export interface Env {
  DB?: D1Database;
  ENVIRONMENT?: string;
  API_VERSION?: string;
  CORS_ORIGINS?: string;
}

// In-memory fallback store for development & mock runs
class MemoryStore {
  users = new Map<string, UserProfile>();
  settings = new Map<string, UserSettings>();
  devices = new Map<string, DeviceCapability>();
  pairingCodes = new Map<string, { code: string; owner_id: string; expires_at: string; used_at?: string; device_id?: string }>();
  projects = new Map<string, Project>();
  cues = new Map<string, CueItem[]>(); // project_id -> CueItem[]
  jobs = new Map<string, Job>();
  resources = new Map<string, ModelResource[]>(); // device_id -> ModelResource[]

  constructor() {
    this.seedDefaultData();
  }

  seedDefaultData() {
    const demoUser: UserProfile = {
      id: 'usr_demo_123',
      email: 'creator@viustudio.local',
      name: 'VIUStudio Creator',
      role: 'user',
      created_at: new Date().toISOString(),
    };
    this.users.set(demoUser.id, demoUser);

    const demoSettings: UserSettings = {
      user_id: demoUser.id,
      preferences: {
        default_source_lang: 'auto',
        default_target_lang: 'vi',
        export_preset: 'Balanced',
        export_bitrate_kbps: 2500,
        theme: 'dark',
        density: 'comfortable',
        preferred_device_id: 'dev_local_pc',
      },
      sync: {
        sync_subtitles_enabled: false, // Default false per spec WEB-25
        sync_metadata_enabled: true,
        last_synced_at: new Date().toISOString(),
      },
      local_storage_path: 'D:\\VIUStudio_Projects',
      cache_quota_gb: 50,
    };
    this.settings.set(demoUser.id, demoSettings);

    const demoDevice: DeviceCapability = {
      device_id: 'dev_local_pc',
      name: 'My PC',
      protocol_version: '1.0',
      companion_version: '2.4.1',
      ready_state: 'Ready',
      last_seen_at: new Date().toISOString(),
      hardware: {
        os: 'Windows 11 Pro 64-bit',
        cpu_name: 'AMD Ryzen 7 5800X 8-Core Processor',
        cpu_cores: 16,
        gpu_name: 'NVIDIA GeForce RTX 3070 (8GB)',
        has_gpu_acceleration: true,
        total_memory_bytes: 32 * 1024 * 1024 * 1024,
        available_memory_bytes: 18 * 1024 * 1024 * 1024,
        available_disk_bytes: 240 * 1024 * 1024 * 1024,
      },
      engines: ['piper', 'zerotts', 'kokoro', 'whisper', 'demucs', 'ffmpeg'],
      languages: ['vi', 'en', 'auto'],
      encoders: ['h264_nvenc', 'libx264', 'hevc_nvenc'],
      supported_actions: ['transcribe', 'tts', 'separation', 'export', 'prepare'],
      active_jobs_count: 0,
    };
    this.devices.set(demoDevice.device_id, demoDevice);

    const demoProject: Project = {
      id: 'prj_demo_sample',
      owner_id: demoUser.id,
      name: 'Sample Recap Video',
      revision: 3,
      generation: 1,
      device_id: demoDevice.device_id,
      device_name: 'My PC',
      languages: { source_lang: 'auto', target_lang: 'vi' },
      goal: 'Subtitles + voice',
      duration_ms: 68400,
      sync_status: 'Saved locally',
      tracks: [
        { id: 'trk_v1', name: 'V1 Video', kind: 'video', volume: 1.0, muted: false, solo: false, locked: false },
        { id: 'trk_a1', name: 'Original Audio', kind: 'original_audio', volume: 0.8, muted: false, solo: false, locked: false },
        { id: 'trk_dub', name: 'Dub Voice', kind: 'dub', volume: 1.2, muted: false, solo: false, locked: false },
        { id: 'trk_music', name: 'Music Stem', kind: 'music', volume: 0.5, muted: false, solo: false, locked: false },
        { id: 'trk_sub', name: 'Subtitles', kind: 'subtitles', volume: 1.0, muted: false, solo: false, locked: false },
      ],
      audio_mix: {
        preset: 'Dialogue Focused',
        voice_volume: 1.2,
        music_volume: 0.4,
        original_volume: 0.2,
      },
      export_settings: {
        output_name: 'Sample_Recap_Video_Export.mp4',
        resolution: '1080p',
        fps: 30,
        preset: 'Balanced',
        video_bitrate_kbps: 2500,
        bitrate_mode: 'Auto',
        burn_subtitles: true,
        audio_tracks: ['trk_dub', 'trk_music'],
      },
      created_at: new Date(Date.now() - 3600000 * 24).toISOString(),
      updated_at: new Date(Date.now() - 3600000 * 2).toISOString(),
    };
    this.projects.set(demoProject.id, demoProject);

    const sampleCues: CueItem[] = [
      {
        id: 'cue_1_1000',
        project_id: demoProject.id,
        index: 1,
        start_ms: 1000,
        end_ms: 4500,
        original_text: 'Welcome back to our channel. Today we explore the latest discoveries.',
        translated_text: 'Chào mừng các bạn đã quay trở lại kênh. Hôm nay chúng ta sẽ khám phá những phát hiện mới nhất.',
        audio_status: 'Ready',
        speaker_id: 'Narrator',
        voice_config_hash: 'piper_vi_female',
      },
      {
        id: 'cue_2_5000',
        project_id: demoProject.id,
        index: 2,
        start_ms: 5000,
        end_ms: 9200,
        original_text: 'In the deep ocean, scientists found mysterious glowing creatures.',
        translated_text: 'Dưới lòng đại dương sâu thẳm, các nhà khoa học đã tìm thấy những sinh vật phát sáng kỳ bí.',
        audio_status: 'Ready',
        speaker_id: 'Narrator',
        voice_config_hash: 'piper_vi_female',
      },
      {
        id: 'cue_3_9800',
        project_id: demoProject.id,
        index: 3,
        start_ms: 9800,
        end_ms: 14200,
        original_text: 'Let us take a closer look at how their bioluminescence actually works.',
        translated_text: 'Hãy cùng tìm hiểu kỹ hơn về cách hiện tượng phát quang sinh học của chúng hoạt động.',
        audio_status: 'Ready',
        speaker_id: 'Narrator',
        voice_config_hash: 'piper_vi_female',
      },
    ];
    this.cues.set(demoProject.id, sampleCues);

    const sampleResources: ModelResource[] = [
      {
        id: 'piper_vi_vivos',
        name: 'Piper [VN] · Fast (VIVOS)',
        category: 'tts',
        engine: 'piper',
        languages: ['VN'],
        description: 'Ultra-fast lightweight neural TTS for Vietnamese.',
        download_size_bytes: 65 * 1024 * 1024,
        installed_size_bytes: 70 * 1024 * 1024,
        status: 'Ready',
        is_integrated: true,
      },
      {
        id: 'zerotts_vn',
        name: 'ZeroTTS [VN] · Natural',
        category: 'tts',
        engine: 'zerotts',
        languages: ['VN'],
        description: 'High-fidelity natural Vietnamese voice synthesis.',
        download_size_bytes: 420 * 1024 * 1024,
        installed_size_bytes: 450 * 1024 * 1024,
        status: 'Not installed',
        is_integrated: true,
      },
      {
        id: 'kokoro_en_82m',
        name: 'Kokoro-82M [EN] · Natural',
        category: 'tts',
        engine: 'kokoro',
        languages: ['EN'],
        description: 'Compact, natural English voice model.',
        download_size_bytes: 82 * 1024 * 1024,
        installed_size_bytes: 90 * 1024 * 1024,
        status: 'Ready',
        is_integrated: true,
      },
      {
        id: 'whisper_large_v3',
        name: 'Whisper Large v3 (Multilingual)',
        category: 'speech_recognition',
        engine: 'whisper',
        languages: ['VN', 'EN', 'Auto'],
        description: 'State-of-the-art multilingual speech transcription.',
        download_size_bytes: 1500 * 1024 * 1024,
        installed_size_bytes: 1600 * 1024 * 1024,
        status: 'Ready',
        is_integrated: true,
      },
      {
        id: 'demucs_htdemucs',
        name: 'Demucs HTDemucs 4-Stem',
        category: 'separation',
        engine: 'demucs',
        languages: [],
        description: 'Audio source separation for Voice and Music stems.',
        download_size_bytes: 180 * 1024 * 1024,
        installed_size_bytes: 200 * 1024 * 1024,
        status: 'Ready',
        is_integrated: true,
      },
      {
        id: 'korvatts_future',
        name: 'KorvaTTS Expressive',
        category: 'tts',
        engine: 'korvatts',
        languages: ['VN'],
        description: 'Expressive Vietnamese speech synthesis.',
        status: 'Coming soon',
        is_integrated: false,
      },
    ];
    this.resources.set(demoDevice.device_id, sampleResources);
  }
}

export const memoryStore = new MemoryStore();

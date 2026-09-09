export type AudioStatus = 'Missing' | 'Generating' | 'Ready' | 'Outdated' | 'Failed';

export interface CueItem {
  id: string;
  project_id: string;
  index: number;
  start_ms: number;
  end_ms: number;
  original_text: string;
  translated_text: string;
  speaker_id?: string;
  voice_config_hash?: string;
  audio_status: AudioStatus;
  audio_url?: string;
  audio_duration_ms?: number;
  cps_warning?: boolean;
}

export type AssetKind = 'video' | 'audio_source' | 'dub' | 'music_stem' | 'voice_stem' | 'proxy' | 'export';
export type AssetAvailability = 'Stored on this device' | 'Available on remote device' | 'Missing' | 'Downloading';

export interface Asset {
  id: string;
  project_id: string;
  device_id: string;
  kind: AssetKind;
  file_name: string;
  fingerprint?: string;
  duration_ms?: number;
  size_bytes?: number;
  availability: AssetAvailability;
  local_path?: string;
  created_at: string;
}

export interface TrackSettings {
  id: string;
  name: string;
  kind: 'video' | 'original_audio' | 'dub' | 'music' | 'subtitles';
  volume: number; // 0.0 to 2.0 (1.0 = 100%)
  muted: boolean;
  solo: boolean;
  locked: boolean;
}

export interface AudioMixSettings {
  preset: 'Default' | 'Dialogue Focused' | 'Background Music' | 'Custom';
  voice_volume: number;
  music_volume: number;
  original_volume: number;
}

export interface ExportSettings {
  output_name: string;
  resolution: '1080p' | '720p' | '4k' | 'source';
  fps: number;
  preset: 'Fast' | 'Balanced' | 'Maximum quality';
  video_bitrate_kbps: number;
  bitrate_mode: 'Auto' | 'Custom';
  burn_subtitles: boolean;
  audio_tracks: string[];
}

export interface ProjectLanguages {
  source_lang: string; // 'auto', 'vi', 'en', etc.
  target_lang: string; // 'vi', 'en', etc.
}

export type ProjectGoal = 'Transcript only' | 'Translated subtitles' | 'Subtitles + voice' | 'Voice only';

export interface Project {
  id: string;
  owner_id: string;
  name: string;
  revision: number;
  generation: number;
  device_id: string;
  device_name?: string;
  languages: ProjectLanguages;
  goal: ProjectGoal;
  tracks: TrackSettings[];
  audio_mix: AudioMixSettings;
  export_settings?: ExportSettings;
  duration_ms: number;
  sync_status: 'Saved locally' | 'Synced' | 'Draft saved in browser';
  is_archived?: boolean;
  created_at: string;
  updated_at: string;
}

export interface SyncSettings {
  sync_subtitles_enabled: boolean; // MUST default to false for privacy
  sync_metadata_enabled: boolean;
  last_synced_at?: string;
}

export interface UserPreferences {
  default_source_lang: string;
  default_target_lang: string;
  export_preset: 'Fast' | 'Balanced' | 'Maximum quality';
  export_bitrate_kbps: number;
  theme: 'dark' | 'system';
  density: 'comfortable' | 'compact';
  preferred_device_id?: string;
}

export interface UserSettings {
  user_id: string;
  preferences: UserPreferences;
  sync: SyncSettings;
  local_storage_path?: string;
  cache_quota_gb?: number;
}

export interface UserProfile {
  id: string;
  email: string;
  name: string;
  avatar_url?: string;
  role: 'user' | 'admin';
  created_at: string;
}

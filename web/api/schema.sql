-- VIUStudio Cloudflare D1 SQLite Schema
-- Multi-tenant schema with owner_id scoping for all user data

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    avatar_url TEXT,
    role TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id TEXT PRIMARY KEY,
    preferences_json TEXT NOT NULL,
    sync_subtitles_enabled INTEGER NOT NULL DEFAULT 0, -- PRIVACY: default 0 (OFF) per Section 3 & WEB-25
    sync_metadata_enabled INTEGER NOT NULL DEFAULT 1,
    local_storage_path TEXT,
    cache_quota_gb REAL DEFAULT 50.0,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    name TEXT NOT NULL,
    os TEXT NOT NULL,
    protocol_version TEXT NOT NULL,
    companion_version TEXT NOT NULL,
    ready_state TEXT NOT NULL DEFAULT 'Offline', -- 'Ready', 'Busy', 'Offline'
    hardware_json TEXT,
    engines_json TEXT,
    languages_json TEXT,
    encoders_json TEXT,
    last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pairing_codes (
    code TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    device_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    name TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    generation INTEGER NOT NULL DEFAULT 1,
    device_id TEXT NOT NULL,
    source_lang TEXT NOT NULL DEFAULT 'auto',
    target_lang TEXT NOT NULL DEFAULT 'vi',
    goal TEXT NOT NULL DEFAULT 'Subtitles + voice',
    tracks_json TEXT,
    audio_mix_json TEXT,
    export_settings_json TEXT,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    sync_status TEXT NOT NULL DEFAULT 'Synced',
    is_archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cues (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    cue_index INTEGER NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    original_text TEXT NOT NULL,
    translated_text TEXT NOT NULL DEFAULT '',
    speaker_id TEXT,
    voice_config_hash TEXT,
    audio_status TEXT NOT NULL DEFAULT 'Missing',
    audio_duration_ms INTEGER,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cues_project ON cues(project_id, cue_index);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    project_id TEXT,
    device_id TEXT NOT NULL,
    type TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 1,
    input_revision INTEGER,
    state TEXT NOT NULL DEFAULT 'Queued',
    progress_json TEXT,
    error_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_jobs_owner ON jobs(owner_id, state);
CREATE INDEX IF NOT EXISTS idx_jobs_device ON jobs(device_id, state);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    project_id TEXT,
    device_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    file_name TEXT NOT NULL,
    size_bytes INTEGER,
    duration_ms INTEGER,
    availability TEXT NOT NULL DEFAULT 'Stored on this device',
    local_path TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

import { Project, CueItem, ProjectGoal } from '../types/project.js';
import { DeviceCapability, PairingRequest } from '../types/device.js';
import { Job, ProgressEvent } from '../types/job.js';
import { ModelResource } from '../types/resource.js';
import { UserProfile, UserSettings } from '../types/user.js';

export interface ApiResponse<T = unknown> {
  ok: boolean;
  data?: T;
  error?: string;
  error_code?: string;
}

// Auth
export interface SignInRequest {
  provider: 'google' | 'demo';
  token?: string;
  email?: string;
  name?: string;
}

export interface SessionResponse {
  user: UserProfile;
  settings: UserSettings;
  token: string;
}

// Device Pairing
export interface CreatePairingCodeResponse {
  code: string;
  expires_at: string;
}

export interface ConfirmPairingRequest {
  code: string;
  device_id: string;
  device_name: string;
  protocol_version: string;
  companion_version: string;
  hardware: DeviceCapability['hardware'];
  engines: string[];
  languages: string[];
  encoders: string[];
}

export interface DeviceHeartbeatRequest {
  device_id: string;
  ready_state: 'Ready' | 'Busy';
  active_jobs_count: number;
  available_disk_bytes?: number;
  available_memory_bytes?: number;
}

// Projects
export interface CreateProjectRequest {
  name: string;
  device_id: string;
  source_lang: string;
  target_lang: string;
  goal: ProjectGoal;
}

export interface UpdateProjectRequest {
  name?: string;
  goal?: ProjectGoal;
  device_id?: string;
  languages?: { source_lang: string; target_lang: string };
  tracks?: Project['tracks'];
  audio_mix?: Project['audio_mix'];
  export_settings?: Project['export_settings'];
}

export interface SyncCuesRequest {
  project_id: string;
  base_revision: number;
  mutation_id: string;
  cues: CueItem[];
}

export interface SyncCuesResponse {
  new_revision: number;
  cues: CueItem[];
}

// Jobs
export interface CreateJobRequest {
  project_id?: string;
  device_id: string;
  type: Job['type'];
  params?: Record<string, unknown>;
  input_revision?: number;
}

export interface ReportJobProgressRequest {
  job_id: string;
  attempt: number;
  sequence: number;
  stage: string;
  current: number;
  total: number;
  unit: string;
  message: string;
  speed?: string;
  eta_seconds?: number;
}

export interface CompleteJobRequest {
  job_id: string;
  artifacts?: Job['artifacts'];
}

export interface FailJobRequest {
  job_id: string;
  code: string;
  message: string;
  stage?: string;
  details?: string;
}

// Resources
export interface ListResourcesResponse {
  device_id: string;
  resources: ModelResource[];
}

export interface InstallResourceRequest {
  resource_id: string;
  device_id: string;
}

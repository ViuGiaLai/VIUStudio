export type JobState =
  | 'Queued'
  | 'Waiting for device'
  | 'Preparing'
  | 'Running'
  | 'Finalizing'
  | 'Completed'
  | 'Failed'
  | 'Cancelling'
  | 'Cancelled'
  | 'Interrupted';

export type JobType =
  | 'transcribe'
  | 'tts'
  | 'separation'
  | 'export'
  | 'model_download'
  | 'prepare'
  | 'proxy';

export interface ProgressEvent {
  job_id: string;
  attempt: number;
  sequence: number;
  stage: string;
  current: number;
  total: number;
  unit: string; // e.g., 'cues', 'bytes', 'seconds', 'percent'
  message: string;
  timestamp: string;
  speed?: string;
  eta_seconds?: number;
}

export interface Artifact {
  id: string;
  job_id: string;
  project_id?: string;
  project_revision?: number;
  kind: string; // e.g. 'wav', 'mp4', 'srt', 'vtt'
  file_name: string;
  device_id: string;
  availability: 'Stored on this device' | 'Available on remote device' | 'Missing';
  size_bytes?: number;
  duration_ms?: number;
  local_path?: string;
  download_url?: string;
  created_at: string;
}

export interface Job {
  id: string;
  owner_id: string;
  project_id?: string;
  project_name?: string;
  device_id: string;
  device_name?: string;
  type: JobType;
  attempt: number;
  input_revision?: number;
  state: JobState;
  progress?: ProgressEvent;
  error?: {
    code: string;
    message: string;
    stage?: string;
    details?: string;
  };
  artifacts?: Artifact[];
  created_at: string;
  updated_at: string;
}

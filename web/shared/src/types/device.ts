export type DeviceReadyState = 'Ready' | 'Busy' | 'Offline';

export interface HardwareSpecs {
  os: string;
  cpu_name: string;
  cpu_cores: number;
  gpu_name?: string;
  has_gpu_acceleration: boolean;
  total_memory_bytes?: number;
  available_memory_bytes?: number;
  available_disk_bytes?: number;
}

export interface DeviceCapability {
  device_id: string;
  name: string;
  protocol_version: string;
  companion_version: string;
  ready_state: DeviceReadyState;
  last_seen_at: string;
  hardware: HardwareSpecs;
  engines: string[]; // e.g. ['piper', 'zerotts', 'kokoro', 'whisper', 'demucs', 'ffmpeg']
  languages: string[]; // e.g. ['vi', 'en', 'auto']
  encoders: string[]; // e.g. ['h264_nvenc', 'libx264', 'hevc_nvenc']
  supported_actions: string[];
  active_jobs_count: number;
}

export interface PairingRequest {
  code: string;
  expires_at: string;
  owner_id: string;
  device_id?: string;
  device_name?: string;
  status: 'pending' | 'paired' | 'expired' | 'revoked';
  created_at: string;
}

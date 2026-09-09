export type ResourceCategory = 'speech_recognition' | 'tts' | 'separation' | 'video_utilities';

export type ResourceStatus =
  | 'Not installed'
  | 'Runtime installed, model missing'
  | 'Downloading'
  | 'Installing'
  | 'Verifying'
  | 'Ready'
  | 'Failed'
  | 'Incompatible'
  | 'Coming soon';

export interface ModelResource {
  id: string;
  name: string;
  category: ResourceCategory;
  engine: string;
  languages: string[]; // e.g. ['VN', 'EN']
  description: string;
  download_size_bytes?: number;
  installed_size_bytes?: number;
  status: ResourceStatus;
  progress_percent?: number;
  download_speed?: string;
  is_integrated: boolean;
  required_gpu?: boolean;
  error_message?: string;
  preview_audio_url?: string;
}

export interface VoiceOption {
  id: string;
  name: string;
  engine: string;
  language: string;
  gender: 'male' | 'female' | 'neutral';
  quality: 'Fast' | 'Natural' | 'High Quality';
  status: ResourceStatus;
  preview_url?: string;
}

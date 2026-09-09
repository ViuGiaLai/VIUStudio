import {
  Project,
  CueItem,
  DeviceCapability,
  Job,
  ModelResource,
  UserProfile,
  UserSettings,
  CreatePairingCodeResponse,
  ConfirmPairingRequest,
  CreateProjectRequest,
  UpdateProjectRequest,
  CreateJobRequest,
  ApiResponse,
} from '@viustudio/shared';

const API_BASE = '/api';

class ApiClient {
  private token: string | null = null;

  setToken(t: string) {
    this.token = t;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const headers = new Headers(options.headers || {});
    if (this.token) headers.set('Authorization', `Bearer ${this.token}`);
    headers.set('Content-Type', 'application/json');

    try {
      const res = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers,
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.error || `HTTP ${res.status}`);
      }

      const json = (await res.json()) as ApiResponse<T>;
      if (!json.ok && json.error) {
        throw new Error(json.error);
      }
      return json.data as T;
    } catch (err: any) {
      console.warn(`[ApiClient] Request to ${endpoint} failed:`, err.message);
      throw err;
    }
  }

  // Auth
  async getSession(): Promise<{ user: UserProfile; settings: UserSettings; token: string }> {
    return this.request('/auth/session');
  }

  async updateSettings(settings: Partial<UserSettings>): Promise<UserSettings> {
    return this.request('/auth/settings', {
      method: 'PUT',
      body: JSON.stringify(settings),
    });
  }

  // Devices
  async getDevices(): Promise<DeviceCapability[]> {
    return this.request('/devices');
  }

  async createPairingCode(): Promise<CreatePairingCodeResponse> {
    return this.request('/devices/pairing-code', { method: 'POST' });
  }

  async confirmPairing(data: ConfirmPairingRequest): Promise<DeviceCapability> {
    return this.request('/devices/pair-confirm', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async renameDevice(deviceId: string, name: string): Promise<DeviceCapability> {
    return this.request(`/devices/${deviceId}/rename`, {
      method: 'PUT',
      body: JSON.stringify({ name }),
    });
  }

  async disconnectDevice(deviceId: string): Promise<void> {
    await this.request(`/devices/${deviceId}`, { method: 'DELETE' });
  }

  // Projects
  async getProjects(): Promise<Project[]> {
    return this.request('/projects');
  }

  async getProject(id: string): Promise<Project & { cues: CueItem[] }> {
    return this.request(`/projects/${id}`);
  }

  async createProject(req: CreateProjectRequest): Promise<Project> {
    return this.request('/projects', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  }

  async updateProject(id: string, req: UpdateProjectRequest): Promise<Project> {
    return this.request(`/projects/${id}`, {
      method: 'PUT',
      body: JSON.stringify(req),
    });
  }

  async duplicateProject(id: string): Promise<Project> {
    return this.request(`/projects/${id}/duplicate`, { method: 'POST' });
  }

  async deleteProject(id: string): Promise<void> {
    await this.request(`/projects/${id}`, { method: 'DELETE' });
  }

  // Cues sync
  async syncCues(projectId: string, baseRevision: number, cues: CueItem[]): Promise<{ new_revision: number; cues: CueItem[] }> {
    return this.request('/sync/cues', {
      method: 'POST',
      body: JSON.stringify({
        project_id: projectId,
        base_revision: baseRevision,
        mutation_id: `mut_${Date.now()}`,
        cues,
      }),
    });
  }

  // Jobs
  async getJobs(status?: 'active' | 'completed' | 'failed'): Promise<Job[]> {
    const q = status ? `?status=${status}` : '';
    return this.request(`/jobs${q}`);
  }

  async getJob(id: string): Promise<Job> {
    return this.request(`/jobs/${id}`);
  }

  async createJob(req: CreateJobRequest): Promise<Job> {
    return this.request('/jobs', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  }

  async cancelJob(id: string): Promise<Job> {
    return this.request(`/jobs/${id}/cancel`, { method: 'POST' });
  }

  // Resources
  async getResources(deviceId?: string): Promise<ModelResource[]> {
    const q = deviceId ? `?device_id=${deviceId}` : '';
    return this.request(`/resources${q}`);
  }

  async installResource(deviceId: string, resourceId: string): Promise<ModelResource> {
    return this.request('/resources/install', {
      method: 'POST',
      body: JSON.stringify({ device_id: deviceId, resource_id: resourceId }),
    });
  }
}

export const api = new ApiClient();

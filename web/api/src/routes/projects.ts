import { Hono } from 'hono';
import { memoryStore } from '../db/index.js';
import {
  Project,
  CueItem,
  CreateProjectRequest,
  UpdateProjectRequest,
} from '@viustudio/shared';

const projects = new Hono();

// List user projects
projects.get('/', async (c) => {
  const userId = c.get('userId');
  const userProjects = Array.from(memoryStore.projects.values()).filter(
    (p) => p.owner_id === userId
  );
  return c.json({ ok: true, data: userProjects });
});

// Create project
projects.post('/', async (c) => {
  const userId = c.get('userId');
  const body = (await c.req.json().catch(() => ({}))) as CreateProjectRequest;

  if (!body.name) {
    return c.json({ ok: false, error: 'Project name is required' }, 400);
  }

  const device = memoryStore.devices.get(body.device_id) || Array.from(memoryStore.devices.values())[0];
  const deviceId = device ? device.device_id : 'dev_local_pc';
  const deviceName = device ? device.name : 'My PC';

  const newProject: Project = {
    id: `prj_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
    owner_id: userId,
    name: body.name,
    revision: 1,
    generation: 1,
    device_id: deviceId,
    device_name: deviceName,
    languages: {
      source_lang: body.source_lang || 'auto',
      target_lang: body.target_lang || 'vi',
    },
    goal: body.goal || 'Subtitles + voice',
    duration_ms: 0,
    sync_status: 'Saved locally',
    tracks: [
      { id: 'trk_v1', name: 'V1 Video', kind: 'video', volume: 1.0, muted: false, solo: false, locked: false },
      { id: 'trk_a1', name: 'Original Audio', kind: 'original_audio', volume: 1.0, muted: false, solo: false, locked: false },
      { id: 'trk_dub', name: 'Dub Voice', kind: 'dub', volume: 1.0, muted: false, solo: false, locked: false },
      { id: 'trk_music', name: 'Music Stem', kind: 'music', volume: 0.5, muted: false, solo: false, locked: false },
      { id: 'trk_sub', name: 'Subtitles', kind: 'subtitles', volume: 1.0, muted: false, solo: false, locked: false },
    ],
    audio_mix: {
      preset: 'Default',
      voice_volume: 1.0,
      music_volume: 0.5,
      original_volume: 0.8,
    },
    export_settings: {
      output_name: `${body.name.replace(/\s+/g, '_')}_Export.mp4`,
      resolution: '1080p',
      fps: 30,
      preset: 'Balanced',
      video_bitrate_kbps: 2500,
      bitrate_mode: 'Auto',
      burn_subtitles: true,
      audio_tracks: ['trk_dub', 'trk_music'],
    },
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };

  memoryStore.projects.set(newProject.id, newProject);
  memoryStore.cues.set(newProject.id, []);

  return c.json({ ok: true, data: newProject }, 201);
});

// Get single project (WEB-01: multi-tenant check)
projects.get('/:id', async (c) => {
  const userId = c.get('userId');
  const projectId = c.req.param('id');
  const project = memoryStore.projects.get(projectId);

  if (!project || project.owner_id !== userId) {
    // WEB-01: reject, no metadata leak
    return c.json({ ok: false, error: 'Project not found' }, 404);
  }

  const cues = memoryStore.cues.get(projectId) || [];
  return c.json({
    ok: true,
    data: {
      ...project,
      cues,
    },
  });
});

// Update project
projects.put('/:id', async (c) => {
  const userId = c.get('userId');
  const projectId = c.req.param('id');
  const project = memoryStore.projects.get(projectId);

  if (!project || project.owner_id !== userId) {
    return c.json({ ok: false, error: 'Project not found' }, 404);
  }

  const body = (await c.req.json().catch(() => ({}))) as UpdateProjectRequest;

  project.name = body.name ?? project.name;
  project.goal = body.goal ?? project.goal;
  project.device_id = body.device_id ?? project.device_id;
  if (body.languages) {
    project.languages = body.languages;
  }
  if (body.tracks) {
    project.tracks = body.tracks;
  }
  if (body.audio_mix) {
    project.audio_mix = body.audio_mix;
  }
  if (body.export_settings) {
    project.export_settings = body.export_settings;
  }

  project.revision += 1;
  project.updated_at = new Date().toISOString();

  return c.json({ ok: true, data: project });
});

// Duplicate project (Section 8.1: clones config & references without copying big files)
projects.post('/:id/duplicate', async (c) => {
  const userId = c.get('userId');
  const projectId = c.req.param('id');
  const source = memoryStore.projects.get(projectId);

  if (!source || source.owner_id !== userId) {
    return c.json({ ok: false, error: 'Project not found' }, 404);
  }

  const duplicatedId = `prj_${Date.now()}_copy`;
  const duplicated: Project = {
    ...JSON.parse(JSON.stringify(source)),
    id: duplicatedId,
    name: `${source.name} (Copy)`,
    revision: 1,
    generation: 1,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };

  memoryStore.projects.set(duplicatedId, duplicated);
  const sourceCues = memoryStore.cues.get(projectId) || [];
  const clonedCues: CueItem[] = sourceCues.map((c) => ({
    ...c,
    id: `${c.id}_copy`,
    project_id: duplicatedId,
  }));
  memoryStore.cues.set(duplicatedId, clonedCues);

  return c.json({ ok: true, data: duplicated }, 201);
});

// Delete project
projects.delete('/:id', async (c) => {
  const userId = c.get('userId');
  const projectId = c.req.param('id');
  const project = memoryStore.projects.get(projectId);

  if (!project || project.owner_id !== userId) {
    return c.json({ ok: false, error: 'Project not found' }, 404);
  }

  memoryStore.projects.delete(projectId);
  memoryStore.cues.delete(projectId);
  return c.json({ ok: true });
});

export default projects;

import { Hono } from 'hono';
import { memoryStore } from '../db/index.js';
import { SyncCuesRequest, SyncCuesResponse } from '@viustudio/shared';

const sync = new Hono();

// Sync cues for a project
sync.post('/cues', async (c) => {
  const userId = c.get('userId');
  const body = (await c.req.json().catch(() => ({}))) as SyncCuesRequest;

  const project = memoryStore.projects.get(body.project_id);
  if (!project || project.owner_id !== userId) {
    return c.json({ ok: false, error: 'Project not found' }, 404);
  }

  const userSettings = memoryStore.settings.get(userId);
  const isSubtitleSyncEnabled = userSettings?.sync.sync_subtitles_enabled ?? false;

  // WEB-25: If subtitle text sync is off, cloud must NOT store transcript/translation text
  if (!isSubtitleSyncEnabled) {
    // Return with warning / metadata sync only
    return c.json({
      ok: false,
      error: 'Subtitle text sync across devices is disabled in user privacy settings.',
      error_code: 'SUBTITLE_SYNC_DISABLED',
    }, 403);
  }

  // Revision conflict check (Section 16.1)
  if (body.base_revision < project.revision) {
    return c.json({
      ok: false,
      error: 'This project changed on another session.',
      error_code: 'REVISION_CONFLICT',
      current_revision: project.revision,
    }, 409);
  }

  // Apply new cues
  project.revision += 1;
  project.updated_at = new Date().toISOString();
  project.sync_status = 'Synced';

  memoryStore.cues.set(project.id, body.cues);

  const response: SyncCuesResponse = {
    new_revision: project.revision,
    cues: body.cues,
  };

  return c.json({ ok: true, data: response });
});

export default sync;

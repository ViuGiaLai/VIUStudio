import { Hono } from 'hono';
import { memoryStore } from '../db/index.js';
import { InstallResourceRequest } from '@viustudio/shared';

const resources = new Hono();

// List resources for device
resources.get('/', async (c) => {
  const deviceId = c.req.query('device_id') || 'dev_local_pc';
  const list = memoryStore.resources.get(deviceId) || memoryStore.resources.get('dev_local_pc') || [];
  return c.json({ ok: true, data: list });
});

// Trigger install/download
resources.post('/install', async (c) => {
  const body = (await c.req.json().catch(() => ({}))) as InstallResourceRequest;
  const list = memoryStore.resources.get(body.device_id) || memoryStore.resources.get('dev_local_pc') || [];
  const target = list.find((r) => r.id === body.resource_id);

  if (!target) {
    return c.json({ ok: false, error: 'Resource not found' }, 404);
  }

  if (!target.is_integrated) {
    return c.json({ ok: false, error: 'Resource engine integration is coming soon' }, 400);
  }

  target.status = 'Installing';
  target.progress_percent = 50;

  return c.json({ ok: true, data: target });
});

export default resources;

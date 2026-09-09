import { Hono } from 'hono';
import { memoryStore } from '../db/index.js';
import { SignInRequest, SessionResponse, ApiResponse } from '@viustudio/shared';

const auth = new Hono();

auth.post('/sign-in', async (c) => {
  const body = (await c.req.json().catch(() => ({}))) as SignInRequest;
  const user = memoryStore.users.get('usr_demo_123')!;
  const settings = memoryStore.settings.get(user.id)!;

  const response: ApiResponse<SessionResponse> = {
    ok: true,
    data: {
      user,
      settings,
      token: user.id,
    },
  };
  return c.json(response);
});

auth.get('/session', async (c) => {
  const userId = c.get('userId');
  const user = memoryStore.users.get(userId);
  const settings = memoryStore.settings.get(userId);

  if (!user || !settings) {
    return c.json({ ok: false, error: 'Session expired' }, 401);
  }

  return c.json({
    ok: true,
    data: {
      user,
      settings,
      token: user.id,
    },
  });
});

auth.put('/settings', async (c) => {
  const userId = c.get('userId');
  const body = await c.req.json().catch(() => ({}));
  const existing = memoryStore.settings.get(userId);

  if (!existing) {
    return c.json({ ok: false, error: 'User settings not found' }, 404);
  }

  const updated = {
    ...existing,
    preferences: { ...existing.preferences, ...body.preferences },
    sync: { ...existing.sync, ...body.sync },
    local_storage_path: body.local_storage_path ?? existing.local_storage_path,
  };

  memoryStore.settings.set(userId, updated);
  return c.json({ ok: true, data: updated });
});

export default auth;

import { Context, Next } from 'hono';
import { memoryStore } from '../db/index.js';
import { UserProfile } from '@viustudio/shared';

declare module 'hono' {
  interface ContextVariableMap {
    user: UserProfile;
    userId: string;
  }
}

export async function authMiddleware(c: Context, next: Next) {
  const authHeader = c.req.header('Authorization');

  // Support demo token or Bearer token
  let token = 'usr_demo_123';
  if (authHeader && authHeader.startsWith('Bearer ')) {
    token = authHeader.substring(7).trim();
  }

  // Look up user
  let user = memoryStore.users.get(token);
  if (!user) {
    // If not found, use default demo user or create session user
    user = memoryStore.users.get('usr_demo_123');
  }

  if (!user) {
    return c.json({ ok: false, error: 'Unauthorized', error_code: 'UNAUTHORIZED' }, 401);
  }

  c.set('user', user);
  c.set('userId', user.id);

  await next();
}

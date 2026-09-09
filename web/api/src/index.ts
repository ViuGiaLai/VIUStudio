import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { logger } from 'hono/logger';
import { authMiddleware } from './middleware/auth.js';
import authRoutes from './routes/auth.js';
import devicesRoutes from './routes/devices.js';
import projectsRoutes from './routes/projects.js';
import jobsRoutes from './routes/jobs.js';
import resourcesRoutes from './routes/resources.js';
import syncRoutes from './routes/sync.js';

const app = new Hono();

// Middlewares
app.use('*', logger());
app.use(
  '*',
  cors({
    origin: '*',
    allowMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allowHeaders: ['Content-Type', 'Authorization', 'X-Requested-With'],
  })
);

// Health check
app.get('/health', (c) => {
  return c.json({
    ok: true,
    service: 'viustudio-api',
    status: 'healthy',
    timestamp: new Date().toISOString(),
  });
});

// Mount routes with authentication
const api = new Hono();
api.use('*', authMiddleware);

api.route('/auth', authRoutes);
api.route('/devices', devicesRoutes);
api.route('/projects', projectsRoutes);
api.route('/jobs', jobsRoutes);
api.route('/resources', resourcesRoutes);
api.route('/sync', syncRoutes);

app.route('/api', api);

// 404 handler
app.notFound((c) => {
  return c.json({ ok: false, error: 'Route not found' }, 404);
});

// Error handler
app.onError((err, c) => {
  console.error('API Error:', err);
  return c.json({ ok: false, error: err.message || 'Internal Server Error' }, 500);
});

export default app;

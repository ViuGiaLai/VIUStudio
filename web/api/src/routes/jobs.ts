import { Hono } from 'hono';
import { memoryStore } from '../db/index.js';
import {
  Job,
  CreateJobRequest,
  ReportJobProgressRequest,
  CompleteJobRequest,
  FailJobRequest,
} from '@viustudio/shared';

const jobs = new Hono();

// List user jobs
jobs.get('/', async (c) => {
  const userId = c.get('userId');
  const statusFilter = c.req.query('status'); // 'active' | 'completed' | 'failed'

  let userJobs = Array.from(memoryStore.jobs.values()).filter(
    (j) => j.owner_id === userId
  );

  if (statusFilter === 'active') {
    userJobs = userJobs.filter((j) =>
      ['Queued', 'Waiting for device', 'Preparing', 'Running', 'Finalizing', 'Cancelling'].includes(
        j.state
      )
    );
  } else if (statusFilter === 'completed') {
    userJobs = userJobs.filter((j) => j.state === 'Completed');
  } else if (statusFilter === 'failed') {
    userJobs = userJobs.filter((j) => ['Failed', 'Cancelled', 'Interrupted'].includes(j.state));
  }

  // Sort by updated_at descending
  userJobs.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());

  return c.json({ ok: true, data: userJobs });
});

// Create job (WEB-19: idempotency protection)
jobs.post('/', async (c) => {
  const userId = c.get('userId');
  const body = (await c.req.json().catch(() => ({}))) as CreateJobRequest;

  if (!body.type || !body.device_id) {
    return c.json({ ok: false, error: 'Job type and device_id are required' }, 400);
  }

  // Check if identical active job already exists (WEB-19)
  const existingActive = Array.from(memoryStore.jobs.values()).find(
    (j) =>
      j.owner_id === userId &&
      j.project_id === body.project_id &&
      j.type === body.type &&
      ['Queued', 'Waiting for device', 'Preparing', 'Running'].includes(j.state)
  );

  if (existingActive) {
    return c.json({
      ok: true,
      data: existingActive,
      message: 'Active job already exists for this task.',
    });
  }

  const project = body.project_id ? memoryStore.projects.get(body.project_id) : undefined;
  const device = memoryStore.devices.get(body.device_id);

  const newJob: Job = {
    id: `job_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
    owner_id: userId,
    project_id: body.project_id,
    project_name: project?.name,
    device_id: body.device_id,
    device_name: device?.name || 'My PC',
    type: body.type,
    attempt: 1,
    input_revision: body.input_revision ?? project?.revision,
    state: 'Queued',
    progress: {
      job_id: '',
      attempt: 1,
      sequence: 0,
      stage: 'Queued',
      current: 0,
      total: 100,
      unit: '%',
      message: 'Waiting for device to accept task...',
      timestamp: new Date().toISOString(),
    },
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };

  newJob.progress!.job_id = newJob.id;
  memoryStore.jobs.set(newJob.id, newJob);

  return c.json({ ok: true, data: newJob }, 201);
});

// Get single job detail (WEB-01: multi-tenant check)
jobs.get('/:id', async (c) => {
  const userId = c.get('userId');
  const jobId = c.req.param('id');
  const job = memoryStore.jobs.get(jobId);

  if (!job || job.owner_id !== userId) {
    // WEB-01: reject without leaking info
    return c.json({ ok: false, error: 'Job not found' }, 404);
  }

  return c.json({ ok: true, data: job });
});

// Progress update from Companion
jobs.post('/:id/progress', async (c) => {
  const jobId = c.req.param('id');
  const job = memoryStore.jobs.get(jobId);
  if (!job) {
    return c.json({ ok: false, error: 'Job not found' }, 404);
  }

  const body = (await c.req.json().catch(() => ({}))) as ReportJobProgressRequest;

  // Enforce monotonic sequence numbers
  if (job.progress && body.sequence < job.progress.sequence) {
    return c.json({ ok: false, error: 'Outdated progress sequence' }, 400);
  }

  job.state = 'Running';
  job.progress = {
    job_id: jobId,
    attempt: body.attempt,
    sequence: body.sequence,
    stage: body.stage,
    current: body.current,
    total: body.total,
    unit: body.unit,
    message: body.message,
    speed: body.speed,
    eta_seconds: body.eta_seconds,
    timestamp: new Date().toISOString(),
  };
  job.updated_at = new Date().toISOString();

  return c.json({ ok: true, data: job });
});

// Complete job
jobs.post('/:id/complete', async (c) => {
  const jobId = c.req.param('id');
  const job = memoryStore.jobs.get(jobId);
  if (!job) {
    return c.json({ ok: false, error: 'Job not found' }, 404);
  }

  const body = (await c.req.json().catch(() => ({}))) as CompleteJobRequest;
  job.state = 'Completed';
  job.artifacts = body.artifacts || [];
  if (job.progress) {
    job.progress.stage = 'Completed';
    job.progress.current = job.progress.total;
    job.progress.message = '✓ Task completed successfully';
  }
  job.updated_at = new Date().toISOString();

  return c.json({ ok: true, data: job });
});

// Cancel job
jobs.post('/:id/cancel', async (c) => {
  const userId = c.get('userId');
  const jobId = c.req.param('id');
  const job = memoryStore.jobs.get(jobId);

  if (!job || job.owner_id !== userId) {
    return c.json({ ok: false, error: 'Job not found' }, 404);
  }

  job.state = 'Cancelled';
  if (job.progress) {
    job.progress.stage = 'Cancelled';
    job.progress.message = 'Task cancelled by user';
  }
  job.updated_at = new Date().toISOString();

  return c.json({ ok: true, data: job });
});

export default jobs;

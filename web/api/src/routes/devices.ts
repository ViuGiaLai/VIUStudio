import { Hono } from 'hono';
import { memoryStore } from '../db/index.js';
import {
  CreatePairingCodeResponse,
  ConfirmPairingRequest,
  DeviceHeartbeatRequest,
  DeviceCapability,
} from '@viustudio/shared';

const devices = new Hono();

// List user devices
devices.get('/', async (c) => {
  const all = Array.from(memoryStore.devices.values());
  return c.json({ ok: true, data: all });
});

// Generate 6-digit pairing code (valid for 10 minutes)
devices.post('/pairing-code', async (c) => {
  const userId = c.get('userId');
  // Generate random 6-digit code
  const code = Math.floor(100000 + Math.random() * 900000).toString();
  const expiresAt = new Date(Date.now() + 10 * 60 * 1000).toISOString();

  memoryStore.pairingCodes.set(code, {
    code,
    owner_id: userId,
    expires_at: expiresAt,
  });

  const response: CreatePairingCodeResponse = {
    code,
    expires_at: expiresAt,
  };
  return c.json({ ok: true, data: response });
});

// Companion confirms pairing
devices.post('/pair-confirm', async (c) => {
  const body = (await c.req.json().catch(() => ({}))) as ConfirmPairingRequest;
  const pairing = memoryStore.pairingCodes.get(body.code);

  if (!pairing) {
    return c.json({ ok: false, error: 'Invalid pairing code' }, 400);
  }

  if (new Date(pairing.expires_at).getTime() < Date.now()) {
    return c.json({ ok: false, error: 'Pairing code expired' }, 400);
  }

  const newDevice: DeviceCapability = {
    device_id: body.device_id,
    name: body.device_name || 'My PC',
    protocol_version: body.protocol_version || '1.0',
    companion_version: body.companion_version || '1.0.0',
    ready_state: 'Ready',
    last_seen_at: new Date().toISOString(),
    hardware: body.hardware || {
      os: 'Windows 11',
      cpu_name: 'Standard CPU',
      cpu_cores: 8,
      has_gpu_acceleration: false,
    },
    engines: body.engines || ['piper'],
    languages: body.languages || ['vi', 'en'],
    encoders: body.encoders || ['libx264'],
    supported_actions: ['transcribe', 'tts', 'export'],
    active_jobs_count: 0,
  };

  memoryStore.devices.set(newDevice.device_id, newDevice);
  pairing.used_at = new Date().toISOString();
  pairing.device_id = newDevice.device_id;

  return c.json({ ok: true, data: newDevice });
});

// Heartbeat
devices.post('/heartbeat', async (c) => {
  const body = (await c.req.json().catch(() => ({}))) as DeviceHeartbeatRequest;
  const dev = memoryStore.devices.get(body.device_id);
  if (!dev) {
    return c.json({ ok: false, error: 'Device not found' }, 404);
  }

  dev.ready_state = body.ready_state || 'Ready';
  dev.active_jobs_count = body.active_jobs_count ?? dev.active_jobs_count;
  dev.last_seen_at = new Date().toISOString();
  if (body.available_disk_bytes !== undefined) {
    dev.hardware.available_disk_bytes = body.available_disk_bytes;
  }
  if (body.available_memory_bytes !== undefined) {
    dev.hardware.available_memory_bytes = body.available_memory_bytes;
  }

  return c.json({ ok: true });
});

// Rename
devices.put('/:id/rename', async (c) => {
  const deviceId = c.req.param('id');
  const body = await c.req.json().catch(() => ({}));
  const dev = memoryStore.devices.get(deviceId);
  if (!dev) {
    return c.json({ ok: false, error: 'Device not found' }, 404);
  }
  if (body.name) {
    dev.name = body.name;
  }
  return c.json({ ok: true, data: dev });
});

// Disconnect
devices.delete('/:id', async (c) => {
  const deviceId = c.req.param('id');
  memoryStore.devices.delete(deviceId);
  return c.json({ ok: true });
});

export default devices;

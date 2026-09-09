/**
 * Real Hardware & Companion Detection Service
 * Reads authentic browser and system capabilities via WebGL, Web APIs,
 * and actively probes the local Python Companion Daemon on port 8765.
 */

export type ClientPlatform =
  | 'desktop_companion'    // PC connected to Companion (has real C/D/E filesystem access)
  | 'desktop_browser'      // PC on web browser without companion (WASM + Browser Cache)
  | 'mobile_browser';      // Smartphone / Tablet (Touch, limited tab RAM, Browser Cache only)

export interface BrowserStorageInfo {
  usageBytes: number;
  quotaBytes: number;
  usageMb: number;
  quotaMb: number;
  isSupported: boolean;
}

export interface RealHardwareInfo {
  os: string;
  cpu_name: string;
  cpu_cores: number;
  gpu_name: string;
  has_gpu_acceleration: boolean;
  total_memory_bytes: number;
  wasm_supported: boolean;
  audio_supported: boolean;
  is_mobile: boolean;
  recommended_tier: 'mobile' | 'pc' | 'workstation';
  platform?: ClientPlatform;
}

export interface CompanionStatus {
  online: boolean;
  service?: string;
  profile?: string;
  ping_ms?: number;
  error?: string;
  timestamp: string;
}

export function getClientPlatform(is_mobile: boolean, companionOnline: boolean): ClientPlatform {
  if (is_mobile) return 'mobile_browser';
  if (companionOnline) return 'desktop_companion';
  return 'desktop_browser';
}

/**
 * Estimate real browser storage quota & current usage
 */
export async function getBrowserStorageEstimate(): Promise<BrowserStorageInfo> {
  if (typeof navigator !== 'undefined' && navigator.storage && navigator.storage.estimate) {
    try {
      const estimate = await navigator.storage.estimate();
      const usageBytes = estimate.usage || 0;
      const quotaBytes = estimate.quota || 0;
      return {
        usageBytes,
        quotaBytes,
        usageMb: Math.round(usageBytes / (1024 * 1024)),
        quotaMb: Math.round(quotaBytes / (1024 * 1024)),
        isSupported: true,
      };
    } catch {
      // ignore
    }
  }
  return {
    usageBytes: 0,
    quotaBytes: 0,
    usageMb: 0,
    quotaMb: 0,
    isSupported: false,
  };
}

/**
 * Clear genuine browser caches and IndexedDB storage (freeing real browser disk space)
 */
export async function clearRealBrowserStorage(): Promise<{ clearedCaches: number; clearedIndexedDb: boolean }> {
  // Only remove downloaded Piper models. Never erase project databases or auth caches.
  const tts = await import('@mintplex-labs/piper-tts-web');
  const models = await tts.stored();
  await tts.flush();
  return { clearedCaches: models.length, clearedIndexedDb: false };
}

/**
 * Detect real hardware capabilities from the user's browser environment
 */
export function detectRealClientHardware(): RealHardwareInfo {
  const userAgent = navigator.userAgent || '';
  const is_mobile =
    /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(userAgent) ||
    (typeof window !== 'undefined' && window.innerWidth <= 768);

  let os = 'Windows';
  if (/iPhone|iPad|iPod/i.test(userAgent)) {
    os = 'iOS';
  } else if (/Android/i.test(userAgent)) {
    os = 'Android';
  } else if (userAgent.includes('Macintosh') || userAgent.includes('Mac OS')) {
    os = 'macOS';
  } else if (userAgent.includes('Linux')) {
    os = 'Linux';
  } else if (userAgent.includes('Windows NT 10.0')) {
    os = 'Windows 11 / 10';
  }

  const cpu_cores = navigator.hardwareConcurrency || 1;
  const memoryGb = (navigator as any).deviceMemory || 0;
  const total_memory_bytes = memoryGb * 1024 * 1024 * 1024;

  let gpu_name = 'Trình duyệt không cung cấp thông tin GPU';
  let webglAvailable = false;

  try {
    const canvas = document.createElement('canvas');
    const gl =
      (canvas.getContext('webgl') as WebGLRenderingContext | null) ||
      (canvas.getContext('experimental-webgl') as WebGLRenderingContext | null);

    if (gl) {
      webglAvailable = true;
      const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
      if (debugInfo) {
        const unmaskedRenderer = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL);
        if (unmaskedRenderer && typeof unmaskedRenderer === 'string') {
          const renderer = unmaskedRenderer
            .replace(/^ANGLE \(/, '')
            .replace(/\)$/, '')
            .replace(/Direct3D.*$/, '')
            .replace(/vs_.*$/, '')
            .trim();
          gpu_name = /basic render|swiftshader|software/i.test(renderer)
            ? 'Kết xuất phần mềm của trình duyệt'
            : renderer || gpu_name;
        }
      }
    }
  } catch {
    webglAvailable = false;
  }

  const wasm_supported = typeof WebAssembly === 'object' && typeof WebAssembly.instantiate === 'function';
  const audio_supported = typeof window.AudioContext !== 'undefined' || typeof (window as any).webkitAudioContext !== 'undefined';

  let recommended_tier: 'mobile' | 'pc' | 'workstation' = 'pc';
  if (is_mobile) {
    recommended_tier = 'mobile';
  } else if (webglAvailable && cpu_cores >= 8) {
    recommended_tier = 'workstation';
  }

  return {
    os,
    cpu_name: `${cpu_cores} luồng xử lý trình duyệt`,
    cpu_cores,
    gpu_name,
    // WebGL only proves graphics rendering. It does not prove CUDA/DirectML AI support.
    has_gpu_acceleration: false,
    total_memory_bytes,
    wasm_supported,
    audio_supported,
    is_mobile,
    recommended_tier,
    platform: is_mobile ? 'mobile_browser' : 'desktop_browser',
  };
}

/**
 * Actively probe local Companion daemon on port 8765
 */
export async function probeCompanionDaemon(): Promise<CompanionStatus> {
  const start = performance.now();
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 1800);

    const res = await fetch('/companion/health', {
      method: 'GET',
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    const elapsed = Math.round(performance.now() - start);

    const contentType = res.headers.get('content-type') || '';
    if (res.ok && contentType.includes('application/json')) {
      const data = await res.json();
      const isCompanion = data?.status === 'ok' || data?.healthy === true || typeof data?.service === 'string';
      if (!isCompanion) {
        return {
          online: false,
          error: 'Phản hồi không phải từ VIUStudio Companion',
          ping_ms: elapsed,
          timestamp: new Date().toISOString(),
        };
      }
      return {
        online: true,
        service: data.service || 'viustudio-remote-api',
        profile: data.profile || 'local',
        ping_ms: Math.max(1, elapsed),
        timestamp: new Date().toISOString(),
      };
    }

    return {
      online: false,
      error: contentType.includes('text/html') ? 'Companion chưa được cấu hình trên máy này' : `HTTP ${res.status}`,
      ping_ms: elapsed,
      timestamp: new Date().toISOString(),
    };
  } catch (err: any) {
    return {
      online: false,
      error: err.name === 'AbortError' ? 'Hết thời gian chờ (1.8s)' : 'Chưa bật Companion daemon',
      timestamp: new Date().toISOString(),
    };
  }
}

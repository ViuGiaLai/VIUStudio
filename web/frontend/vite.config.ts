import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { createReadStream, readFileSync } from 'node:fs';

const ortFiles = ['ort-wasm-simd-threaded.wasm', 'ort-wasm-simd-threaded.mjs'];
const ortDist = path.resolve(__dirname, '../node_modules/onnxruntime-web/dist');

const localOrtAssets = () => ({
  name: 'viustudio-ort-assets',
  configureServer(server: { middlewares: { use: (route: string, handler: (request: { url?: string }, response: { statusCode: number; setHeader: (name: string, value: string) => void; end: () => void }) => void) => void } }) {
    server.middlewares.use('/ort', (request, response) => {
      const filename = path.basename(request.url || '');
      if (!ortFiles.includes(filename)) {
        response.statusCode = 404;
        response.end();
        return;
      }
      response.setHeader('Content-Type', filename.endsWith('.wasm') ? 'application/wasm' : 'text/javascript; charset=utf-8');
      createReadStream(path.join(ortDist, filename)).pipe(response as never);
    });
  },
  generateBundle(this: { emitFile: (asset: { type: 'asset'; fileName: string; source: Buffer }) => void }) {
    for (const filename of ortFiles) {
      this.emitFile({ type: 'asset', fileName: `ort/${filename}`, source: readFileSync(path.join(ortDist, filename)) });
    }
  },
});

export default defineConfig({
  plugins: [react(), localOrtAssets()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('@supabase') || id.includes('/node_modules/ws/')) return 'supabase';
          if (id.includes('react') || id.includes('scheduler')) return 'react-vendor';
          return undefined;
        },
      },
    },
  },
  worker: {
    format: 'es',
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@viustudio/shared': path.resolve(__dirname, '../shared/src/index.ts'),
    },
  },
  server: {
    port: 3000,
    host: '127.0.0.1',
    headers: {
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
    },
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8787',
        changeOrigin: true,
      },
      '/companion': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/companion/, ''),
      },
    },
  },
  preview: {
    headers: {
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
    },
  },
});

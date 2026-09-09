# VIUStudio Web

> Multi-user web application and Cloudflare Workers API for VIUStudio, operating in tandem with the local **VIUStudio Companion** desktop worker.

Based strictly on the specification in [docs/web-ui-specification.md](../docs/web-ui-specification.md).

---

## Directory Structure

```
web/
├── frontend/  # React + TypeScript + Vite + Tailwind CSS (App Shell, Editor, Tools Hub)
├── api/       # Cloudflare Workers backend (Hono, D1 SQLite migrations, Multi-tenant)
└── shared/    # Common TypeScript types, API contracts, SRT parser & validation
```

---

## Core Architecture Principles

1. **Local Media & Privacy (Section 3)**:
   - Video, audio stems, and AI models remain strictly on the user's computer.
   - Cloudflare Workers only store user profiles, device registrations, project metadata, and job state queues.
   - Video files are **never** uploaded to the cloud by default.

2. **Subtitle Text Synchronization Opt-In (Section 3 & WEB-25)**:
   - `Sync subtitle text across devices` is an explicit user preference, defaulted to **OFF**.
   - When off, other sessions only see project metadata and statuses without loading sensitive text.

3. **Standalone SRT Subtitle Editor (Section 9.1 & WEB-03)**:
   - Operates 100% inside the browser without requiring Companion or desktop backend.
   - Includes full cue table, timing adjustments, search & replace, split/merge, character-per-second warning, and UTF-8 SRT export.

4. **Browser SRT → TTS → MP3**:
   - Open `/app/srt-tts`, import an SRT, choose a Vietnamese or US English Piper voice, then create MP3.
   - The source video is not required. Silence and speech are written at the original SRT timestamps, so the MP3 can be placed at `00:00` in CapCut.
   - Piper loads only when this page is opened. Voice models are downloaded once and cached in the browser's private file system.
   - MP3 is encoded incrementally in the browser to keep memory stable for long subtitle files. The API/VPS does not synthesize or receive the subtitle text.
   - Production hosting must preserve the COOP/COEP headers in `frontend/public/_headers`; these enable threaded WebAssembly.

---

## Quick Start

### 1. Install Dependencies
From the `web/` root directory:
```bash
npm install
```

### 2. Build Shared Library
```bash
npm run build:shared
```

### 3. Run Frontend (Vite)
```bash
npm run dev:frontend
```
Frontend will be available at `http://127.0.0.1:3000`.

### 4. Run API Worker (Cloudflare Wrangler)
```bash
npm run dev:api
```
Worker API runs locally at `http://127.0.0.1:8787`.

---

## Verification & Typecheck

```bash
npm run typecheck
npm run build
```

# Supabase setup for VIUStudio Web

The frontend is already configured with the project's public URL and publishable key. To enable cloud accounts, finish these two server-side steps in the Supabase dashboard:

1. Open **SQL Editor** and run `migrations/20260909_auth_and_workspace.sql` once.
2. Open **Authentication → Providers → Google**, enable Google, and add the Google OAuth client ID and secret.

Add these redirect URLs under **Authentication → URL Configuration**:

- `https://138-2-109-17.sslip.io/**`
- `http://127.0.0.1:3000/**`

Security model:

- Every cloud table has Row Level Security enabled.
- Policies restrict rows to `auth.uid()`.
- Video and generated audio are not uploaded to Supabase.
- Project metadata, subtitle cues, and user settings are synchronized only for authenticated users.
- The public SRT → TTS → MP3 tool does not query private workspace tables.

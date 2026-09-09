import type { User } from '@supabase/supabase-js';
import type { CueItem, Project, UserProfile, UserSettings } from '@viustudio/shared';
import { assertGoogleProviderEnabled, requireSupabase, supabase } from '../lib/supabase';

type ProjectRow = {
  id: string;
  owner_id: string;
  project: Project;
  cues: CueItem[] | null;
};

const isMissingTable = (message?: string) =>
  Boolean(message && /(relation .* does not exist|schema cache|could not find the table)/i.test(message));

export function profileFromAuthUser(authUser: User): UserProfile {
  const metadata = authUser.user_metadata || {};
  return {
    id: authUser.id,
    email: authUser.email || '',
    name: metadata.full_name || metadata.name || authUser.email?.split('@')[0] || 'Người dùng',
    avatar_url: metadata.avatar_url || metadata.picture,
    role: 'user',
    created_at: authUser.created_at,
  };
}

export async function signInWithGoogle() {
  await assertGoogleProviderEnabled();
  const client = requireSupabase();
  const { error } = await client.auth.signInWithOAuth({
    provider: 'google',
    options: { redirectTo: `${window.location.origin}/app` },
  });
  if (error) throw error;
}

export async function signOutCloud() {
  if (!supabase) return;
  const { error } = await supabase.auth.signOut();
  if (error) throw error;
}

export async function loadCloudWorkspace(ownerId: string) {
  const client = requireSupabase();
  const [projectResult, settingsResult] = await Promise.all([
    client.from('projects').select('id, owner_id, project, cues').eq('owner_id', ownerId).order('updated_at', { ascending: false }),
    client.from('user_settings').select('settings').eq('user_id', ownerId).maybeSingle(),
  ]);

  const error = projectResult.error || settingsResult.error;
  if (error) {
    if (isMissingTable(error.message)) {
      throw new Error('Cơ sở dữ liệu chưa được khởi tạo. Hãy chạy file migration Supabase của VIUStudio.');
    }
    throw error;
  }

  const rows = (projectResult.data || []) as ProjectRow[];
  return {
    projects: rows.map((row) => ({ ...row.project, id: row.id, owner_id: row.owner_id })),
    cues: Object.fromEntries(rows.filter((row) => row.cues !== null).map((row) => [row.id, row.cues])) as Record<string, CueItem[]>,
    settings: (settingsResult.data?.settings || null) as UserSettings | null,
  };
}

export async function saveCloudProject(project: Project, cues: CueItem[], syncSubtitles = false) {
  const client = requireSupabase();
  const { cues: _privateCues, ...metadata } = project as Project & { cues?: CueItem[] };
  const { error } = await client.from('projects').upsert({
    id: project.id,
    owner_id: project.owner_id,
    name: project.name,
    project: metadata,
    cues: syncSubtitles ? cues : null,
    updated_at: new Date().toISOString(),
  });
  if (error) throw error;
}

export async function deleteCloudProject(projectId: string) {
  const client = requireSupabase();
  const { error } = await client.from('projects').delete().eq('id', projectId);
  if (error) throw error;
}

export async function saveCloudSettings(settings: UserSettings) {
  const client = requireSupabase();
  if (!settings.sync.sync_subtitles_enabled) {
    const existing = await client.from('projects').select('id, project').eq('owner_id', settings.user_id);
    if (existing.error) throw existing.error;
    for (const row of existing.data || []) {
      const { cues: _privateCues, ...metadata } = row.project || {};
      const cleared = await client.from('projects').update({ project: metadata, cues: null }).eq('id', row.id).eq('owner_id', settings.user_id);
      if (cleared.error) throw cleared.error;
    }
  }
  const { error } = await client.from('user_settings').upsert({
    user_id: settings.user_id,
    settings,
    updated_at: new Date().toISOString(),
  });
  if (error) throw error;
}

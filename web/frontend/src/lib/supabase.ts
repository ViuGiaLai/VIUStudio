import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL?.trim();
const supabaseKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY?.trim();

export const supabaseConfigured = Boolean(supabaseUrl && supabaseKey);

export const supabase = supabaseConfigured
  ? createClient(supabaseUrl, supabaseKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    })
  : null;

export function requireSupabase() {
  if (!supabase) {
    throw new Error('Supabase chưa được cấu hình cho bản web này.');
  }
  return supabase;
}

export async function assertGoogleProviderEnabled() {
  if (!supabaseConfigured) throw new Error('Supabase chưa được cấu hình cho bản web này.');
  const response = await fetch(`${supabaseUrl}/auth/v1/settings`, {
    headers: { apikey: supabaseKey },
  });
  if (!response.ok) throw new Error('Không thể kiểm tra cấu hình đăng nhập lúc này.');
  const settings = await response.json();
  if (!settings?.external?.google) {
    throw new Error('Đăng nhập Google chưa được quản trị viên bật trong Supabase. Bạn vẫn có thể dùng Voice Studio miễn phí.');
  }
}

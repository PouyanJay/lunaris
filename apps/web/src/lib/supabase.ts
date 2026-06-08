import { createClient, type SupabaseClient } from "@supabase/supabase-js";

/** The Supabase browser client, or null when auth is not configured (offline/dev without login).
 *
 *  Present only when BOTH `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` are set at build time.
 *  Null disables the login gate so local dev against the API still works without a Supabase project. */
const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

export const supabase: SupabaseClient | null = url && anonKey ? createClient(url, anonKey) : null;

/** The current user's access token (JWT) for `Authorization: Bearer`, or null when not signed in. */
export async function getAccessToken(): Promise<string | null> {
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

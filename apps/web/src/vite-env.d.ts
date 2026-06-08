/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the Lunaris API (e.g. http://localhost:8000). Unset → use the static seed. */
  readonly VITE_API_URL?: string;
  /** Topic to generate when running against the API. */
  readonly VITE_COURSE_TOPIC?: string;
  /** Supabase project URL. Set together with the anon key to require end-user login (multi-tenant). */
  readonly VITE_SUPABASE_URL?: string;
  /** Supabase anon (publishable) key — safe to ship in the client; auth is enforced server-side. */
  readonly VITE_SUPABASE_ANON_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

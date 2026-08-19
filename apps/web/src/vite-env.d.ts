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
  /** "true" offers Lunaris Live (the gateway, the product switcher, the /live route-space). Unset
   *  or anything else keeps Lunaris as Studio alone — the default until Live's Phase 2 exit. */
  readonly VITE_LIVE_ENABLED?: string;
  /** Base URL of Lunaris Live's CopilotKit runtime (e.g. http://localhost:8100). A separate host
   *  from `VITE_API_URL` because it is a separate service: Node, not Python. Unset → the generative
   *  session surface is unavailable and Live falls back to P2a's plain transcript, which still
   *  works because the REST endpoints it uses never went away. */
  readonly VITE_COPILOT_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the Lunaris API (e.g. http://localhost:8000). Unset → use the static seed. */
  readonly VITE_API_URL?: string;
  /** Topic to generate when running against the API. */
  readonly VITE_COURSE_TOPIC?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

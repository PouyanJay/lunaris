import { authedFetch } from "./apiClient";
/** Config API client. Unlike secrets, these values ARE shown — we read them back and edit them. */

export type ConfigKind = "toggle" | "text" | "model" | "number";

export interface ConfigSetting {
  name: string;
  value: string;
  default: string;
  kind: ConfigKind;
  /** True when the value is read at process start (langsmith) — a change needs a restart. */
  restartRequired: boolean;
}

// The explainer-video config keys (V6). The Video section owns these; the generic Runtime
// configuration panel filters them out so they render once, in their own three-layer disclosure.
export const VIDEO_MASTER_KEY = "videoEnabled";
// A sub-toggle of the master: off ⇒ a build makes only the two course-level videos, no per-lesson ones.
export const VIDEO_LESSONS_KEY = "videoLessonsEnabled";
export const VIDEO_VOICE_KEY = "videoVoice";
export const VIDEO_LENGTH_KEYS = [
  "videoSummarySeconds",
  "videoOverviewSeconds",
  "videoLessonSeconds",
] as const;
export const VIDEO_CONFIG_KEYS: ReadonlySet<string> = new Set<string>([
  VIDEO_MASTER_KEY,
  VIDEO_LESSONS_KEY,
  VIDEO_VOICE_KEY,
  ...VIDEO_LENGTH_KEYS,
]);

/** The wire value for a toggle setting — the one place the boolean ⇄ "true"/"false" mapping lives. */
export const boolToConfigValue = (on: boolean): string => (on ? "true" : "false");

export class ConfigError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "ConfigError";
  }
}

async function request(input: string, init?: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await authedFetch(input, init);
  } catch (cause) {
    throw new ConfigError("Could not reach the configuration service.", { cause });
  }
  if (!response.ok) {
    const detail = await response
      .json()
      .then((body: { detail?: string }) => body?.detail)
      .catch(() => undefined);
    throw new ConfigError(detail ?? `Configuration request failed (HTTP ${response.status}).`);
  }
  return response.json();
}

export function fetchConfig(apiBaseUrl: string, signal?: AbortSignal): Promise<ConfigSetting[]> {
  return request(`${apiBaseUrl}/api/config`, signal ? { signal } : undefined).then(
    (body) => (body as { settings: ConfigSetting[] }).settings,
  );
}

/** Persist one config value; resolves to its updated setting (rejects ConfigError on a bad value). */
export function updateConfig(
  apiBaseUrl: string,
  name: string,
  value: string,
): Promise<ConfigSetting> {
  return request(`${apiBaseUrl}/api/config/${name}`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ value }),
  }) as Promise<ConfigSetting>;
}

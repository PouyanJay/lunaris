import { authedFetch } from "./apiClient";
/** Config API client. Unlike secrets, these values ARE shown — we read them back and edit them. */

export type ConfigKind = "toggle" | "text" | "model";

export interface ConfigSetting {
  name: string;
  value: string;
  default: string;
  kind: ConfigKind;
  /** True when the value is read at process start (langsmith) — a change needs a restart. */
  restartRequired: boolean;
}

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

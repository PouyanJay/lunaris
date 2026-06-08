import { authedFetch } from "./apiClient";
/** Settings API client. Secrets are write-only: we send values but only ever read back
 *  status (set/unset + last4) — the value never comes back over the wire. */

export interface SecretStatus {
  name: string;
  isSet: boolean;
  last4: string | null;
}

export interface SettingsView {
  secrets: SecretStatus[];
  pipeline: string;
  /** Whether the active pipeline can re-author a single lesson. The reader hides the regenerate
   *  action when false (the deep-agent pipeline doesn't support it and would 501). */
  supportsLessonRegeneration: boolean;
  /** Whether plain-language "Explain" is available (an Anthropic key is reachable). The transcript
   *  hides the Explain affordance when false rather than offering a button that 503s. */
  supportsExplain: boolean;
  /** Whether per-user BYOK is configured. When true the Keys panel manages the tenant's own keys
   *  via the authed /api/credentials surface; when false it uses the file-backed secret store. */
  byokEnabled: boolean;
}

export class SettingsError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "SettingsError";
  }
}

async function request(input: string, init?: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await authedFetch(input, init);
  } catch (cause) {
    throw new SettingsError("Could not reach the settings service.", { cause });
  }
  if (!response.ok) {
    // The API returns {detail: "..."} for validation/400s — surface it to guide the fix.
    const detail = await response
      .json()
      .then((body: { detail?: string }) => body?.detail)
      .catch(() => undefined);
    throw new SettingsError(detail ?? `Settings request failed (HTTP ${response.status}).`);
  }
  return response.json();
}

export function fetchSettings(apiBaseUrl: string, signal?: AbortSignal): Promise<SettingsView> {
  return request(
    `${apiBaseUrl}/api/settings`,
    signal ? { signal } : undefined,
  ) as Promise<SettingsView>;
}

/** Validate + store a secret. Resolves to its new status; rejects (SettingsError) if the key
 *  was rejected by validation, with the backend's message. */
export function saveSecret(apiBaseUrl: string, name: string, value: string): Promise<SecretStatus> {
  return request(`${apiBaseUrl}/api/settings/secrets/${name}`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ value }),
  }) as Promise<SecretStatus>;
}

export function clearSecret(apiBaseUrl: string, name: string): Promise<SecretStatus> {
  return request(`${apiBaseUrl}/api/settings/secrets/${name}`, {
    method: "DELETE",
  }) as Promise<SecretStatus>;
}

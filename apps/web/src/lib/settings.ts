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
    response = await fetch(input, init);
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

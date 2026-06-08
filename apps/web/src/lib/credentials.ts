import { authedFetch } from "./apiClient";

/** BYOK credentials API client (Phase 2). Per-user provider keys are write-only: we send values
 *  but only ever read back status (set/unset + last4) — the value never comes back over the wire.
 *  Every call is authed via `authedFetch`; the server scopes to the signed-in user. */

export interface CredentialStatus {
  provider: string;
  isSet: boolean;
  last4: string | null;
}

/** The result of probing a key without storing it (the "Test" action). */
export interface CredentialTestResult {
  ok: boolean;
  detail: string | null;
}

export class CredentialError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "CredentialError";
  }
}

async function request(input: string, init?: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await authedFetch(input, init);
  } catch (cause) {
    throw new CredentialError("Could not reach the key service.", { cause });
  }
  if (!response.ok) {
    // The API returns {detail: "..."} for 400/404/503 — surface it to guide the fix.
    const detail = await response
      .json()
      .then((body: { detail?: string }) => body?.detail)
      .catch(() => undefined);
    throw new CredentialError(detail ?? `Key request failed (HTTP ${response.status}).`);
  }
  return response.json();
}

export function fetchCredentials(
  apiBaseUrl: string,
  signal?: AbortSignal,
): Promise<CredentialStatus[]> {
  return request(`${apiBaseUrl}/api/credentials`, signal ? { signal } : undefined) as Promise<
    CredentialStatus[]
  >;
}

/** Store (or rotate) a provider key. Resolves to its new masked status; rejects (CredentialError)
 *  with the backend's message if the key is empty/invalid or the provider rejects it. */
export function saveCredential(
  apiBaseUrl: string,
  provider: string,
  value: string,
): Promise<CredentialStatus> {
  return request(`${apiBaseUrl}/api/credentials/${provider}`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ value }),
  }) as Promise<CredentialStatus>;
}

export function deleteCredential(apiBaseUrl: string, provider: string): Promise<CredentialStatus> {
  return request(`${apiBaseUrl}/api/credentials/${provider}`, {
    method: "DELETE",
  }) as Promise<CredentialStatus>;
}

/** Probe a key's validity without storing it. Resolves to {ok, detail} (ok=false is a normal
 *  result, not an error); rejects only on a malformed request or transport failure. */
export function testCredential(
  apiBaseUrl: string,
  provider: string,
  value: string,
): Promise<CredentialTestResult> {
  return request(`${apiBaseUrl}/api/credentials/${provider}/test`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ value }),
  }) as Promise<CredentialTestResult>;
}

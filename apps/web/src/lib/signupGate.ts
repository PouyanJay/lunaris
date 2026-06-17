import { authedFetch } from "./apiClient";

/** Public, pre-login status of the signup gate — whether an invitation code is required. */
export interface SignupGateStatus {
  enforced: boolean;
}

/** The admin view of the gate: the plaintext shared code, the enforced flag, and when it changed. */
export interface SignupGate {
  inviteCode: string;
  enforced: boolean;
  updatedAt: string | null;
}

/** A change to the gate — rotate the code, toggle enforcement, or both. Omitted fields are kept. */
export interface SignupGateUpdate {
  inviteCode?: string;
  enforced?: boolean;
}

export class SignupGateError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "SignupGateError";
  }
}

type Fetcher = (input: string, init?: RequestInit) => Promise<Response>;

async function request(
  input: string,
  init?: RequestInit,
  fetcher: Fetcher = authedFetch,
): Promise<unknown> {
  let response: Response;
  try {
    response = await fetcher(input, init);
  } catch (cause) {
    throw new SignupGateError("Could not reach the invitation service.", { cause });
  }
  if (!response.ok) {
    const detail = await response
      .json()
      .then((body: { detail?: string }) => body?.detail)
      .catch(() => undefined);
    throw new SignupGateError(detail ?? `Invitation request failed (HTTP ${response.status}).`);
  }
  return response.json();
}

/** Public: whether the sign-up form must collect an invitation code. Runs pre-login, so it uses a
 *  plain `fetch` (no bearer token to attach) rather than the authenticated client. */
export function fetchSignupGateStatus(
  apiBaseUrl: string,
  signal?: AbortSignal,
): Promise<SignupGateStatus> {
  return request(
    `${apiBaseUrl}/api/signup-gate`,
    signal ? { signal } : undefined,
    (input, init) => fetch(input, init),
  ) as Promise<SignupGateStatus>;
}

/** Admin: read the current shared code + enforced flag. 403 unless the caller is an admin. */
export function fetchSignupGate(apiBaseUrl: string, signal?: AbortSignal): Promise<SignupGate> {
  return request(
    `${apiBaseUrl}/api/admin/signup-gate`,
    signal ? { signal } : undefined,
  ) as Promise<SignupGate>;
}

/** Admin: rotate the code and/or toggle enforcement. Resolves to the updated gate. */
export function updateSignupGate(
  apiBaseUrl: string,
  update: SignupGateUpdate,
): Promise<SignupGate> {
  return request(`${apiBaseUrl}/api/admin/signup-gate`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(update),
  }) as Promise<SignupGate>;
}

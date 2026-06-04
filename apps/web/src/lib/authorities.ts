import type { SourceAuthority, SubjectField } from "../types/course";

/** A failure reaching or using the trust-config API (network or non-OK response). */
export class AuthoritiesError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "AuthoritiesError";
  }
}

/** List the trust-config rows (GET /api/source-authorities). */
export async function fetchAuthorities(
  apiBaseUrl: string,
  signal?: AbortSignal,
): Promise<SourceAuthority[]> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/api/source-authorities`, signal ? { signal } : undefined);
  } catch (cause) {
    throw new AuthoritiesError("Could not reach the trust-config service.", { cause });
  }
  if (!response.ok) {
    throw new AuthoritiesError(`Couldn't load trusted sources (HTTP ${response.status}).`);
  }
  return response.json() as Promise<SourceAuthority[]>;
}

/** Add or replace a trust-config row (PUT /api/source-authorities); identity is (domain, field). */
export async function upsertAuthority(
  apiBaseUrl: string,
  authority: SourceAuthority,
): Promise<SourceAuthority> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/api/source-authorities`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(authority),
    });
  } catch (cause) {
    throw new AuthoritiesError("Could not reach the trust-config service.", { cause });
  }
  if (response.status === 422) {
    throw new AuthoritiesError("That entry isn't valid (a pack needs a field; others must not).");
  }
  if (!response.ok) {
    throw new AuthoritiesError(`Couldn't save the entry (HTTP ${response.status}).`);
  }
  return response.json() as Promise<SourceAuthority>;
}

/** Remove a trust-config row by its (domain, field) key (DELETE /api/source-authorities). */
export async function deleteAuthority(
  apiBaseUrl: string,
  domain: string,
  field: SubjectField | null,
): Promise<void> {
  const query = new URLSearchParams({ domain });
  if (field !== null) query.set("field", field);
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/api/source-authorities?${query}`, { method: "DELETE" });
  } catch (cause) {
    throw new AuthoritiesError("Could not reach the trust-config service.", { cause });
  }
  if (!response.ok) {
    throw new AuthoritiesError(`Couldn't remove the entry (HTTP ${response.status}).`);
  }
}

import { getAccessToken, supabase } from "./supabase";

/** `fetch` that attaches the signed-in user's bearer token, so every API call is authenticated.
 *
 *  The single choke point for auth on the API: all `lib/*` request helpers go through it. When auth
 *  is not configured (no Supabase client) it delegates to `fetch` synchronously — identical timing
 *  and behaviour to a bare call, so anonymous/offline use and tests are unaffected. When configured,
 *  it resolves the current token and adds `Authorization: Bearer <jwt>`; the server decides access
 *  (200 on public routes, 401 on protected ones). Existing headers, body, and `signal` are preserved. */
export function authedFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  if (!supabase) return fetch(input, init);
  return getAccessToken().then((token) => {
    const headers = new Headers(init.headers);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    return fetch(input, { ...init, headers });
  });
}

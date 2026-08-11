/** How the browser addresses Lunaris Live's CopilotKit runtime.
 *
 *  Its own module rather than sitting beside the component: these two are a contract between
 *  deployables — the Node service decides the mount path and reads the session header — and the
 *  contract is worth testing without rendering anything.
 */

/** The header the Node runtime reads to decide whose session a run belongs to. */
export const SESSION_HEADER = "x-lunaris-session-id";

/** Which agent the runtime exposes. One, because there is one loop. */
export const LIVE_AGENT = "live";

/** Where the runtime answers, from the host an operator configured.
 *
 *  The Node service mounts at `/api/copilotkit`; a browser pointed at the bare host 404s every run
 *  with nothing on screen to explain why. The trailing slash is trimmed because this value is typed
 *  into an Azure environment variable by hand, and `http://host/` is what an address bar hands you.
 */
export function copilotRuntimeUrl(base: string): string {
  return `${base.replace(/\/+$/, "")}/api/copilotkit`;
}

/** The headers every run carries. The session id is not decoration — it is the only thing on the
 *  request that says whose lesson this is. */
export function sessionHeaders(sessionId: string): Record<string, string> {
  return { [SESSION_HEADER]: sessionId };
}

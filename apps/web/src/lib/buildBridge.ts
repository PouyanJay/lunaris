/** The build-bridge worker: this tab serving a device-compute build's LLM completions.
 *
 *  While a device build runs, the worker long-polls the run's bridge for parked completion
 *  requests, runs each on the on-device engine, and posts the text back. It stops on its own
 *  when the run ends — the server discards the bridge and the next poll 404s — or when the
 *  caller aborts (the learner navigated away / started another build). The server, not this
 *  loop, owns failure policy: if this tab goes silent, the build is failed server-side.
 */

import { authedFetch } from "./apiClient";
import type { ChatBackend, ChatMessage } from "./deviceEngine";

/** Matches the server's long-poll window (bridge router POLL_WAIT_DEFAULT_S). */
const POLL_WAIT_S = 25;

/** Pause after a transient failure (network blip, 5xx) so a broken poll can't spin hot. */
const RETRY_DELAY_MS = 1000;

interface BridgeRequest {
  requestId: string;
  messages: ChatMessage[];
}

export interface BuildBridgeWorkerOptions {
  apiBaseUrl: string;
  runId: string;
  engine: ChatBackend;
  /** Abort to stop the loop (e.g. the build's own AbortController). */
  signal: AbortSignal;
  /** Test seam: transient-failure backoff (defaults to 1s). */
  retryDelayMs?: number;
}

/** Serve the run's completions until the run ends (bridge 404) or `signal` aborts. */
export async function runBuildBridgeWorker({
  apiBaseUrl,
  runId,
  engine,
  signal,
  retryDelayMs = RETRY_DELAY_MS,
}: BuildBridgeWorkerOptions): Promise<void> {
  const base = `${apiBaseUrl}/api/runs/${runId}/bridge`;
  while (!signal.aborted) {
    let claimed: BridgeRequest[];
    try {
      const poll = await authedFetch(`${base}/requests?wait=${POLL_WAIT_S}`, { signal });
      if (poll.status === 404) return; // the run ended — the worker's stop signal
      if (!poll.ok) {
        await delay(retryDelayMs, signal);
        continue;
      }
      claimed = (await poll.json()) as BridgeRequest[];
    } catch {
      if (signal.aborted) return;
      await delay(retryDelayMs, signal); // transient network failure — poll again
      continue;
    }
    for (const request of claimed) {
      if (signal.aborted) return;
      const ended = await answerOne(base, request, engine, signal);
      if (ended) return;
    }
  }
}

/** Run one completion and post its result. Returns true when the run is gone (stop the loop);
 *  a 409 (already answered — e.g. a second tab raced this one) is skipped, not fatal. */
async function answerOne(
  base: string,
  request: BridgeRequest,
  engine: ChatBackend,
  signal: AbortSignal,
): Promise<boolean> {
  const text = await engine.chat(request.messages);
  if (signal.aborted) return true;
  const posted = await authedFetch(`${base}/results`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ requestId: request.requestId, text }),
    signal,
  });
  return posted.status === 404;
}

function delay(ms: number, signal: AbortSignal): Promise<void> {
  if (ms <= 0 || signal.aborted) return Promise.resolve();
  return new Promise((resolve) => {
    const timer = setTimeout(done, ms);
    function done() {
      signal.removeEventListener("abort", done);
      clearTimeout(timer);
      resolve();
    }
    signal.addEventListener("abort", done);
  });
}

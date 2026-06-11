import { authedFetch } from "./apiClient";

/** Thrown when an explanation can't be produced (network, HTTP, or the service is unavailable). */
export class ExplainError extends Error {}

/** Which server tier answered (the wire's provenance; "on-device" is stamped client-side). */
export type ServerExplainSource = "hosted" | "server-fallback";

export interface ServerExplainOutcome {
  explanation: string;
  source: ServerExplainSource;
}

/**
 * Ask the API to explain a transcript blob in plain language. Resolves with the explanation, or
 * rejects with {@link ExplainError} (e.g. a 503 when no Anthropic key is configured) — one error
 * channel for the caller. `context` is a short hint (e.g. the active phase) to steer the summary.
 */
export async function explainBlob(
  apiBaseUrl: string,
  content: string,
  context?: string,
): Promise<ServerExplainOutcome> {
  let response: Response;
  try {
    response = await authedFetch(`${apiBaseUrl}/api/explain`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(context ? { content, context } : { content }),
    });
  } catch (cause) {
    throw new ExplainError("Couldn't reach the explanation service.", { cause });
  }
  if (!response.ok) {
    throw new ExplainError("Couldn't generate an explanation right now.");
  }
  const body = (await response.json()) as { explanation?: unknown; source?: unknown };
  if (typeof body.explanation !== "string") {
    throw new ExplainError("The explanation response was malformed.");
  }
  // Older servers omit source; hosted is their only tier, so it is the honest default.
  const source = body.source === "server-fallback" ? "server-fallback" : "hosted";
  return { explanation: body.explanation, source };
}

/** Thrown when an explanation can't be produced (network, HTTP, or the service is unavailable). */
export class ExplainError extends Error {}

/**
 * Ask the API to explain a transcript blob in plain language. Resolves with the explanation, or
 * rejects with {@link ExplainError} (e.g. a 503 when no Anthropic key is configured) — one error
 * channel for the caller. `context` is a short hint (e.g. the active phase) to steer the summary.
 */
export async function explainBlob(
  apiBaseUrl: string,
  content: string,
  context?: string,
): Promise<string> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/api/explain`, {
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
  const body = (await response.json()) as { explanation?: unknown };
  if (typeof body.explanation !== "string") {
    throw new ExplainError("The explanation response was malformed.");
  }
  return body.explanation;
}

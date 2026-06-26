/** The FastAPI error body shape: `{ "detail": "..." }`. Read the human message from a non-OK
 *  response, falling back to `undefined` when the body isn't JSON or carries no detail. Shared by the
 *  admin API client libs so each surfaces the server's message consistently. */
export async function detailOf(response: Response): Promise<string | undefined> {
  return response
    .json()
    .then((body: { detail?: string }) => body?.detail)
    .catch(() => undefined);
}

/** The message from a thrown cause when it's an `Error` with text, else the given fallback. Shared by
 *  the admin sections so a caught failure surfaces consistently. */
export function messageFor(cause: unknown, fallback: string): string {
  return cause instanceof Error && cause.message ? cause.message : fallback;
}

/** The FastAPI error body shape: `{ "detail": "..." }`. Read the human message from a non-OK
 *  response, falling back to `undefined` when the body isn't JSON or carries no detail. Shared by the
 *  admin API client libs so each surfaces the server's message consistently. */
export async function detailOf(response: Response): Promise<string | undefined> {
  return response
    .json()
    .then((body: { detail?: string }) => body?.detail)
    .catch(() => undefined);
}

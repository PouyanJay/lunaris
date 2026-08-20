import { useCallback, useState } from "react";

export interface SessionVerbRunner {
  /** The session a verb is in flight for, so only its own row shows as busy. */
  busy: string | null;
  /** The API's own words when a verb was refused, or null. */
  failure: string | null;
  /** Run one verb against one session, then re-read the list. */
  run: (sessionId: string, verb: () => Promise<unknown>) => Promise<void>;
  /** Drop a failure the learner has moved on from (closing a dialog, say). */
  clear: () => void;
}

/** Running one lifecycle verb, and what to say when it does not go through.
 *
 *  Its own hook because the surface that presses these verbs should be a rendering concern: the
 *  list already reads through `useLiveSessions`, and the state a verb needs while it is in flight
 *  is the same three fields every time.
 *
 *  **Never optimistic.** Every verb here is irreversible or costs a model call, which is exactly
 *  where a real pending state and the true result are owed rather than a guess. The server also
 *  decides things the surface cannot: whether a close wrote a goodbye turn, whether a reset was
 *  refused because a session is still going. So the list is re-read rather than patched. */
export function useSessionVerb(refresh: () => void): SessionVerbRunner {
  const [busy, setBusy] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const run = useCallback(
    async (sessionId: string, verb: () => Promise<unknown>) => {
      setBusy(sessionId);
      setFailure(null);
      try {
        await verb();
        refresh();
      } catch (error) {
        // The API's own sentence, not a generic one: "a turn is in flight" and "you still have a
        // session going on this topic" are both instructions, and replacing them would take the
        // fix away from the learner.
        setFailure(error instanceof Error ? error.message : "That didn't go through.");
      } finally {
        setBusy(null);
      }
    },
    [refresh],
  );

  const clear = useCallback(() => setFailure(null), []);

  return { busy, failure, run, clear };
}

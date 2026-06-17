import { useEffect, useState } from "react";

import { fetchMe } from "../lib/me";

/** The signed-in caller's identity flags (currently just admin). Best-effort: a failed/aborted probe
 *  leaves ``isAdmin`` false, so the admin surface simply stays hidden — and the API enforces admin
 *  access on every admin route regardless of what the web shows. */
export function useMe(apiBaseUrl: string): { isAdmin: boolean } {
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetchMe(apiBaseUrl, controller.signal)
      .then((me) => {
        if (!controller.signal.aborted) setIsAdmin(me.isAdmin);
      })
      .catch(() => {
        /* best-effort — no admin nav on failure */
      });
    return () => controller.abort();
  }, [apiBaseUrl]);

  return { isAdmin };
}

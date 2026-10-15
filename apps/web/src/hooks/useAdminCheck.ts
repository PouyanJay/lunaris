import { useEffect, useState } from "react";

import { messageFor } from "../lib/apiErrors";
import { fetchMe } from "../lib/me";

export type AdminCheck =
  | { status: "verifying" }
  | { status: "admin" }
  | { status: "not-admin" }
  | { status: "error"; message: string };

/** Whether the signed-in caller is an administrator, asked of `baseUrl` (the always-on control
 *  plane while production is off). `retry` asks again after an error. */
export function useAdminCheck(baseUrl: string): { check: AdminCheck; retry: () => void } {
  const [check, setCheck] = useState<AdminCheck>({ status: "verifying" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setCheck({ status: "verifying" });
    fetchMe(baseUrl, controller.signal)
      .then((me) => {
        if (controller.signal.aborted) return;
        setCheck({ status: me.isAdmin ? "admin" : "not-admin" });
      })
      .catch((cause) => {
        if (controller.signal.aborted) return;
        setCheck({
          status: "error",
          message: messageFor(cause, "Could not confirm administrator access."),
        });
      });
    return () => controller.abort();
  }, [baseUrl, attempt]);

  return { check, retry: () => setAttempt((n) => n + 1) };
}

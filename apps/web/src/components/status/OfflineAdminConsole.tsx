import { useEffect, useId, useState, type ReactNode } from "react";

import { useAuth } from "../../hooks/useAuth";
import { messageFor } from "../../lib/apiErrors";
import { fetchMe } from "../../lib/me";
import { ErrorWithRetry } from "../admin/ErrorWithRetry";
import { PowerSwitch } from "../admin/PowerSwitch";
import { Button } from "../primitives/Button";
import styles from "./ServiceOffline.module.css";

type AdminCheck =
  | { status: "checking" }
  | { status: "admin" }
  | { status: "not-admin" }
  | { status: "error"; message: string };

/** Production controls for a signed-in visitor while the service is offline.
 *
 *  Administrator access is confirmed by the control plane, not the stopped API: it runs the same
 *  admin check and stays deployed when production is off. It scales to zero, so the first answer
 *  can take a while as it wakes. */
export function OfflineAdminConsole({ controlBaseUrl }: { controlBaseUrl: string }) {
  const { signOut } = useAuth();
  const [check, setCheck] = useState<AdminCheck>({ status: "checking" });
  const [attempt, setAttempt] = useState(0);
  const headingId = useId();

  useEffect(() => {
    const controller = new AbortController();
    setCheck({ status: "checking" });
    fetchMe(controlBaseUrl, controller.signal)
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
  }, [controlBaseUrl, attempt]);

  let body: ReactNode;
  if (check.status === "checking") {
    body = (
      <p className={styles.consoleNote} role="status" aria-live="polite">
        Checking administrator access… This can take up to a minute while the controls wake up.
      </p>
    );
  } else if (check.status === "error") {
    body = <ErrorWithRetry message={check.message} onRetry={() => setAttempt((n) => n + 1)} />;
  } else if (check.status === "not-admin") {
    body = (
      <p className={styles.consoleNote}>
        This account isn&rsquo;t an administrator, so it can&rsquo;t manage production.
      </p>
    );
  } else {
    body = <PowerSwitch controlBaseUrl={controlBaseUrl} />;
  }

  return (
    <section className={styles.console} aria-labelledby={headingId}>
      <span className="eyebrow">Administrator</span>
      <h2 id={headingId} className={styles.consoleHeading}>
        Production controls
      </h2>
      {body}
      <div className={styles.signOut}>
        <Button variant="ghost" onClick={() => void signOut()}>
          Sign out
        </Button>
      </div>
    </section>
  );
}

import { useId } from "react";

import { useAdminCheck, type AdminCheck } from "../../hooks/useAdminCheck";
import { useAuth } from "../../hooks/useAuth";
import { ErrorWithRetry } from "../admin/ErrorWithRetry";
import { PowerSwitch } from "../admin/PowerSwitch";
import { Button } from "../primitives/Button";
import styles from "./ServiceOffline.module.css";

/** Production controls for a signed-in visitor while the service is offline.
 *
 *  Administrator access is confirmed by the control plane, not the stopped API: it runs the same
 *  admin check and stays deployed when production is off. It scales to zero, so the first answer
 *  can take a while as it wakes. */
export function OfflineAdminConsole({ controlBaseUrl }: { controlBaseUrl: string }) {
  const { signOut } = useAuth();
  const { check, retry } = useAdminCheck(controlBaseUrl);
  const headingId = useId();

  return (
    <section className={styles.console} aria-labelledby={headingId}>
      <span className="eyebrow">Administrator</span>
      <h2 id={headingId} className={styles.consoleHeading}>
        Production controls
      </h2>
      <ConsoleBody check={check} onRetry={retry} controlBaseUrl={controlBaseUrl} />
      <div className={styles.signOut}>
        <Button variant="ghost" onClick={() => void signOut()}>
          Sign out
        </Button>
      </div>
    </section>
  );
}

function ConsoleBody({
  check,
  onRetry,
  controlBaseUrl,
}: {
  check: AdminCheck;
  onRetry: () => void;
  controlBaseUrl: string;
}) {
  switch (check.status) {
    case "verifying":
      return (
        <p className={styles.consoleNote} role="status" aria-live="polite">
          Checking administrator access… This can take up to a minute while the controls wake up.
        </p>
      );
    case "error":
      return <ErrorWithRetry message={check.message} onRetry={onRetry} />;
    case "not-admin":
      return (
        <p className={styles.consoleNote}>
          This account isn&rsquo;t an administrator, so it can&rsquo;t manage production.
        </p>
      );
    case "admin":
      return <PowerSwitch controlBaseUrl={controlBaseUrl} />;
  }
}

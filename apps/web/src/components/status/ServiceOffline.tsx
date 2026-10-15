import { useId, useState } from "react";

import { useAuth } from "../../hooks/useAuth";
import { ACCESS_CONTACT_EMAIL } from "../../lib/accessContact";
import { AuthScreen } from "../auth/AuthScreen";
import { Button } from "../primitives/Button";
import { buttonClassName } from "../primitives/buttonVariants";
import { StatusDot } from "../primitives/StatusDot";
import { BrandMark } from "../shell/BrandMark";
import { OfflineAdminConsole } from "./OfflineAdminConsole";
import styles from "./ServiceOffline.module.css";

interface ServiceOfflineProps {
  /** The always-on control plane, which answers while the API is stopped. */
  controlBaseUrl: string;
  /** A manual re-check is in flight. */
  checking: boolean;
  onRetry: () => void;
}

/** The page every visitor sees while production is offline: what is going on and who to ask for
 *  access. An administrator can sign in from here and turn production back on, since the rest of
 *  the app (which talks to the stopped API) is unavailable. */
export function ServiceOffline({ controlBaseUrl, checking, onRetry }: ServiceOfflineProps) {
  const { enabled, session } = useAuth();
  const [signingIn, setSigningIn] = useState(false);
  const headingId = useId();

  if (signingIn && !session) {
    return <AuthScreen adminSignIn={{ onBack: () => setSigningIn(false) }} />;
  }

  return (
    <main className={styles.screen} aria-labelledby={headingId}>
      <div className={styles.panel}>
        <div className={styles.brand}>
          <BrandMark size={28} />
          <span className={styles.wordmark}>Lunaris</span>
        </div>
        <div className={styles.status}>
          <StatusDot label="Offline" tone="warning" />
        </div>
        <h1 id={headingId} className={styles.heading}>
          Lunaris is offline
        </h1>
        <p className={styles.body}>
          The service is currently offline. If you&rsquo;d like access, send a note to the address
          below.
        </p>
        <div className={styles.actions}>
          <a className={buttonClassName("primary")} href={`mailto:${ACCESS_CONTACT_EMAIL}`}>
            Email {ACCESS_CONTACT_EMAIL}
          </a>
          <Button onClick={onRetry} disabled={checking}>
            {checking ? "Checking…" : "Try again"}
          </Button>
        </div>

        {enabled && (
          <AdminEntry
            signedIn={session !== null}
            controlBaseUrl={controlBaseUrl}
            onSignIn={() => setSigningIn(true)}
          />
        )}
      </div>
    </main>
  );
}

/** The way in for an administrator: production controls once signed in, else a quiet sign-in. */
function AdminEntry({
  signedIn,
  controlBaseUrl,
  onSignIn,
}: {
  signedIn: boolean;
  controlBaseUrl: string;
  onSignIn: () => void;
}) {
  if (signedIn) return <OfflineAdminConsole controlBaseUrl={controlBaseUrl} />;
  return (
    <p className={styles.footer}>
      <button type="button" className={styles.footerButton} onClick={onSignIn}>
        Administrator sign in
      </button>
    </p>
  );
}

import { type ReactNode } from "react";

import { useAuth } from "../../hooks/useAuth";
import { AuthScreen } from "./AuthScreen";
import styles from "./AuthGate.module.css";

/** Renders its children only when the user is authenticated.
 *
 *  When auth is not configured (no Supabase client) the gate is transparent — local dev against the
 *  API still works without a login. When configured: a brief loading state while the session is
 *  restored, then the login screen until signed in. ``apiBaseUrl`` is forwarded to the login screen
 *  so it can read the public signup-gate status (whether to collect an invitation code). */
export function AuthGate({
  children,
  apiBaseUrl,
}: {
  children: ReactNode;
  apiBaseUrl?: string | undefined;
}) {
  const { enabled, loading, session } = useAuth();

  if (!enabled) return <>{children}</>;
  if (loading) {
    return (
      <div className={styles.loading} role="status" aria-live="polite">
        Loading…
      </div>
    );
  }
  if (!session) return <AuthScreen apiBaseUrl={apiBaseUrl} />;
  return <>{children}</>;
}

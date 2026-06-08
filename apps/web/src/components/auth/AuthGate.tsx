import { type ReactNode } from "react";

import { useAuth } from "../../hooks/useAuth";
import { AuthScreen } from "./AuthScreen";
import styles from "./AuthGate.module.css";

/** Renders its children only when the user is authenticated.
 *
 *  When auth is not configured (no Supabase client) the gate is transparent — local dev against the
 *  API still works without a login. When configured: a brief loading state while the session is
 *  restored, then the login screen until signed in. */
export function AuthGate({ children }: { children: ReactNode }) {
  const { enabled, loading, session } = useAuth();

  if (!enabled) return <>{children}</>;
  if (loading) {
    return (
      <div className={styles.loading} role="status" aria-live="polite">
        Loading…
      </div>
    );
  }
  if (!session) return <AuthScreen />;
  return <>{children}</>;
}

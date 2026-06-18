import { useEffect, useState, type ReactNode } from "react";

import { deleteAdminUser, fetchAdminUsers, type AdminAccount } from "../../lib/adminUsers";
import { Button } from "../primitives/Button";
import styles from "./AdminPortal.module.css";

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; accounts: AdminAccount[] };

function messageFor(cause: unknown, fallback: string): string {
  return cause instanceof Error && cause.message ? cause.message : fallback;
}

function formatDate(iso: string | null, fallback: string): string {
  if (!iso) return fallback;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return fallback;
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/** The list of end-user accounts with their status, plus a delete action (admins only). A section of
 *  the Admin Portal — owns its own loading/error state inline. */
export function AdminUsersSection({ apiBaseUrl }: { apiBaseUrl: string }) {
  const [state, setState] = useState<State>({ status: "loading" });
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadCount, setReloadCount] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "loading" });
    fetchAdminUsers(apiBaseUrl, controller.signal)
      .then((accounts) => {
        if (controller.signal.aborted) return;
        setState({ status: "ready", accounts });
      })
      .catch((cause) => {
        if (controller.signal.aborted) return;
        setState({ status: "error", message: messageFor(cause, "Could not load users.") });
      });
    return () => controller.abort();
  }, [apiBaseUrl, reloadCount]);

  async function remove(id: string) {
    setBusyId(id);
    setError(null);
    try {
      await deleteAdminUser(apiBaseUrl, id);
      setConfirmingId(null);
      setReloadCount((n) => n + 1);
    } catch (cause) {
      setError(messageFor(cause, "Could not delete the account."));
    } finally {
      setBusyId(null);
    }
  }

  let body: ReactNode;
  if (state.status === "loading") {
    body = (
      <p className={styles.status} role="status" aria-live="polite">
        Loading…
      </p>
    );
  } else if (state.status === "error") {
    body = (
      <div className={styles.statusRegion}>
        <p className={styles.error} role="alert">
          {state.message}
        </p>
        <div>
          <Button type="button" onClick={() => setReloadCount((n) => n + 1)}>
            Retry
          </Button>
        </div>
      </div>
    );
  } else if (state.accounts.length === 0) {
    body = <p className={styles.empty}>No accounts yet.</p>;
  } else {
    body = (
      <div className={styles.tableWrap}>
        <table className={styles.table} aria-label="User accounts">
          <thead>
            <tr>
              <th scope="col">Email</th>
              <th scope="col">Status</th>
              <th scope="col">Created</th>
              <th scope="col">Last sign-in</th>
              <th scope="col">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {state.accounts.map((account) => (
              <tr key={account.id}>
                <td>
                  <span className={styles.email}>
                    {account.email ?? "(no email)"}
                    {account.isAdmin && (
                      <span className={`${styles.badge} ${styles.badgeAdmin}`}>Admin</span>
                    )}
                    {account.isSelf && (
                      <span className={`${styles.badge} ${styles.badgeYou}`}>You</span>
                    )}
                  </span>
                </td>
                <td>
                  {account.emailConfirmed ? (
                    <span className={styles.meta}>Confirmed</span>
                  ) : (
                    <span className={`${styles.badge} ${styles.badgePending}`}>Pending</span>
                  )}
                </td>
                <td className={styles.meta}>{formatDate(account.createdAt, "—")}</td>
                <td className={styles.meta}>{formatDate(account.lastSignInAt, "Never")}</td>
                <td className={styles.actionsCell}>
                  {account.isSelf ? null : confirmingId === account.id ? (
                    <span className={styles.confirmRow}>
                      <span className={styles.confirmText}>Delete?</span>
                      <Button
                        type="button"
                        onClick={() => setConfirmingId(null)}
                        disabled={busyId === account.id}
                      >
                        Cancel
                      </Button>
                      <Button
                        type="button"
                        variant="danger"
                        onClick={() => void remove(account.id)}
                        disabled={busyId === account.id}
                      >
                        {busyId === account.id ? "Deleting…" : "Delete"}
                      </Button>
                    </span>
                  ) : (
                    <Button
                      type="button"
                      variant="danger"
                      aria-label={`Delete ${account.email ?? "account"}`}
                      onClick={() => setConfirmingId(account.id)}
                    >
                      Delete
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <section className={styles.section}>
      <h2 className={styles.heading}>Users</h2>
      <p className={styles.intro}>
        Everyone who has created an account. Deleting an account removes their sign-in; you can't
        delete your own.
      </p>
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
      {body}
    </section>
  );
}

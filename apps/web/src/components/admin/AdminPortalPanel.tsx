import { AdminUsersSection } from "./AdminUsersSection";
import { InviteGateSection } from "./InviteGateSection";
import { ProdOpsSection } from "./ProdOpsSection";
import styles from "./AdminPortal.module.css";

/** The Admin Portal canvas: the shared invitation-code gate, the user list, and prod operations, as
 *  sibling sections. Shown only to admins (the nav and the API both gate on the admin allowlist);
 *  each section owns its own data loading so one slow fetch never blocks the other. */
export function AdminPortalPanel({ apiBaseUrl }: { apiBaseUrl: string }) {
  return (
    <div className={styles.panel}>
      <InviteGateSection apiBaseUrl={apiBaseUrl} />
      <AdminUsersSection apiBaseUrl={apiBaseUrl} />
      <ProdOpsSection apiBaseUrl={apiBaseUrl} />
    </div>
  );
}

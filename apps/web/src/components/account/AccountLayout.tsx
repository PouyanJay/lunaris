import type { AccountSection } from "../../lib/routes";
import { AdminPortalPanel } from "../admin/AdminPortalPanel";
import { CanvasNotice } from "../states/CanvasNotice";
import { AccountNav } from "./AccountNav";
import { UserAccountSection } from "./UserAccountSection";
import settingsStyles from "../settings/SettingsLayout.module.css";

interface AccountLayoutProps {
  apiBaseUrl: string;
  /** The active sub-section (from the `/account/:section` URL). */
  section: AccountSection;
  /** Whether the signed-in user is a workspace admin — gates the Admin Portal section + the sub-nav. */
  isAdmin: boolean;
  /** Return to the app after signing out (or when there's no session). */
  onGoHome: () => void;
}

/** The Account surface. For an admin it mirrors Settings: a left sub-nav (User account | Admin
 *  Portal) welded to the active section's content. A non-admin only has their own account, so no
 *  sub-nav is shown — just the User account content, full width. `/admin` folds in here as the
 *  Admin Portal section (see resolveRoute). */
export function AccountLayout({ apiBaseUrl, section, isAdmin, onGoHome }: AccountLayoutProps) {
  const content = renderSection(section, isAdmin, apiBaseUrl, onGoHome);

  // The content region is the single scroller (mirrors Settings) — each section renders its own bare
  // panel stack into it, so there's exactly one scrollbar and one gutter, never a nested pair.
  const surface = <div className={settingsStyles.content}>{content}</div>;

  // Non-admins have a single surface — render it plainly, no sub-nav.
  if (!isAdmin) return surface;

  return (
    <div className={settingsStyles.layout}>
      <AccountNav active={section} />
      {surface}
    </div>
  );
}

function renderSection(
  section: AccountSection,
  isAdmin: boolean,
  apiBaseUrl: string,
  onGoHome: () => void,
) {
  if (section === "admin-portal") {
    // Fail closed: until /api/me confirms admin, hold the portal behind the notice (the API also
    // enforces admin on every call — this is presentation, not the security boundary).
    return isAdmin ? (
      <AdminPortalPanel apiBaseUrl={apiBaseUrl} />
    ) : (
      <CanvasNotice
        eyebrow="Restricted"
        title="Admin access required"
        body="This page is only available to workspace administrators."
        actionLabel="Go home"
        onAction={onGoHome}
      />
    );
  }
  return <UserAccountSection onGoHome={onGoHome} />;
}

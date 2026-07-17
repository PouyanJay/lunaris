import { render, screen, within } from "@testing-library/react";
import type { User } from "@supabase/supabase-js";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { AccountLayout } from "./AccountLayout";
import type { AccountSection } from "../../lib/routes";

// Stub the admin portal (its sections self-fetch) — this suite tests the layout's routing/gating,
// not the portal's internals.
vi.mock("../admin/AdminPortalPanel", () => ({
  AdminPortalPanel: () => <div>ADMIN PORTAL PANEL</div>,
}));

// A signed-in user so the User account section renders its identity, not the no-session notice.
vi.mock("../../hooks/useAuth", () => ({
  useAuth: () => ({
    user: { email: "pj@example.com", user_metadata: { display_name: "Pouyan" } } as unknown as User,
    updateDisplayName: vi.fn(),
    signOut: vi.fn(),
  }),
}));

function renderLayout(section: AccountSection, isAdmin: boolean) {
  return render(
    <MemoryRouter>
      <AccountLayout apiBaseUrl="http://api.test" section={section} isAdmin={isAdmin} onGoHome={vi.fn()} />
    </MemoryRouter>,
  );
}

describe("AccountLayout", () => {
  it("shows no sub-nav for a non-admin — just their own account", () => {
    renderLayout("user-account", false);

    expect(screen.queryByRole("navigation", { name: /account sections/i })).not.toBeInTheDocument();
    expect(screen.getByLabelText(/display name/i)).toBeInTheDocument();
  });

  it("gives an admin a sub-nav (User account | Admin Portal) welded to the section content", () => {
    renderLayout("user-account", true);

    const nav = screen.getByRole("navigation", { name: /account sections/i });
    const links = within(nav).getAllByRole("link");
    expect(links.map((a) => a.textContent)).toEqual(["User account", "Admin Portal"]);
    expect(within(nav).getByRole("link", { name: /user account/i })).toHaveAttribute(
      "aria-current",
      "page",
    );
    // The active section's content is the user's identity.
    expect(screen.getByLabelText(/display name/i)).toBeInTheDocument();
  });

  it("routes an admin to the Admin Portal section", () => {
    renderLayout("admin-portal", true);

    expect(screen.getByText("ADMIN PORTAL PANEL")).toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: /account sections/i }),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("navigation", { name: /account sections/i })).getByRole("link", {
        name: /admin portal/i,
      }),
    ).toHaveAttribute("aria-current", "page");
  });

  it("fails closed: a non-admin at the Admin Portal section gets the restricted notice", () => {
    renderLayout("admin-portal", false);

    expect(screen.getByRole("heading", { name: /admin access required/i })).toBeInTheDocument();
    expect(screen.queryByText("ADMIN PORTAL PANEL")).not.toBeInTheDocument();
  });
});

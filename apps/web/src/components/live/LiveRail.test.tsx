import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

// The rail's footer reads the signed-in user for the account row — stub it so the test needs no
// AuthProvider, the same way Studio's rail test does.
vi.mock("../../hooks/useAuth", () => ({
  useAuth: () => ({ user: { email: "pj@example.com", user_metadata: { display_name: "Pouyan" } } }),
}));

import { LiveRail } from "./LiveRail";

/** The rail, rendered at a route, with the theme props the shell threads into it. */
function shown(path = "/live?topic=How%20neural%20networks%20learn", collapsed = false) {
  const onToggleCollapsed = vi.fn();
  const onToggleTheme = vi.fn();
  render(
    <MemoryRouter initialEntries={[path]}>
      <LiveRail
        collapsed={collapsed}
        onToggleCollapsed={onToggleCollapsed}
        theme="light"
        onToggleTheme={onToggleTheme}
      />
    </MemoryRouter>,
  );
  return { onToggleCollapsed, onToggleTheme };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("LiveRail", () => {
  it("carries Live's own destinations, not Studio's", () => {
    shown();

    const nav = screen.getByRole("navigation", { name: /primary/i });
    expect(within(nav).getByRole("link", { name: /your sessions/i })).toBeInTheDocument();
    // Studio's nouns would be dead links inside a session: there are no courses here to list, and
    // no build activity to watch.
    expect(within(nav).queryByRole("link", { name: /my courses/i })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: /bookmarks/i })).not.toBeInTheDocument();
  });

  it("offers a way back to Studio", () => {
    shown();

    // The whole complaint that started this task: once you were in Live, the only exit was editing
    // the URL.
    const back = screen.getByRole("link", { name: /studio/i });
    expect(back).toHaveAttribute("href", "/");
  });

  it("starts a new session in the composer already in Live mode", () => {
    shown();

    // A "new session" that landed the learner in Studio's composer would be a rail sending them
    // out of the product they are standing in.
    expect(screen.getByRole("link", { name: /new session/i })).toHaveAttribute(
      "href",
      "/new?mode=live",
    );
  });

  it("keeps the shared footer, so Live is not a place with no settings", () => {
    shown();

    const footer = screen.getByRole("navigation", { name: /secondary/i });
    expect(within(footer).getByRole("link", { name: /settings/i })).toBeInTheDocument();
    expect(
      within(footer).getByRole("button", { name: /switch to dark mode/i }),
    ).toBeInTheDocument();
  });

  it("names every destination even when it is only an icon", () => {
    shown("/live/sessions", true);

    // Collapsed, the labels drop away and the accessible names must not: an icon rail that is
    // unreadable to a screen reader is a rail that only sighted mouse users have.
    const nav = screen.getByRole("navigation", { name: /primary/i });
    expect(within(nav).getByRole("link", { name: /your sessions/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /new session/i })).toBeInTheDocument();
  });

  it("can be expanded from the rail itself", () => {
    const { onToggleCollapsed } = shown("/live?topic=Anything", true);

    fireEvent.click(screen.getByRole("button", { name: /expand sidebar/i }));

    expect(onToggleCollapsed).toHaveBeenCalled();
  });

  it("marks where the learner is", () => {
    shown("/live/sessions");

    // NavLink sets aria-current on the active destination, which is how anybody navigating by
    // keyboard or screen reader knows which of these they are standing on.
    expect(screen.getByRole("link", { name: /your sessions/i })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });
});

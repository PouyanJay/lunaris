import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

// The rail reads the signed-in user for the account row — stub it so the test needs no AuthProvider.
vi.mock("../../hooks/useAuth", () => ({
  useAuth: () => ({ user: { email: "pj@example.com", user_metadata: { display_name: "Pouyan" } } }),
}));

import { Sidebar } from "./Sidebar";

function renderSidebar(props: Partial<React.ComponentProps<typeof Sidebar>> = {}) {
  const onPrefetchLibrary = vi.fn();
  render(
    <MemoryRouter>
      <Sidebar
        onNewCourse={vi.fn()}
        collapsed={false}
        onToggleCollapsed={vi.fn()}
        onPrefetchLibrary={onPrefetchLibrary}
        theme="dark"
        onToggleTheme={vi.fn()}
        {...props}
      />
    </MemoryRouter>,
  );
  return { onPrefetchLibrary };
}

afterEach(() => vi.clearAllMocks());

describe("Sidebar library prefetch on intent", () => {
  it("warms the library on hover of the My courses entry", () => {
    const { onPrefetchLibrary } = renderSidebar();

    fireEvent.mouseEnter(screen.getByRole("link", { name: "My courses" }));

    expect(onPrefetchLibrary).toHaveBeenCalled();
  });

  it("warms the library on keyboard focus of the My courses entry", () => {
    const { onPrefetchLibrary } = renderSidebar();

    fireEvent.focus(screen.getByRole("link", { name: "My courses" }));

    expect(onPrefetchLibrary).toHaveBeenCalled();
  });

  it("does not prefetch from hovering a different nav entry (Home)", () => {
    const { onPrefetchLibrary } = renderSidebar();

    fireEvent.mouseEnter(screen.getByRole("link", { name: "Home" }));

    expect(onPrefetchLibrary).not.toHaveBeenCalled();
  });
});

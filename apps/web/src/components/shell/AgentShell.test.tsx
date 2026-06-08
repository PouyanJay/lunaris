import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { SidebarLayout } from "../../hooks/useSidebarLayout";
import { AgentShell } from "./AgentShell";

/** A static layout — the drawer behaviour under test is independent of resize/collapse. */
function makeLayout(): SidebarLayout {
  return {
    collapsed: false,
    width: 264,
    resizing: false,
    toggleCollapsed: vi.fn(),
    startResize: vi.fn(),
    nudgeWidth: vi.fn(),
  };
}

function renderShell(overrides: Partial<React.ComponentProps<typeof AgentShell>> = {}) {
  const props: React.ComponentProps<typeof AgentShell> = {
    sidebar: <button type="button">A run</button>,
    title: "New course",
    layout: makeLayout(),
    mobileNavOpen: false,
    onOpenMobileNav: vi.fn(),
    onCloseMobileNav: vi.fn(),
    children: <p>canvas</p>,
    ...overrides,
  };
  return { props, ...render(<AgentShell {...props} />) };
}

describe("AgentShell mobile nav drawer", () => {
  it("opens the drawer from the header menu button", () => {
    const onOpenMobileNav = vi.fn();
    renderShell({ onOpenMobileNav });

    fireEvent.click(screen.getByRole("button", { name: /open navigation/i }));

    expect(onOpenMobileNav).toHaveBeenCalledOnce();
  });

  it("marks the rail open and shows a dismiss scrim when the drawer is open", () => {
    const onCloseMobileNav = vi.fn();
    renderShell({ mobileNavOpen: true, onCloseMobileNav });

    // The rail advertises its open state for the CSS slide-in + assistive tech.
    expect(screen.getByRole("complementary", { name: /runs and navigation/i })).toHaveAttribute(
      "data-drawer-open",
    );
    // Tapping the scrim closes it.
    fireEvent.click(screen.getByRole("button", { name: /close navigation/i }));
    expect(onCloseMobileNav).toHaveBeenCalledOnce();
  });

  it("closes the open drawer on Escape", () => {
    const onCloseMobileNav = vi.fn();
    renderShell({ mobileNavOpen: true, onCloseMobileNav });

    fireEvent.keyDown(window, { key: "Escape" });

    expect(onCloseMobileNav).toHaveBeenCalledOnce();
  });

  it("renders no scrim while the drawer is closed", () => {
    renderShell({ mobileNavOpen: false });

    expect(screen.queryByRole("button", { name: /close navigation/i })).not.toBeInTheDocument();
  });

  it("moves focus into the rail on open and restores it to the menu button on close", () => {
    // Arrange — start closed with the menu button focused (as a real tap would leave it).
    const { props, rerender } = renderShell({
      mobileNavOpen: false,
      sidebar: <button type="button">First run</button>,
    });
    screen.getByRole("button", { name: /open navigation/i }).focus();

    // Act — open: focus moves to the first focusable element in the rail.
    rerender(<AgentShell {...props} mobileNavOpen />);
    expect(screen.getByRole("button", { name: /first run/i })).toHaveFocus();

    // Act — close: focus returns to the trigger (the WCAG drawer contract).
    rerender(<AgentShell {...props} mobileNavOpen={false} />);
    expect(screen.getByRole("button", { name: /open navigation/i })).toHaveFocus();
  });

  it("locks body scroll while open and restores it on close", () => {
    const { props, rerender } = renderShell({ mobileNavOpen: true });
    expect(document.body.style.overflow).toBe("hidden");

    rerender(<AgentShell {...props} mobileNavOpen={false} />);
    expect(document.body.style.overflow).toBe("");
  });
});

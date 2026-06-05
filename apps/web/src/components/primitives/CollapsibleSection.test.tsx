import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CollapsibleSection } from "./CollapsibleSection";

describe("CollapsibleSection", () => {
  it("renders the eyebrow + title and shows the body open by default", () => {
    render(
      <CollapsibleSection eyebrow="Settings" title="Keys & configuration">
        <p>body content</p>
      </CollapsibleSection>,
    );

    expect(screen.getByText("Settings")).toBeInTheDocument();
    const trigger = screen.getByRole("button", { name: /keys & configuration/i });
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("body content")).toBeVisible();
  });

  it("collapses and re-expands the body when the header is toggled", () => {
    render(
      <CollapsibleSection eyebrow="Settings" title="Keys & configuration">
        <p>body content</p>
      </CollapsibleSection>,
    );
    const trigger = screen.getByRole("button", { name: /keys & configuration/i });

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("body content")).not.toBeVisible();

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("body content")).toBeVisible();
  });

  it("can start collapsed and exposes the body via aria-controls", () => {
    render(
      <CollapsibleSection
        eyebrow="Trusted sources"
        title="Source authority config"
        defaultOpen={false}
      >
        <p>body content</p>
      </CollapsibleSection>,
    );
    const trigger = screen.getByRole("button", { name: /source authority config/i });

    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("body content")).not.toBeVisible();
    // The trigger points at the collapsed region by id (the body wrapper, not its inner text).
    const region = screen.getByRole("region", { hidden: true });
    expect(trigger).toHaveAttribute("aria-controls", region.id);
  });

  it("renders an action beside the trigger, not inside it", () => {
    render(
      <CollapsibleSection
        eyebrow="Settings"
        title="Keys & configuration"
        action={<button>Done</button>}
      >
        <p>body content</p>
      </CollapsibleSection>,
    );

    const done = screen.getByRole("button", { name: "Done" });
    const trigger = screen.getByRole("button", { name: /keys & configuration/i });
    expect(done).toBeInTheDocument();
    expect(trigger).not.toContainElement(done);
  });
});

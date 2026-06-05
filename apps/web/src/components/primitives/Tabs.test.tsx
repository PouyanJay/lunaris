import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { Tabs } from "./Tabs";

const TABS = [
  { id: "spine", label: "Universal spine" },
  { id: "pack", label: "Field packs" },
  { id: "denylist", label: "Denylist" },
];

function Harness({ initial = "spine" }: { initial?: string }) {
  const [active, setActive] = useState(initial);
  return (
    <Tabs tabs={TABS} activeId={active} onChange={setActive} label="Source groups">
      <p>panel: {active}</p>
    </Tabs>
  );
}

describe("Tabs", () => {
  it("renders a tablist with the active tab selected and its panel shown", () => {
    render(<Harness />);

    expect(screen.getByRole("tablist", { name: "Source groups" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Universal spine" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("tabpanel")).toHaveTextContent("panel: spine");
  });

  it("switches the panel when another tab is clicked", () => {
    render(<Harness />);

    fireEvent.click(screen.getByRole("tab", { name: "Field packs" }));

    expect(screen.getByRole("tab", { name: "Field packs" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("tabpanel")).toHaveTextContent("panel: pack");
  });

  it("moves between tabs with arrow keys (roving tabindex)", () => {
    render(<Harness />);
    const spine = screen.getByRole("tab", { name: "Universal spine" });

    expect(spine).toHaveAttribute("tabindex", "0");
    fireEvent.keyDown(spine, { key: "ArrowRight" });

    const pack = screen.getByRole("tab", { name: "Field packs" });
    expect(pack).toHaveAttribute("aria-selected", "true");
    expect(pack).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("tab", { name: "Universal spine" })).toHaveAttribute("tabindex", "-1");
  });

  it("wraps with Home/End", () => {
    render(<Harness />);
    fireEvent.keyDown(screen.getByRole("tab", { name: "Universal spine" }), { key: "End" });
    expect(screen.getByRole("tab", { name: "Denylist" })).toHaveAttribute("aria-selected", "true");

    fireEvent.keyDown(screen.getByRole("tab", { name: "Denylist" }), { key: "Home" });
    expect(screen.getByRole("tab", { name: "Universal spine" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });
});

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SegmentedControl } from "./SegmentedControl";

const SEGMENTS = [
  { value: "standard", label: "Standard" },
  { value: "thorough", label: "Thorough" },
] as const;

function renderControl(value: "standard" | "thorough" = "standard") {
  const onChange = vi.fn();
  render(
    <SegmentedControl segments={[...SEGMENTS]} value={value} onChange={onChange} label="Depth" />,
  );
  return onChange;
}

describe("SegmentedControl", () => {
  it("marks the selected segment and exposes a radiogroup", () => {
    renderControl("thorough");
    expect(screen.getByRole("radiogroup", { name: "Depth" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Thorough" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Standard" })).not.toBeChecked();
  });

  it("selects a segment on click", () => {
    const onChange = renderControl("standard");
    fireEvent.click(screen.getByRole("radio", { name: "Thorough" }));
    expect(onChange).toHaveBeenCalledWith("thorough");
  });

  it("moves the selection with arrow keys (roving tabindex)", () => {
    const onChange = renderControl("standard");
    const selected = screen.getByRole("radio", { name: "Standard" });
    // Only the selected segment is a tab stop.
    expect(selected).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("radio", { name: "Thorough" })).toHaveAttribute("tabindex", "-1");
    fireEvent.keyDown(selected, { key: "ArrowRight" });
    expect(onChange).toHaveBeenCalledWith("thorough");
  });
});

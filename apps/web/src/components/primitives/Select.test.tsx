import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Select } from "./Select";

const OPTIONS = [
  { value: "a", label: "Alpha" },
  { value: "b", label: "Beta" },
  { value: "c", label: "Gamma" },
];

function renderSelect(value = "a", onChange = vi.fn()) {
  render(
    <>
      <span id="lbl">Greek letter</span>
      <Select value={value} options={OPTIONS} onChange={onChange} aria-labelledby="lbl" />
    </>,
  );
  return onChange;
}

describe("Select", () => {
  it("shows the selected option's label on the trigger, not the raw value", () => {
    renderSelect("b");
    expect(screen.getByRole("button", { name: /greek letter beta/i })).toBeInTheDocument();
    // The list is closed until opened.
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("opens a listbox and reports the chosen value", () => {
    const onChange = renderSelect("a");

    fireEvent.click(screen.getByRole("button", { name: /greek letter/i }));
    const list = screen.getByRole("listbox", { name: /greek letter/i });
    expect(list).toBeInTheDocument();
    // The current value is marked selected.
    expect(screen.getByRole("option", { name: "Alpha" })).toHaveAttribute("aria-selected", "true");

    fireEvent.pointerDown(screen.getByRole("option", { name: "Gamma" }));
    expect(onChange).toHaveBeenCalledWith("c");
    // Closes after choosing.
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("is keyboard-operable: arrow to move, Enter to choose", () => {
    const onChange = renderSelect("a");
    const trigger = screen.getByRole("button", { name: /greek letter/i });

    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    const list = screen.getByRole("listbox");
    // Active starts on the current value (Alpha); one ArrowDown moves to Beta.
    fireEvent.keyDown(list, { key: "ArrowDown" });
    fireEvent.keyDown(list, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith("b");
  });

  it("closes on Escape without choosing", () => {
    const onChange = renderSelect("a");

    fireEvent.click(screen.getByRole("button", { name: /greek letter/i }));
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "Escape" });

    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("does not open when disabled", () => {
    render(<Select value="a" options={OPTIONS} onChange={vi.fn()} disabled aria-labelledby="lbl" />);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });
});

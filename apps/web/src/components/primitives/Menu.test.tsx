import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { Menu } from "./Menu";

const OPTIONS = [
  { value: "standard", label: "Standard", description: "Fewer sources, faster build" },
  { value: "thorough", label: "Thorough", description: "Wider research. Slower, better grounded" },
];

function Harness({ onChange = vi.fn() }: { onChange?: (v: string) => void }) {
  const [value, setValue] = useState("standard");
  return (
    <Menu
      label="Depth"
      value={value}
      options={OPTIONS}
      onChange={(next) => {
        setValue(next);
        onChange(next);
      }}
    />
  );
}

function openMenu() {
  fireEvent.click(screen.getByRole("button", { name: /depth/i }));
  return screen.getByRole("menu");
}

/** The menu's option rows, index-checked so the suite reads without non-null assertions. */
function rows(): HTMLElement[] {
  return within(screen.getByRole("menu")).getAllByRole("menuitemradio");
}

function row(index: number): HTMLElement {
  const found = rows()[index];
  if (!found) throw new Error(`no menu row at index ${index}`);
  return found;
}

describe("Menu", () => {
  it("shows the current value on its trigger without opening", () => {
    render(<Harness />);

    expect(screen.getByRole("button", { name: /depth/i })).toHaveTextContent("Standard");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("opens on click and marks only the current option as chosen", () => {
    render(<Harness />);

    const menu = openMenu();
    expect(within(menu).getAllByRole("menuitemradio")).toHaveLength(2);
    expect(row(0)).toHaveAttribute("aria-checked", "true");
    // Asserting only the positive would pass even if every row were marked chosen.
    expect(row(1)).toHaveAttribute("aria-checked", "false");
  });

  it("shows each option's description, not just its label", () => {
    render(<Harness />);

    const menu = openMenu();
    expect(within(menu).getByText(/fewer sources, faster build/i)).toBeInTheDocument();
  });

  it("picks an option, writes it back to the trigger, and closes", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);

    const menu = openMenu();
    fireEvent.click(within(menu).getByRole("menuitemradio", { name: /thorough/i }));

    expect(onChange).toHaveBeenCalledWith("thorough");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /depth/i })).toHaveTextContent("Thorough");
  });

  // ─── Keyboard. The mockup was mouse-only; this is the part that has to be built. ─────────────

  it("opens with the keyboard and lands focus on the current option", () => {
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: /depth/i });
    trigger.focus();

    fireEvent.keyDown(trigger, { key: "ArrowDown" });

    expect(row(0)).toHaveFocus();
  });

  it("moves through options with the arrow keys and wraps", () => {
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: /depth/i });
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "ArrowDown" });

    fireEvent.keyDown(row(0), { key: "ArrowDown" });
    expect(row(1)).toHaveFocus();

    // Past the end, back to the top: a menu is a ring, not a dead end.
    fireEvent.keyDown(row(1), { key: "ArrowDown" });
    expect(row(0)).toHaveFocus();

    fireEvent.keyDown(row(0), { key: "ArrowUp" });
    expect(row(1)).toHaveFocus();
  });

  it("jumps to the first and last option with Home and End", () => {
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: /depth/i });
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "ArrowDown" });

    fireEvent.keyDown(row(0), { key: "End" });
    expect(row(1)).toHaveFocus();

    fireEvent.keyDown(row(1), { key: "Home" });
    expect(row(0)).toHaveFocus();
  });

  it("closes on Escape and returns focus to the trigger", () => {
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: /depth/i });
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "ArrowDown" });

    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });

    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    // Losing focus to the page body after closing strands a keyboard user.
    expect(trigger).toHaveFocus();
  });

  it("chooses the focused option with Enter", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const trigger = screen.getByRole("button", { name: /depth/i });
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "ArrowDown" });

    fireEvent.keyDown(row(0), { key: "ArrowDown" });
    fireEvent.keyDown(row(1), { key: "Enter" });

    expect(onChange).toHaveBeenCalledWith("thorough");
    expect(trigger).toHaveFocus();
  });

  it("closes when the surrounding page is clicked", () => {
    render(<Harness />);
    openMenu();

    fireEvent.mouseDown(document.body);

    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("reports its expanded state on the trigger", () => {
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: /depth/i });

    expect(trigger).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
  });

  // ─── Variants ────────────────────────────────────────────────────────────────────────────────

  it("falls back to the first option when the value is not one of them", () => {
    // A stored preference can outlive the option that produced it. Showing a blank chip would be
    // worse than showing the default it will actually build with.
    render(<Menu label="Depth" value="retired" options={OPTIONS} onChange={vi.fn()} />);

    expect(screen.getByRole("button", { name: /depth/i })).toHaveTextContent("Standard");
  });

  it("still opens and chooses when there is only one option", () => {
    const onChange = vi.fn();
    const single = [OPTIONS[0]!];
    render(<Menu label="Depth" value="standard" options={single} onChange={onChange} />);

    const trigger = screen.getByRole("button", { name: /depth/i });
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "ArrowDown" });

    // A one-item ring wraps onto itself rather than dividing by zero or losing focus.
    const only = within(screen.getByRole("menu")).getByRole("menuitemradio");
    expect(only).toHaveFocus();
    fireEvent.keyDown(only, { key: "ArrowDown" });
    expect(only).toHaveFocus();

    fireEvent.keyDown(only, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith("standard");
  });

  it("closes one menu when another opens, so two panels never overlap", () => {
    render(
      <>
        <Menu label="Depth" value="standard" options={OPTIONS} onChange={vi.fn()} />
        <Menu label="Level" value="standard" options={OPTIONS} onChange={vi.fn()} />
      </>,
    );

    fireEvent.click(screen.getByRole("button", { name: /depth/i }));
    expect(screen.getByRole("menu", { name: "Depth" })).toBeInTheDocument();

    // Pressing the second trigger dismisses the first through the outside-press path.
    fireEvent.mouseDown(screen.getByRole("button", { name: /level/i }));
    fireEvent.click(screen.getByRole("button", { name: /level/i }));

    expect(screen.queryByRole("menu", { name: "Depth" })).not.toBeInTheDocument();
    expect(screen.getByRole("menu", { name: "Level" })).toBeInTheDocument();
  });

  it("renders a footer group below a separator when one is given", () => {
    render(
      <Menu
        label="Depth"
        value="standard"
        options={OPTIONS}
        onChange={vi.fn()}
        footer={<button type="button">Trusted domains</button>}
      />,
    );

    openMenu();

    expect(screen.getByRole("button", { name: /trusted domains/i })).toBeInTheDocument();
  });

  it("closes on Tab and lets focus move on, rather than trapping it in an open panel", () => {
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: /depth/i });
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "ArrowDown" });

    fireEvent.keyDown(row(0), { key: "Tab" });

    // A menu whose rows are native tab stops would leave the panel open while focus walked away.
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("makes only the chosen option a tab stop", () => {
    render(<Harness />);
    openMenu();

    expect(row(0)).toHaveAttribute("tabindex", "0");
    expect(row(1)).toHaveAttribute("tabindex", "-1");
  });
});

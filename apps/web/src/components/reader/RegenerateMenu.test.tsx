import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RegenerateMenu } from "./RegenerateMenu";

describe("RegenerateMenu", () => {
  it("opens to only the available modes and reports the chosen one", () => {
    const onSelect = vi.fn();
    render(<RegenerateMenu available={["fresh", "simpler"]} onSelect={onSelect} />);

    // Closed: no menu, no items.
    expect(screen.queryByRole("menu")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /regenerate/i }));
    expect(screen.getByRole("menu")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /fresh take/i })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: /simpler/i })).toBeInTheDocument();
    // The reuse modes weren't offered here (a failed video has no contract to reuse).
    expect(screen.queryByRole("menuitem", { name: /^retry/i })).toBeNull();
    expect(screen.queryByRole("menuitem", { name: /add narration/i })).toBeNull();

    fireEvent.click(screen.getByRole("menuitem", { name: /simpler/i }));
    expect(onSelect).toHaveBeenCalledWith("simpler");
    // Selecting closes the menu.
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("moves focus between items with the arrow keys", () => {
    render(<RegenerateMenu available={["retry", "simpler", "fresh"]} onSelect={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /regenerate/i }));

    const retry = screen.getByRole("menuitem", { name: /^retry/i });
    const simpler = screen.getByRole("menuitem", { name: /^simpler/i });
    const fresh = screen.getByRole("menuitem", { name: /fresh take/i });
    expect(retry).toHaveFocus(); // opens onto the first item

    fireEvent.keyDown(retry, { key: "ArrowDown" });
    expect(simpler).toHaveFocus();
    fireEvent.keyDown(simpler, { key: "End" });
    expect(fresh).toHaveFocus();
    fireEvent.keyDown(fresh, { key: "ArrowDown" }); // wraps to the first
    expect(retry).toHaveFocus();
  });

  it("closes on Escape without selecting", () => {
    const onSelect = vi.fn();
    render(<RegenerateMenu available={["fresh"]} onSelect={onSelect} />);

    fireEvent.click(screen.getByRole("button", { name: /regenerate/i }));
    fireEvent.keyDown(screen.getByRole("menuitem", { name: /fresh take/i }), { key: "Escape" });

    expect(screen.queryByRole("menu")).toBeNull();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("disables the trigger and announces progress while busy", () => {
    render(<RegenerateMenu available={["fresh"]} onSelect={vi.fn()} busy />);
    const trigger = screen.getByRole("button", { name: /regenerating/i });
    expect(trigger).toBeDisabled();
  });

  it("uses a custom trigger label and renders nothing with no modes", () => {
    const { container, rerender } = render(
      <RegenerateMenu available={["fresh"]} onSelect={vi.fn()} triggerLabel="Try again" />,
    );
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();

    rerender(<RegenerateMenu available={[]} onSelect={vi.fn()} triggerLabel="Try again" />);
    expect(container).toBeEmptyDOMElement();
  });
});

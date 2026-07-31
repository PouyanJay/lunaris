import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MenuPanel } from "./MenuPanel";

function Harness() {
  return (
    <MenuPanel label="For you" value="Personalize">
      {(close) => (
        <div>
          <p>panel body</p>
          <button type="button" onClick={close}>
            Done
          </button>
        </div>
      )}
    </MenuPanel>
  );
}

function trigger() {
  return screen.getByRole("button", { name: /personalize/i });
}

describe("MenuPanel", () => {
  it("opens on click and reports its state on the trigger", () => {
    render(<Harness />);

    expect(trigger()).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(trigger());

    expect(trigger()).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("dialog", { name: /for you/i })).toBeInTheDocument();
  });

  it("shows the key alongside the value only once something is set", () => {
    // An unset chip is an invitation and reads as one word; a set chip has to say what it is the
    // value OF, or the bar is a row of bare words.
    const { rerender } = render(
      <MenuPanel label="For you" value="Personalize">
        {() => null}
      </MenuPanel>,
    );
    expect(trigger()).not.toHaveTextContent("For you");

    rerender(
      <MenuPanel label="For you" value="Tailored" set>
        {() => null}
      </MenuPanel>,
    );
    expect(screen.getByRole("button", { name: /tailored/i })).toHaveTextContent("For you");
  });

  // ─── Dismissal. Every route out of the panel, because a panel that cannot be closed is a trap. ──

  it("closes on Escape and returns focus to the trigger", () => {
    render(<Harness />);
    fireEvent.click(trigger());

    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger()).toHaveFocus();
  });

  it("closes when the surrounding page is pressed", () => {
    render(<Harness />);
    fireEvent.click(trigger());

    fireEvent.mouseDown(document.body);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("stays open when the panel's own content is pressed", () => {
    // The outside-press listener sits on the document, so it has to exclude the panel itself or
    // interacting with the form inside would dismiss it.
    render(<Harness />);
    fireEvent.click(trigger());

    fireEvent.mouseDown(screen.getByText("panel body"));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("closes from its own content's close callback", () => {
    render(<Harness />);
    fireEvent.click(trigger());

    fireEvent.click(screen.getByRole("button", { name: "Done" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger()).toHaveFocus();
  });

  it("toggles shut when the trigger is pressed again", () => {
    render(<Harness />);
    fireEvent.click(trigger());
    fireEvent.click(trigger());

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

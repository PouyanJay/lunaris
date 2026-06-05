import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { Switch } from "./Switch";

describe("Switch", () => {
  it("exposes role=switch with aria-checked reflecting state", () => {
    render(<Switch checked={false} onChange={() => {}} aria-label="Tracing" />);
    expect(screen.getByRole("switch", { name: "Tracing" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
  });

  it("toggles on click", () => {
    function Harness() {
      const [on, setOn] = useState(false);
      return <Switch checked={on} onChange={setOn} aria-label="Tracing" />;
    }
    render(<Harness />);
    const sw = screen.getByRole("switch", { name: "Tracing" });

    fireEvent.click(sw);
    expect(sw).toHaveAttribute("aria-checked", "true");
    fireEvent.click(sw);
    expect(sw).toHaveAttribute("aria-checked", "false");
  });

  it("forwards aria-labelledby to the button", () => {
    render(
      <>
        <span id="lbl">Tracing</span>
        <Switch checked={false} onChange={() => {}} aria-labelledby="lbl" />
      </>,
    );
    expect(screen.getByRole("switch", { name: "Tracing" })).toHaveAttribute(
      "aria-labelledby",
      "lbl",
    );
  });

  it("does not fire onChange when disabled", () => {
    const onChange = vi.fn();
    render(<Switch checked={false} onChange={onChange} disabled aria-label="Tracing" />);
    fireEvent.click(screen.getByRole("switch", { name: "Tracing" }));
    expect(onChange).not.toHaveBeenCalled();
  });
});

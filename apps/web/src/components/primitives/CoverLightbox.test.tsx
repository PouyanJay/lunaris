import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CoverLightbox } from "./CoverLightbox";

const URL = "https://signed/cover.png";

describe("CoverLightbox", () => {
  it("shows the full-size cover in an accessible modal", () => {
    render(<CoverLightbox imageUrl={URL} topic="How HTTPS works" onClose={() => {}} />);

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    // At full size the cover IS the content, so it carries the topic as alt text (not decorative).
    expect(screen.getByRole("img", { name: "How HTTPS works" })).toHaveAttribute("src", URL);
    // Focus lands on the close button, so a keyboard user can dismiss immediately (WCAG 2.2).
    expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
  });

  it("closes on Escape", () => {
    const onClose = vi.fn();
    render(<CoverLightbox imageUrl={URL} topic="t" onClose={onClose} />);

    fireEvent.keyDown(window, { key: "Escape" });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes on a backdrop click but not on a click inside the dialog", () => {
    const onClose = vi.fn();
    const { container } = render(<CoverLightbox imageUrl={URL} topic="t" onClose={onClose} />);

    fireEvent.mouseDown(screen.getByRole("dialog"));
    expect(onClose).not.toHaveBeenCalled();

    const backdrop = screen.getByRole("dialog").parentElement!;
    fireEvent.mouseDown(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(container).toBeTruthy();
  });

  it("closes on the Close button", () => {
    const onClose = vi.fn();
    render(<CoverLightbox imageUrl={URL} topic="t" onClose={onClose} />);

    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Callout } from "./Callout";

describe("Callout", () => {
  it("labels the panel with its variant word (never colour alone)", () => {
    render(<Callout variant="key-takeaway">HTTPS = HTTP + TLS.</Callout>);
    const panel = screen.getByRole("complementary", { name: "Key takeaway" });
    expect(panel).toHaveAttribute("data-variant", "key-takeaway");
    expect(panel).toHaveTextContent("HTTPS = HTTP + TLS.");
  });

  it("falls back to note for an unknown model-emitted variant", () => {
    render(<Callout variant="celebration">Confetti!</Callout>);
    expect(screen.getByRole("complementary", { name: "Note" })).toHaveAttribute(
      "data-variant",
      "note",
    );
  });

  it("renders a trailing action inside the panel", () => {
    render(<Callout action={<button>Explain</button>}>Body</Callout>);
    const panel = screen.getByRole("complementary", { name: "Note" });
    const action = screen.getByRole("button", { name: "Explain" });
    expect(panel).toContainElement(action);
  });
});

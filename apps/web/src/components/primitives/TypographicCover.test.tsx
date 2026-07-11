import { render } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { TypographicCover } from "./TypographicCover";
import { coverWord } from "../../lib/coverWord";

describe("coverWord", () => {
  it("picks the longest content word, skipping stopwords", () => {
    expect(coverWord("How HTTPS works")).toBe("HTTPS");
    expect(coverWord("The Foundations of Thermodynamics")).toBe("Thermodynamics");
  });

  it("falls back to the first word when every word is a stopword", () => {
    expect(coverWord("how to")).toBe("how");
  });

  it("survives an empty or whitespace topic without throwing", () => {
    expect(coverWord("   ")).toBe("");
    expect(coverWord("")).toBe("");
  });
});

describe("TypographicCover", () => {
  it("renders the salient topic word as the ghosted display word", () => {
    const { container } = render(<TypographicCover topic="How HTTPS works" seed={7} />);
    expect(container.textContent).toContain("HTTPS");
  });

  it("is deterministic for a given seed + topic (same cover across sessions)", () => {
    const a = renderToStaticMarkup(<TypographicCover topic="Photosynthesis" seed={3} />);
    const b = renderToStaticMarkup(<TypographicCover topic="Photosynthesis" seed={3} />);
    expect(a).toBe(b);
  });

  it("is decorative (aria-hidden — the adjacent title carries the name)", () => {
    const { container } = render(<TypographicCover topic="Networking" seed={1} />);
    expect(container.querySelector("[aria-hidden='true']")).not.toBeNull();
  });
});

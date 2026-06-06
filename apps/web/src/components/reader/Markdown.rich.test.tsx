import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Markdown } from "./Markdown";

describe("Markdown — rich blocks", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders a :::note directive as a labelled callout", () => {
    render(<Markdown>{":::note\nMind the gap **here**.\n:::"}</Markdown>);

    const callout = screen.getByRole("complementary", { name: "Note" });
    expect(callout).toHaveAttribute("data-variant", "note");
    expect(callout.querySelector("strong")?.textContent).toBe("here");
  });

  it("lifts a 'Tip:' lead-in paragraph into a tip callout and drops the label text", () => {
    render(<Markdown>{"Tip: warm up the cache before measuring."}</Markdown>);

    const callout = screen.getByRole("complementary", { name: "Tip" });
    expect(callout).toHaveAttribute("data-variant", "tip");
    expect(callout.textContent).toContain("warm up the cache");
    // The recognised "Tip:" lead-in is consumed, not shown in the body.
    expect(callout.querySelector("[class*='body']")?.textContent).not.toContain("Tip:");
  });

  it("renders a glossary term with a focus-revealed definition tooltip", () => {
    render(
      <Markdown>{'A :term[morpheme]{title="the smallest unit of meaning"} matters.'}</Markdown>,
    );

    const term = screen.getByRole("button", { name: "morpheme" });
    expect(screen.getByRole("tooltip", { hidden: true })).toHaveTextContent(
      "the smallest unit of meaning",
    );

    fireEvent.focus(term);
    expect(screen.getByRole("tooltip")).toBeVisible();
    expect(term).toHaveAttribute("aria-describedby");
  });

  it("renders a :::details block as a native disclosure", () => {
    render(<Markdown>{":::details[Show the proof]\nBecause it follows.\n:::"}</Markdown>);

    const summary = screen.getByText("Show the proof");
    expect(summary.tagName).toBe("SUMMARY");
    expect(summary.closest("details")).not.toBeNull();
  });

  it("renders a fenced code block with a language label and a working copy button", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });

    render(<Markdown>{"```js\nconst x = 1;\n```"}</Markdown>);

    expect(screen.getByText("js")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith("const x = 1;"));
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("renders a html-preview fence inside a script-free sandboxed iframe", () => {
    render(<Markdown>{"```html-preview\n<p>hello</p>\n```"}</Markdown>);

    const frame = screen.getByTitle("HTML preview") as HTMLIFrameElement;
    expect(frame.tagName).toBe("IFRAME");
    // sandbox carries no allow-scripts token → the snippet is inert.
    expect(frame.getAttribute("sandbox")).toBe("");
    expect(frame).toHaveAttribute("srcdoc", expect.stringContaining("<p>hello</p>"));
  });

  it("renders inline and display math as KaTeX, not raw TeX", () => {
    const { container } = render(
      <Markdown>{"Energy $E=mc^2$ and\n\n$$\n\\int_0^1 x\\,dx\n$$"}</Markdown>,
    );

    expect(container.querySelector(".katex")).not.toBeNull();
    expect(container.querySelector(".katex-display")).not.toBeNull();
    // KaTeX typesets the TeX into positioned glyphs (keeping the source only in the MathML
    // annotation for assistive tech) — so the rendered HTML layer carries no literal `$`.
    expect(container.querySelector(".katex-html")?.textContent).not.toContain("$");
  });

  it("strips dangerous raw HTML while keeping the rich pipeline", () => {
    const { container } = render(
      <Markdown>{":::tip\nStay safe <script>alert(1)</script>\n:::"}</Markdown>,
    );

    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByRole("complementary", { name: "Tip" })).toBeInTheDocument();
  });
});

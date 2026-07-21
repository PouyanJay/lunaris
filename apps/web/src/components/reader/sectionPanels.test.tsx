import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ASTHMA_PROSE } from "./lessonProse.fixture";
import { Markdown } from "./Markdown";

/** R7 — a section labelled WORKED EXAMPLE / WORKED ATTRIBUTION is wrapped in a bordered panel that
 *  sets the concrete instance apart from the general explanation; its inner lifts (R3 flow, R4 keyed
 *  list) ride inside. Ordinary sections (STRATEGY, …) are not panelled. */
describe("example / attribution panels (R7)", () => {
  it("wraps the worked-example section (with its flow) in a panel", () => {
    render(<Markdown>{ASTHMA_PROSE}</Markdown>);

    const heading = screen.getByRole("heading", { name: /worked example/i });
    const panel = heading.closest("section");
    expect(panel).not.toBeNull();
    // The arrow-chain flow lives inside the same panel.
    expect(within(panel as HTMLElement).getByRole("list", { name: /step chain/i })).toBeInTheDocument();
  });

  it("wraps the worked-attribution section (with its keyed list) in a panel", () => {
    render(<Markdown>{ASTHMA_PROSE}</Markdown>);

    const heading = screen.getByRole("heading", { name: /worked attribution/i });
    const panel = heading.closest("section");
    expect(panel).not.toBeNull();
    expect(within(panel as HTMLElement).getAllByRole("term").length).toBeGreaterThanOrEqual(2);
  });

  it("does not panel an ordinary section like STRATEGY", () => {
    render(<Markdown>{ASTHMA_PROSE}</Markdown>);
    const heading = screen.getByRole("heading", { name: /^strategy$/i });
    expect(heading.closest("section")).toBeNull();
  });
});

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CourseScope } from "../../types/course";
import { ScopeBand } from "./ScopeBand";

function makeScope(overrides: Partial<CourseScope> = {}): CourseScope {
  return {
    effort: "About 4-9 weeks of self-paced study (~20-35 hours).",
    delivers: ["A structured understanding of X.", "5 modules sequenced by prerequisite."],
    excludes: ["It will not certify you."],
    ...overrides,
  };
}

describe("ScopeBand", () => {
  it("renders the effort/timeline band as a labelled region", () => {
    render(<ScopeBand scope={makeScope()} />);
    const band = screen.getByRole("region", { name: /course scope/i });
    expect(
      within(band).getByText("About 4-9 weeks of self-paced study (~20-35 hours)."),
    ).toBeInTheDocument();
  });

  it("lists what the course delivers under a 'what you'll get' group", () => {
    render(<ScopeBand scope={makeScope()} />);
    const gets = screen.getByRole("group", { name: /what you'll get/i });
    expect(within(gets).getByText("A structured understanding of X.")).toBeInTheDocument();
    expect(within(gets).getByText("5 modules sequenced by prerequisite.")).toBeInTheDocument();
  });

  it("lists the honest exclusions under a separate 'what it won't' group", () => {
    render(<ScopeBand scope={makeScope()} />);
    const wont = screen.getByRole("group", { name: /what it won't/i });
    expect(within(wont).getByText("It will not certify you.")).toBeInTheDocument();
  });

  it("omits the exclusions group when there are no exclusions", () => {
    render(<ScopeBand scope={makeScope({ excludes: [] })} />);
    expect(screen.queryByRole("group", { name: /what it won't/i })).not.toBeInTheDocument();
    // The delivers group still renders.
    expect(screen.getByRole("group", { name: /what you'll get/i })).toBeInTheDocument();
  });

  it("omits the delivers group when there is nothing to deliver", () => {
    render(<ScopeBand scope={makeScope({ delivers: [] })} />);
    expect(screen.queryByRole("group", { name: /what you'll get/i })).not.toBeInTheDocument();
  });

  it("omits the effort line but keeps the band when effort is unknown", () => {
    render(<ScopeBand scope={makeScope({ effort: "" })} />);
    expect(screen.getByRole("region", { name: /course scope/i })).toBeInTheDocument();
    expect(screen.queryByText(/weeks/i)).not.toBeInTheDocument();
  });

  it("renders an effort-only band with no groups when both lists are empty", () => {
    render(<ScopeBand scope={makeScope({ delivers: [], excludes: [] })} />);
    expect(screen.getByRole("region", { name: /course scope/i })).toBeInTheDocument();
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
  });

  it("does not convey meaning by colour alone — each list has a text-bearing heading", () => {
    render(<ScopeBand scope={makeScope()} />);
    // The group accessible names come from visible headings, not colour.
    expect(screen.getByText(/what you'll get/i)).toBeInTheDocument();
    expect(screen.getByText(/what it won't/i)).toBeInTheDocument();
  });
});

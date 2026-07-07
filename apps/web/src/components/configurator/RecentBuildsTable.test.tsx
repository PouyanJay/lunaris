import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { RecentBuildsTable } from "./RecentBuildsTable";
import { makeRun } from "../../test/fixtures";

function renderTable(runs = [makeRun()]) {
  render(
    <MemoryRouter>
      <RecentBuildsTable runs={runs} />
    </MemoryRouter>,
  );
}

describe("RecentBuildsTable", () => {
  it("renders nothing when there are no builds yet", () => {
    const { container } = render(
      <MemoryRouter>
        <RecentBuildsTable runs={[]} />
      </MemoryRouter>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("lists each build with a linked topic, structure, status, and time", () => {
    renderTable([
      makeRun({ id: "c-1", topic: "How HTTPS works", kcCount: 15, moduleCount: 4 }),
    ]);

    const row = screen.getByRole("row", { name: /how https works/i });
    // The topic is a real link into the course/build canvas (Cmd/middle-click works).
    const link = within(row).getByRole("link", { name: "How HTTPS works" });
    expect(link).toHaveAttribute("href", "/courses/c-1");
    // Structure reads from the run summary (KCs · modules) as mono data.
    expect(within(row).getByText("15 KCs · 4 modules")).toBeInTheDocument();
    // The house status convention: a dot + uppercase-mono label.
    expect(within(row).getByText("COMPLETED")).toBeInTheDocument();
  });

  it("caps the table at the six most-recent builds", () => {
    const runs = Array.from({ length: 8 }, (_, i) =>
      makeRun({ id: `c-${i}`, runId: `r-${i}`, topic: `Course ${i}` }),
    );
    renderTable(runs);

    // Header row + 6 build rows.
    expect(screen.getAllByRole("row")).toHaveLength(7);
  });

  it("singularises a one-KC, one-module build", () => {
    renderTable([makeRun({ topic: "Tiny", kcCount: 1, moduleCount: 1 })]);
    expect(screen.getByText("1 KC · 1 module")).toBeInTheDocument();
  });
});

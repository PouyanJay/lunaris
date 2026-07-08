import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeCourse, makeProgressEvent } from "../../test/fixtures";
import { BuildMetricBand } from "./BuildMetricBand";

describe("BuildMetricBand", () => {
  it("renders nothing until the graph exists — no placeholder zeros", () => {
    render(<BuildMetricBand events={[makeProgressEvent("concepts_extracted", 0)]} />);

    expect(screen.queryByLabelText("Graph metrics")).not.toBeInTheDocument();
  });

  it("reads KCS / EDGES / ACYCLIC off the latest graph event", () => {
    render(
      <BuildMetricBand
        events={[
          makeProgressEvent("graph_built", 1, {
            kcCount: 21,
            edgeCount: 27,
            graph: makeCourse().graph,
          }),
        ]}
      />,
    );

    const band = screen.getByLabelText("Graph metrics");
    expect(band).toHaveTextContent("KCS");
    expect(band).toHaveTextContent("21");
    expect(band).toHaveTextContent("27");
    expect(band).toHaveTextContent("yes");
  });

  it("states a cyclic graph plainly — the moat's failure is never dressed up", () => {
    const graph = { ...makeCourse().graph, isAcyclic: false };
    render(
      <BuildMetricBand
        events={[makeProgressEvent("graph_built", 1, { kcCount: 3, edgeCount: 2, graph })]}
      />,
    );

    expect(screen.getByLabelText("Graph metrics")).toHaveTextContent("no");
  });

  it("answers ACYCLIC with an em dash when the stream predates the structured payload", () => {
    render(
      <BuildMetricBand events={[makeProgressEvent("graph_built", 1, { kcCount: 3, edgeCount: 2 })]} />,
    );

    expect(screen.getByLabelText("Graph metrics")).toHaveTextContent("—");
  });
});

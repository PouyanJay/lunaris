import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeCourse } from "../../test/fixtures";
import { PrereqGraphExplorer } from "./PrereqGraphExplorer";

/** Drive useMediaQuery: report the phone breakpoint as (un)matched so the explorer picks its layout. */
function setViewport(isPhone: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: isPhone && query.includes("max-width: 768px"),
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    })),
  );
}

afterEach(() => vi.unstubAllGlobals());

/** The React Flow `<Panel>` wrapping the difficulty legend (position lands as `top`/`bottom` classes). */
function legendPanel(container: HTMLElement): HTMLElement | null {
  return container.querySelector('[class*="legend"]')?.closest(".react-flow__panel") ?? null;
}

describe("PrereqGraphExplorer responsive chrome", () => {
  it("docks the legend at the bottom and shows the minimap on desktop", async () => {
    setViewport(false);
    const { container } = render(<PrereqGraphExplorer course={makeCourse()} />);

    await waitFor(() => expect(legendPanel(container)?.classList.contains("bottom")).toBe(true));
    expect(container.querySelector(".react-flow__minimap")).toBeInTheDocument();
  });

  it("drops the minimap and lifts the legend to the top on phones", async () => {
    setViewport(true);
    const { container } = render(<PrereqGraphExplorer course={makeCourse()} />);

    await waitFor(() => expect(legendPanel(container)?.classList.contains("top")).toBe(true));
    expect(container.querySelector(".react-flow__minimap")).not.toBeInTheDocument();
  });
});

describe("PrereqGraphExplorer mastery overlay", () => {
  it("keeps the open inspector when the mastery snapshot lands", async () => {
    // A learner can select a concept before the progress fetch resolves — the snapshot landing
    // recomputes badges/edges but must not close the inspector under them.
    setViewport(false);
    const course = makeCourse();
    const { container, rerender } = render(
      <PrereqGraphExplorer course={course} kcMastery={null} />,
    );

    fireEvent.click(container.querySelector('[data-id="sorted_order"]')!);
    expect(await screen.findByRole("heading", { name: "Sorted Order" })).toBeInTheDocument();

    rerender(<PrereqGraphExplorer course={course} kcMastery={{ comparison: true }} />);

    // The inspector survives, and the node under it now announces the fresh state.
    expect(screen.getByRole("heading", { name: "Sorted Order" })).toBeInTheDocument();
    await waitFor(() =>
      expect(container.querySelector('[aria-label*="Up next."]')).not.toBeNull(),
    );
  });

  it("re-seeding on a course change still drops the selection", async () => {
    setViewport(false);
    const { container, rerender } = render(
      <PrereqGraphExplorer course={makeCourse()} kcMastery={null} />,
    );
    fireEvent.click(container.querySelector('[data-id="sorted_order"]')!);
    await screen.findByRole("heading", { name: "Sorted Order" });

    rerender(<PrereqGraphExplorer course={makeCourse()} kcMastery={null} />);

    await waitFor(() =>
      expect(screen.queryByRole("heading", { name: "Sorted Order" })).not.toBeInTheDocument(),
    );
  });
});

import { render, waitFor } from "@testing-library/react";
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

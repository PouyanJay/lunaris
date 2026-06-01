import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LunarSpinner } from "./LunarSpinner";

describe("LunarSpinner", () => {
  it("renders a decorative moon sized to the size prop", () => {
    render(<LunarSpinner size={20} />);

    const moon = screen.getByTestId("lunar-spinner");
    // Decorative: the text status carries the meaning for screen readers, not the icon.
    expect(moon).toHaveAttribute("aria-hidden", "true");
    expect(moon).toHaveStyle({ width: "20px", height: "20px" });
  });

  it("defaults to a 13px diameter", () => {
    render(<LunarSpinner />);

    expect(screen.getByTestId("lunar-spinner")).toHaveStyle({ width: "13px", height: "13px" });
  });
});

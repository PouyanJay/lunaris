import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ComposerFeatures } from "./ComposerFeatures";

describe("ComposerFeatures", () => {
  it("renders three informational cards under a labelled list", () => {
    render(<ComposerFeatures />);

    expect(screen.getByRole("list", { name: /what a lunaris build does/i })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    expect(screen.getByRole("heading", { name: /verified against real sources/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /prerequisites mapped first/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /watch it build/i })).toBeInTheDocument();
  });
});

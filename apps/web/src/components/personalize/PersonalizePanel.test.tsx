import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeBriefResponse } from "../../test/fixtures";
import { PersonalizePanel } from "./PersonalizePanel";

function stubFetch(response: { ok: boolean; status?: number; json: () => Promise<unknown> }) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
}

afterEach(() => vi.unstubAllGlobals());

describe("PersonalizePanel", () => {
  it("pre-picks the inference, then builds with the confirmed clarification", async () => {
    stubFetch({ ok: true, json: async () => makeBriefResponse() });
    const onConfirm = vi.fn();
    render(
      <PersonalizePanel
        apiBaseUrl="http://test"
        topic="english"
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );

    // Ready once the brief resolves; the inferred goal is shown and the inferred level pre-checked.
    await screen.findByText(/reach CLB 10/i);
    expect(screen.getByRole("radio", { name: /intermediate/i })).toBeChecked();

    // Adjust the level and add prior knowledge, then build.
    fireEvent.click(screen.getByRole("radio", { name: /advanced/i }));
    fireEvent.change(screen.getByLabelText(/already comfortable with/i), {
      target: { value: "solid grammar" },
    });
    fireEvent.click(screen.getByRole("button", { name: /build course/i }));

    expect(onConfirm).toHaveBeenCalledWith("english", {
      targetLevel: "advanced",
      detailDepth: "balanced",
      languageStyle: "balanced",
      assumedKnown: "solid grammar",
    });
  });

  it("confirming the inference verbatim sends only the no-op choice overrides", async () => {
    stubFetch({ ok: true, json: async () => makeBriefResponse() });
    const onConfirm = vi.fn();
    render(
      <PersonalizePanel
        apiBaseUrl="http://test"
        topic="english"
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: /build course/i }));

    // No text typed → no assumedKnown/background; the choices ride along at the inferred values.
    expect(onConfirm).toHaveBeenCalledWith("english", {
      targetLevel: "intermediate",
      detailDepth: "balanced",
      languageStyle: "balanced",
    });
  });

  it("shows a retryable error when the brief fetch fails", async () => {
    stubFetch({ ok: false, status: 500, json: async () => ({}) });
    render(
      <PersonalizePanel
        apiBaseUrl="http://test"
        topic="english"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("cancels without building", async () => {
    stubFetch({ ok: true, json: async () => makeBriefResponse() });
    const onCancel = vi.fn();
    render(
      <PersonalizePanel
        apiBaseUrl="http://test"
        topic="english"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    );

    await screen.findByText(/reach CLB 10/i);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onCancel).toHaveBeenCalled();
  });
});

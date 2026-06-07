import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeBriefResponse } from "../../test/fixtures";
import { IdleCourseSetup } from "./IdleCourseSetup";

function stubFetch(response: { ok: boolean; status?: number; json: () => Promise<unknown> }) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
}

function renderSetup(overrides: Partial<React.ComponentProps<typeof IdleCourseSetup>> = {}) {
  const props: React.ComponentProps<typeof IdleCourseSetup> = {
    apiBaseUrl: "http://test",
    onGenerate: vi.fn(),
    onOpenSettings: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<IdleCourseSetup {...props} />) };
}

afterEach(() => vi.unstubAllGlobals());

describe("IdleCourseSetup", () => {
  it("renders the topic form beside the persistent course-setup rail", () => {
    renderSetup();

    expect(screen.getByRole("heading", { name: /what do you want to learn/i })).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: /course setup/i })).toBeInTheDocument();
  });

  it("builds in one click with no personalization and the default depth", () => {
    const onGenerate = vi.fn();
    renderSetup({ onGenerate });

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "binary search" } });
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    expect(onGenerate).toHaveBeenCalledWith("binary search", undefined, "standard");
  });

  it("threads the confirmed clarifier into the build when the learner personalizes", async () => {
    stubFetch({ ok: true, json: async () => makeBriefResponse() });
    const onGenerate = vi.fn();
    renderSetup({ onGenerate });

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "english" } });
    fireEvent.click(screen.getByRole("button", { name: /personalize this topic/i }));

    // Brief read → clarifier appears with the inference pre-picked; adjust the level, then build.
    await screen.findByText(/reach CLB 10/i);
    fireEvent.click(screen.getByRole("radio", { name: /advanced/i }));
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    expect(onGenerate).toHaveBeenCalledWith(
      "english",
      // Both the adjusted level and the inferred goal_type (R0) thread into the build.
      expect.objectContaining({ targetLevel: "advanced", goalType: "credential" }),
      "standard",
    );
  });

  it("invalidates a loaded brief when the topic changes, so stale answers can't build", async () => {
    stubFetch({ ok: true, json: async () => makeBriefResponse() });
    renderSetup();

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "english" } });
    fireEvent.click(screen.getByRole("button", { name: /personalize this topic/i }));
    await screen.findByText(/reach CLB 10/i);

    // Editing the topic drops the brief that was read for the old topic.
    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "spanish" } });

    expect(screen.queryByText(/reach CLB 10/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /personalize this topic/i })).toBeInTheDocument();
  });

  it("shows a retryable error when the brief read fails", async () => {
    stubFetch({ ok: false, status: 500, json: async () => ({}) });
    renderSetup();

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "english" } });
    fireEvent.click(screen.getByRole("button", { name: /personalize this topic/i }));

    // The alert carries the real cause, not just a generic "failed".
    expect(await screen.findByRole("alert")).toHaveTextContent(/http 500/i);
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("threads the chosen Thorough depth into the build", () => {
    const onGenerate = vi.fn();
    renderSetup({ onGenerate });

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "binary search" } });
    fireEvent.click(screen.getByRole("button", { name: /advanced/i }));
    fireEvent.click(screen.getByRole("radio", { name: /thorough/i }));
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    expect(onGenerate).toHaveBeenCalledWith("binary search", undefined, "thorough");
  });

  it("opens Settings from the operator pointer", () => {
    const onOpenSettings = vi.fn();
    renderSetup({ onOpenSettings });

    fireEvent.click(screen.getByRole("button", { name: /open settings/i }));

    expect(onOpenSettings).toHaveBeenCalledOnce();
  });

  it("collapses the rail to an edge tab and expands it again", () => {
    renderSetup();

    fireEvent.click(screen.getByRole("button", { name: /collapse course setup/i }));
    const reveal = screen.getByRole("button", { name: /show course setup/i });
    expect(reveal).toBeInTheDocument();

    fireEvent.click(reveal);
    expect(screen.queryByRole("button", { name: /show course setup/i })).not.toBeInTheDocument();
  });

  it("aborts an in-flight brief read when unmounted", () => {
    let captured: AbortSignal | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((_input: unknown, init?: RequestInit) => {
        captured = init?.signal ?? undefined;
        return new Promise<never>(() => {}); // never settles — the read is in-flight
      }),
    );
    const { unmount } = renderSetup();

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "english" } });
    fireEvent.click(screen.getByRole("button", { name: /personalize this topic/i }));
    expect(captured?.aborted).toBe(false);

    unmount();
    expect(captured?.aborted).toBe(true);
  });

  it("opens the setup drawer, closes it on Escape, and returns focus to the toggle", () => {
    renderSetup();
    const toggle = screen.getByRole("button", { name: /^course setup$/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: /close course setup overlay/i })).toBeInTheDocument();

    // Esc dismisses the drawer (WCAG 2.2) and restores focus to the control that opened it.
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveFocus();
  });

  it("closes the setup drawer when the scrim is clicked", () => {
    renderSetup();
    const toggle = screen.getByRole("button", { name: /^course setup$/i });

    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole("button", { name: /close course setup overlay/i }));

    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(
      screen.queryByRole("button", { name: /close course setup overlay/i }),
    ).not.toBeInTheDocument();
  });
});

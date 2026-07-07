import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HomeDashboard } from "./HomeDashboard";
import { makeCourseSummary } from "../../test/fixtures";

function json(body: unknown) {
  return { ok: true, json: async () => body };
}

function renderHome(props: Partial<Parameters<typeof HomeDashboard>[0]> = {}) {
  const onNewCourse = props.onNewCourse ?? vi.fn();
  render(
    <MemoryRouter>
      <HomeDashboard
        apiBaseUrl="http://test"
        userEmail="ada.lovelace@example.com"
        runs={[]}
        onNewCourse={onNewCourse}
        {...props}
      />
    </MemoryRouter>,
  );
  return onNewCourse;
}

describe("HomeDashboard", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("greets the signed-in learner by their derived name", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json([makeCourseSummary()])));

    renderHome();

    expect(
      await screen.findByRole("heading", { name: /good (morning|afternoon|evening), ada lovelace/i }),
    ).toBeInTheDocument();
  });

  it("falls back to a natural greeting when there is no signed-in email", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json([])));

    renderHome({ userEmail: null });

    expect(
      await screen.findByRole("heading", { name: /good (morning|afternoon|evening), there/i }),
    ).toBeInTheDocument();
  });

  it("shows a loading skeleton region while the library is in flight", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));

    renderHome();

    // The greeting renders immediately (no data dependency); the region below shows the skeleton.
    expect(screen.getByRole("heading", { name: /good (morning|afternoon|evening)/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/loading your courses/i)).toBeInTheDocument();
  });

  it("renders a recoverable error when the library fails to load", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 }));

    renderHome();

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("offers a first-run hero that funnels to the composer when there are no courses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json([])));

    const onNewCourse = renderHome();

    fireEvent.click(await screen.findByRole("button", { name: /new course/i }));
    expect(onNewCourse).toHaveBeenCalledOnce();
  });

  it("links to the full library once courses exist", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json([makeCourseSummary()])));

    renderHome();

    await waitFor(() =>
      expect(screen.getByRole("link", { name: /view all courses/i })).toHaveAttribute(
        "href",
        "/courses",
      ),
    );
  });
});

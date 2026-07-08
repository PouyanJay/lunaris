import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../../App";
import { makeCourse, makeRun, routedFetch } from "../../test/fixtures";

/** App-level: the palette is global chrome — proven through the real shell + shortcut + index. */
describe("command palette", () => {
  beforeEach(() => vi.stubEnv("VITE_API_URL", "http://test"));
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  function stubStudio() {
    vi.stubGlobal(
      "fetch",
      routedFetch({
        runs: [makeRun()],
        course: makeCourse(),
        library: [
          {
            id: "course-test",
            topic: "How binary search works",
            lessonTotal: 1,
            lessonsDone: 0,
            percent: 0,
            conceptTotal: 3,
            level: "beginner",
            learnerStatus: "not_started",
            courseStatus: "published",
            builtAt: "2026-07-01T00:00:00Z",
            lastOpenedAt: null,
          },
        ],
      }),
    );
  }

  it("opens with ⌘K, searches the index, and Enter lands on the picked concept", async () => {
    stubStudio();
    window.history.pushState(null, "", "/");
    render(<App />);
    await screen.findByRole("button", { name: /search \(⌘k\)/i });

    // Act — the global shortcut opens the palette; the lazy index builds on this first open.
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    const input = await screen.findByRole("combobox", { name: /search courses/i });
    await waitFor(() => expect(screen.queryByText(/indexing your courses/i)).toBeNull());
    fireEvent.change(input, { target: { value: "comparison" } });
    fireEvent.keyDown(input, { key: "Enter" });

    // Assert — a concept pick deep-links onto the course map with its inspector open.
    expect(window.location.pathname).toBe("/courses/course-test/map");
    expect(await screen.findByRole("heading", { name: "Comparison" })).toBeInTheDocument();
  });

  it("the topbar trigger opens it; Escape closes and restores focus to the trigger", async () => {
    stubStudio();
    window.history.pushState(null, "", "/");
    render(<App />);
    const trigger = await screen.findByRole("button", { name: /search \(⌘k\)/i });

    // Act — focus first: a real browser focuses a clicked button, jsdom doesn't.
    trigger.focus();
    fireEvent.click(trigger);
    const input = await screen.findByRole("combobox", { name: /search courses/i });
    await waitFor(() => expect(input).toHaveFocus());
    fireEvent.keyDown(window, { key: "Escape" });

    // Assert — the modal contract: focus returns to where it came from.
    expect(screen.queryByRole("dialog", { name: "Search" })).not.toBeInTheDocument();
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("says so when nothing matches — never a silent blank", async () => {
    stubStudio();
    window.history.pushState(null, "", "/");
    render(<App />);
    await screen.findByRole("button", { name: /search \(⌘k\)/i });

    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const input = await screen.findByRole("combobox", { name: /search courses/i });
    await waitFor(() => expect(screen.queryByText(/indexing your courses/i)).toBeNull());
    fireEvent.change(input, { target: { value: "zzzznothing" } });

    expect(await screen.findByText(/no matches for/i)).toBeInTheDocument();
  });

  it("arrow keys walk the results across group boundaries", async () => {
    stubStudio();
    window.history.pushState(null, "", "/");
    render(<App />);
    await screen.findByRole("button", { name: /search \(⌘k\)/i });

    fireEvent.keyDown(window, { key: "k", metaKey: true });
    const input = await screen.findByRole("combobox", { name: /search courses/i });
    await waitFor(() => expect(screen.queryByText(/indexing your courses/i)).toBeNull());
    // "binary" matches the course (prefix in title words) AND the KC "binary_search" label?
    fireEvent.change(input, { target: { value: "binary" } });
    const options = await screen.findAllByRole("option");
    expect(options.length).toBeGreaterThanOrEqual(2);
    expect(options[0]).toHaveAttribute("aria-selected", "true");

    // Act — step to the second option.
    fireEvent.keyDown(input, { key: "ArrowDown" });

    // Assert
    expect(options[1]).toHaveAttribute("aria-selected", "true");
    expect(input).toHaveAttribute("aria-activedescendant", options[1]?.id);
  });
});

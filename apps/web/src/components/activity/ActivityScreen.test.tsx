import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ActivityView } from "../../lib/activity";
import { ActivityScreen } from "./ActivityScreen";

const EMPTY_VIEW: ActivityView = {
  stats: { currentStreak: 0, longestStreak: 0, minutesThisWeek: 0, conceptsThisWeek: 0 },
  heat: [],
  week: [],
  feed: [],
};

function okResponse(view: ActivityView) {
  return Promise.resolve({ ok: true, json: async () => view });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ActivityScreen", () => {
  it("shows a loading skeleton while the snapshot is in flight", () => {
    // Arrange — a fetch that never resolves keeps the screen in its loading state.
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );

    // Act
    render(<ActivityScreen apiBaseUrl="http://test" onBrowseCourses={() => {}} />);

    // Assert
    expect(screen.getByLabelText(/loading activity/i)).toBeInTheDocument();
  });

  it("renders the designed empty state for a user with no history", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn(() => okResponse(EMPTY_VIEW)),
    );
    const onBrowseCourses = vi.fn();

    // Act
    render(<ActivityScreen apiBaseUrl="http://test" onBrowseCourses={onBrowseCourses} />);

    // Assert — honest empty state with a next step, never zero-tiles pretending to be data.
    expect(await screen.findByText(/no activity yet/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /browse my courses/i }));
    expect(onBrowseCourses).toHaveBeenCalled();
  });

  it("surfaces a fetch failure as a recoverable error state and retries", async () => {
    // Arrange — first load fails, the retry succeeds.
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new Error("network down"))
      .mockImplementation(() => okResponse(EMPTY_VIEW) as Promise<Response>);
    vi.stubGlobal("fetch", fetchMock);

    // Act
    render(<ActivityScreen apiBaseUrl="http://test" onBrowseCourses={() => {}} />);

    // Assert — error state offers recovery; retrying lands the empty state.
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByText(/no activity yet/i)).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it("renders recorded events in the feed", async () => {
    // Arrange
    const view: ActivityView = {
      ...EMPTY_VIEW,
      feed: [
        {
          eventType: "completed",
          courseId: "course-1",
          courseTitle: "How HTTPS works",
          lessonId: "m-1-l0",
          lessonTitle: "Certificates and authentication",
          kcId: null,
          kcLabel: null,
          occurredAt: new Date().toISOString(),
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(() => okResponse(view)),
    );

    // Act
    render(<ActivityScreen apiBaseUrl="http://test" onBrowseCourses={() => {}} />);

    // Assert — the walking-skeleton path: a stored row reaches the rendered feed.
    expect(await screen.findByText(/certificates and authentication/i)).toBeInTheDocument();
  });

  it("renders the full instrument: stat tiles, heat, week bars, and the grouped feed", async () => {
    // Arrange — a lived-in snapshot: 3-day streak, minutes on the last three days, one mastered
    // concept today and a started lesson yesterday.
    const today = new Date();
    const iso = (daysAgo: number) => {
      const d = new Date(today);
      d.setDate(d.getDate() - daysAgo);
      return d.toISOString().slice(0, 10);
    };
    const view: ActivityView = {
      stats: { currentStreak: 3, longestStreak: 11, minutesThisWeek: 142, conceptsThisWeek: 7 },
      heat: Array.from({ length: 14 }, (_, i) => ({
        date: iso(13 - i),
        minutes: i >= 11 ? 20 : 0,
        active: i >= 11,
      })),
      week: Array.from({ length: 7 }, (_, i) => ({ date: iso(6 - i), minutes: i === 6 ? 33 : 0 })),
      feed: [
        {
          eventType: "mastered",
          courseId: "course-1",
          courseTitle: "How HTTPS works",
          lessonId: null,
          lessonTitle: null,
          kcId: "kc-a",
          kcLabel: "TLS fundamentals",
          occurredAt: today.toISOString(),
        },
        {
          eventType: "started",
          courseId: "course-1",
          courseTitle: "How HTTPS works",
          lessonId: "m-1-l1",
          lessonTitle: "Lesson 2 · Fundamentals",
          kcId: null,
          kcLabel: null,
          // Yesterday NOON local — a fixed hours-ago offset would cross two local days when
          // the suite runs shortly after midnight.
          occurredAt: new Date(new Date(today).setHours(-12, 0, 0, 0)).toISOString(),
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(() => okResponse(view)),
    );

    // Act
    render(<ActivityScreen apiBaseUrl="http://test" onBrowseCourses={() => {}} />);

    // Assert — the four tiles, with their figures.
    expect(await screen.findByText("Current streak")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("Longest streak")).toBeInTheDocument();
    expect(screen.getByText("11")).toBeInTheDocument();
    expect(screen.getByText("142")).toBeInTheDocument();
    expect(screen.getByText("Concepts this week")).toBeInTheDocument();
    // Heat: honest studied-days caption + an accessible chart reading.
    expect(screen.getByText(/studied 3 of the last 14 days/i)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /last 14 days/i })).toBeInTheDocument();
    // Week bars: an accessible chart with a data table fallback.
    expect(screen.getByRole("img", { name: /study minutes/i })).toBeInTheDocument();
    // Feed: grouped by day with worded, typed rows.
    expect(screen.getByText("Today")).toBeInTheDocument();
    expect(screen.getByText("Yesterday")).toBeInTheDocument();
    expect(screen.getByText("Mastered TLS fundamentals in How HTTPS works")).toBeInTheDocument();
    expect(
      screen.getByText("Started Lesson 2 · Fundamentals in How HTTPS works"),
    ).toBeInTheDocument();
  });

  it("sends the viewer's IANA timezone with the snapshot request", async () => {
    // Arrange
    const fetchMock = vi.fn((_input: RequestInfo | URL) => okResponse(EMPTY_VIEW));
    vi.stubGlobal("fetch", fetchMock);

    // Act
    render(<ActivityScreen apiBaseUrl="http://test" onBrowseCourses={() => {}} />);
    await screen.findByText(/no activity yet/i);

    // Assert — day/streak math is user-local; the API needs the viewer's zone.
    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url).toContain("/api/activity?tz=");
  });
});

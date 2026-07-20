import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ActivityState } from "../../hooks/useActivity";
import type { ActivityView } from "../../lib/activity";
import { TrailBand } from "./TrailBand";

function ready(view: Partial<ActivityView>): ActivityState {
  return {
    status: "ready",
    view: {
      stats: { currentStreak: 3, longestStreak: 5, minutesThisWeek: 20, conceptsThisWeek: 2 },
      heat: [],
      week: [],
      feed: [],
      ...view,
    },
  };
}

const NOW = new Date("2026-07-20T18:00:00");

describe("TrailBand", () => {
  it("renders nothing on error", () => {
    // Arrange / Act
    const { container } = render(
      <TrailBand activity={{ status: "error", message: "x" }} lessonNumber={1} lessonTotal={5} />,
    );

    // Assert
    expect(container).toBeEmptyDOMElement();
  });

  it("uses the singular 'day' for a one-day streak", () => {
    render(
      <TrailBand
        activity={ready({
          stats: { currentStreak: 1, longestStreak: 1, minutesThisWeek: 3, conceptsThisWeek: 0 },
        })}
        lessonNumber={2}
        lessonTotal={5}
        now={NOW}
      />,
    );
    expect(screen.getByText(/1 day\b/i)).toBeInTheDocument();
  });

  it("shows the minutes studied today from the activity feed", () => {
    render(
      <TrailBand
        activity={ready({
          heat: [
            { date: "2026-07-19", minutes: 10, active: true },
            { date: "2026-07-20", minutes: 24, active: true },
          ],
        })}
        lessonNumber={1}
        lessonTotal={3}
        now={NOW}
      />,
    );
    expect(screen.getByText(/24 min/i)).toBeInTheDocument();
  });
});

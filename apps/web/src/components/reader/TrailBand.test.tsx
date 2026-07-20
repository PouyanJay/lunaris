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

  it("marks the goal meter reached once XP meets the goal", () => {
    // Three completed lessons today = 30 XP = the goal.
    const feed = [0, 1, 2].map(() => ({
      eventType: "completed" as const,
      courseId: "c1",
      occurredAt: "2026-07-20T09:00:00",
    }));
    render(<TrailBand activity={ready({ feed })} lessonNumber={1} lessonTotal={3} now={NOW} />);
    const meter = screen.getByRole("progressbar", { name: /today's goal/i });
    expect(meter).toHaveAttribute("aria-valuenow", "30");
  });
});

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SessionEnded } from "./SessionEnded";

describe("SessionEnded", () => {
  it("says when to come back, and for what, when the close scheduled a review", () => {
    // P2c T7: the ending is real. The close put a day on what was covered; the ending says it,
    // in the same words on both surfaces, so a learner leaves knowing when to return.
    render(
      <SessionEnded nextReview={{ day: "Thursday 20 August", concepts: ["Prior", "Update"] }} />,
    );

    const ending = screen.getByRole("status", { name: /session ended/i });
    expect(ending).toHaveTextContent(/has ended/i);
    expect(ending).toHaveTextContent(/come back on Thursday 20 August for Prior and Update/i);
  });

  it("names one concept without an 'and'", () => {
    render(<SessionEnded nextReview={{ day: "Thursday 20 August", concepts: ["Prior"] }} />);

    expect(screen.getByRole("status")).toHaveTextContent(/for Prior\./i);
  });

  it("says only that the record stays when nothing was scheduled", () => {
    // A session that graded nothing (or one stored before the schedule existed) has no day to
    // name; the ending must not invent one, and must not read as broken either.
    render(<SessionEnded nextReview={null} />);

    const ending = screen.getByRole("status");
    expect(ending).toHaveTextContent(/has ended/i);
    expect(ending).not.toHaveTextContent(/come back/i);
  });
});

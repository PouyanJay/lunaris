import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeResource } from "../../test/fixtures";
import { WatchSurface } from "./WatchSurface";

const VIDEO = {
  videoUrl: "https://signed.example/final.mp4",
  posterUrl: null,
  captionsUrl: null,
  chapters: [{ id: "S1_intro", title: "Intro", startS: 0, endS: 10 }],
  transcript: [],
  label: "Binary Search — lesson video",
};

describe("WatchSurface", () => {
  it("renders the chaptered player", () => {
    // Arrange / Act
    render(<WatchSurface {...VIDEO} takeaways={[]} resources={[]} />);

    // Assert
    expect(screen.getByRole("navigation", { name: /video chapters/i })).toBeInTheDocument();
    expect(document.querySelector("video")).not.toBeNull();
  });

  it("docks the lesson's key takeaways when present", () => {
    // Arrange / Act
    render(
      <WatchSurface
        {...VIDEO}
        takeaways={["Locate a target with binary search."]}
        resources={[]}
      />,
    );

    // Assert
    expect(screen.getByRole("heading", { name: /key takeaways/i })).toBeInTheDocument();
    expect(screen.getByText(/locate a target with binary search/i)).toBeInTheDocument();
  });

  it("omits the takeaways section when there are none", () => {
    // Arrange / Act
    render(<WatchSurface {...VIDEO} takeaways={[]} resources={[]} />);

    // Assert
    expect(screen.queryByRole("heading", { name: /key takeaways/i })).not.toBeInTheDocument();
  });

  it("docks the lesson's resources when present", () => {
    // Arrange / Act
    render(
      <WatchSurface
        {...VIDEO}
        takeaways={[]}
        resources={[makeResource({ title: "Binary search visualised" })]}
      />,
    );

    // Assert
    expect(screen.getByRole("heading", { name: /resources/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /binary search visualised/i })).toBeInTheDocument();
  });

  it("omits the resources section when there are none", () => {
    // Arrange / Act
    render(<WatchSurface {...VIDEO} takeaways={[]} resources={[]} />);

    // Assert
    expect(screen.queryByRole("heading", { name: /resources/i })).not.toBeInTheDocument();
  });
});

import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { TranscriptCue, VideoChapter } from "../../lib/videoJobs";
import { CinemaPlayer } from "./CinemaPlayer";

const CHAPTERS: VideoChapter[] = [
  { id: "S1_intro", title: "The coastline puzzle", startS: 0, endS: 72 },
  { id: "S2_self", title: "Self-similarity", startS: 72, endS: 158 },
];
const TRANSCRIPT: TranscriptCue[] = [
  { startS: 0, endS: 4, text: "A coastline has no single length." },
  { startS: 72, endS: 76, text: "Parts resemble the whole." },
];

function renderPlayer(overrides: Partial<React.ComponentProps<typeof CinemaPlayer>> = {}) {
  return render(
    <CinemaPlayer
      videoUrl="memory://v.mp4"
      posterUrl={null}
      captionsUrl={null}
      chapters={CHAPTERS}
      transcript={TRANSCRIPT}
      label="Fractals · Lesson 1"
      {...overrides}
    />,
  );
}

describe("CinemaPlayer", () => {
  it("renders the video with a chapter rail and transcript", () => {
    // Arrange / Act
    renderPlayer();

    // Assert
    const chapters = screen.getByRole("navigation", { name: /video chapters/i });
    expect(
      within(chapters).getByRole("button", { name: /the coastline puzzle/i }),
    ).toBeInTheDocument();
    expect(within(chapters).getByRole("button", { name: /self-similarity/i })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /a coastline has no single length/i }),
    ).toBeInTheDocument();
  });

  it("seeks the video when a chapter is clicked", () => {
    // Arrange — jsdom has no media; stub the seek surface.
    renderPlayer();
    const video = screen.getByLabelText("Fractals · Lesson 1") as HTMLVideoElement;
    const setCurrentTime = vi.fn();
    Object.defineProperty(video, "currentTime", { set: setCurrentTime, get: () => 0 });
    video.play = vi.fn().mockResolvedValue(undefined);

    // Act
    fireEvent.click(screen.getByRole("button", { name: /self-similarity/i }));

    // Assert — seeks to the chapter's start second.
    expect(setCurrentTime).toHaveBeenCalledWith(72);
  });

  it("highlights the chapter and cue for the current playback time", () => {
    // Arrange
    renderPlayer();
    const video = screen.getByLabelText("Fractals · Lesson 1") as HTMLVideoElement;
    Object.defineProperty(video, "currentTime", { configurable: true, value: 74 });

    // Act — the video advances into the second chapter.
    fireEvent.timeUpdate(video);

    // Assert — the second chapter and its cue read as current.
    expect(screen.getByRole("button", { name: /self-similarity/i })).toHaveAttribute(
      "aria-current",
      "true",
    );
    expect(screen.getByRole("button", { name: /parts resemble the whole/i })).toHaveAttribute(
      "aria-current",
      "true",
    );
  });

  it("shows only the chapter rail for a silent video (no transcript)", () => {
    // Arrange / Act
    renderPlayer({ transcript: [] });

    // Assert
    expect(screen.getByRole("navigation", { name: /video chapters/i })).toBeInTheDocument();
    expect(screen.queryByText(/^transcript$/i)).not.toBeInTheDocument();
  });
});

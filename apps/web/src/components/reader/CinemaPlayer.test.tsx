import { createEvent, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

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
  // The Fullscreen API is stubbed onto jsdom globals in a couple of tests — clear it after every test
  // (even on failure) so it can't leak into an unrelated one.
  afterEach(() => {
    delete (HTMLElement.prototype as { requestFullscreen?: unknown }).requestFullscreen;
    if (Object.getOwnPropertyDescriptor(document, "fullscreenElement")) {
      delete (document as { fullscreenElement?: unknown }).fullscreenElement;
    }
  });

  it("renders the video with a chapter rail and the current caption", () => {
    // Arrange / Act
    renderPlayer();

    // Assert — the chapter rail, and (at t=0) the first spoken line captioned over the video.
    const chapters = screen.getByRole("navigation", { name: /video chapters/i });
    expect(
      within(chapters).getByRole("button", { name: /the coastline puzzle/i }),
    ).toBeInTheDocument();
    expect(within(chapters).getByRole("button", { name: /self-similarity/i })).toBeInTheDocument();
    expect(screen.getByText(/a coastline has no single length/i)).toBeInTheDocument();
  });

  it("seeks the video when a chapter is clicked", () => {
    // Arrange — jsdom has no media; stub the seek surface.
    renderPlayer();
    const video = screen.getByLabelText("Fractals · Lesson 1") as HTMLVideoElement;
    const setCurrentTime = vi.fn();
    Object.defineProperty(video, "currentTime", { set: setCurrentTime, get: () => 0 });

    // Act
    fireEvent.click(screen.getByRole("button", { name: /self-similarity/i }));

    // Assert — seeks to the chapter's start second.
    expect(setCurrentTime).toHaveBeenCalledWith(72);
  });

  it("advances the active chapter and caption with the playback time", () => {
    // Arrange
    renderPlayer();
    const video = screen.getByLabelText("Fractals · Lesson 1") as HTMLVideoElement;
    Object.defineProperty(video, "currentTime", { configurable: true, value: 74 });

    // Act — the video advances into the second chapter.
    fireEvent.timeUpdate(video);

    // Assert — the second chapter reads as current and its spoken line is captioned.
    expect(screen.getByRole("button", { name: /self-similarity/i })).toHaveAttribute(
      "aria-current",
      "true",
    );
    expect(screen.getByText(/parts resemble the whole/i)).toBeInTheDocument();
  });

  it("marks a chapter watched once playback passes its end", () => {
    // Arrange
    renderPlayer();
    const video = screen.getByLabelText("Fractals · Lesson 1") as HTMLVideoElement;
    Object.defineProperty(video, "currentTime", { configurable: true, value: 74 });

    // Act — playback moves into chapter 2, so chapter 1 (ends at 72) is now behind us.
    fireEvent.timeUpdate(video);

    // Assert — chapter 1 reads as watched; the current chapter does not.
    expect(
      screen.getByRole("button", { name: /the coastline puzzle \(watched\)/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /self-similarity \(watched\)/i }),
    ).not.toBeInTheDocument();
  });

  it("accents a chapter key term in the caption", () => {
    // Arrange / Act — a chapter whose key term appears in the current spoken line.
    render(
      <CinemaPlayer
        videoUrl="memory://v.mp4"
        posterUrl={null}
        captionsUrl={null}
        chapters={[{ id: "S1", title: "Coastlines", startS: 0, endS: 10, keyTerms: ["coastline"] }]}
        transcript={[{ startS: 0, endS: 5, text: "A coastline has no single length." }]}
        label="Fractals"
      />,
    );

    // Assert — the key term is wrapped in a <mark>; the rest of the line is not.
    const term = screen.getByText("coastline", { selector: "mark" });
    expect(term.tagName).toBe("MARK");
  });

  it("shows only the chapter rail for a silent video (no transcript)", () => {
    // Arrange / Act
    renderPlayer({ transcript: [] });

    // Assert — the rail is present; with no transcript there is no synced caption line.
    expect(screen.getByRole("navigation", { name: /video chapters/i })).toBeInTheDocument();
    expect(screen.queryByText(/a coastline has no single length/i)).not.toBeInTheDocument();
  });

  it("plays and pauses through the control-bar button", () => {
    // Arrange
    renderPlayer();
    const video = screen.getByLabelText("Fractals · Lesson 1") as HTMLVideoElement;
    video.play = vi.fn().mockResolvedValue(undefined);
    video.pause = vi.fn();
    Object.defineProperty(video, "paused", { configurable: true, get: () => true });

    // Act — the control-bar Play button starts the video…
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    expect(video.play).toHaveBeenCalled();

    // …and once the video reports playing, the button becomes Pause and the overlay is gone.
    fireEvent.play(video);
    expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /play video/i })).not.toBeInTheDocument();
  });

  it("seeks with the scrubber via the keyboard", () => {
    // Arrange — a known duration, and a captured seek surface.
    renderPlayer();
    const video = screen.getByLabelText("Fractals · Lesson 1") as HTMLVideoElement;
    const setCurrentTime = vi.fn();
    Object.defineProperty(video, "currentTime", {
      configurable: true,
      set: setCurrentTime,
      get: () => 0,
    });
    Object.defineProperty(video, "duration", { configurable: true, get: () => 158 });
    fireEvent.loadedMetadata(video);
    const slider = screen.getByRole("slider", { name: /seek/i });

    // Act / Assert — ArrowRight steps forward 5s and the slider's accessible state tracks it…
    fireEvent.keyDown(slider, { key: "ArrowRight" });
    expect(setCurrentTime).toHaveBeenCalledWith(5);
    expect(slider).toHaveAttribute("aria-valuenow", "5");
    expect(slider).toHaveAttribute("aria-valuetext", "0:05 of 2:38");

    // …End jumps to the duration.
    fireEvent.keyDown(slider, { key: "End" });
    expect(setCurrentTime).toHaveBeenLastCalledWith(158);
  });

  it("seeks the video when the scrubber track is clicked", () => {
    // Arrange — a known duration and track geometry (jsdom lays nothing out).
    renderPlayer();
    const video = screen.getByLabelText("Fractals · Lesson 1") as HTMLVideoElement;
    const setCurrentTime = vi.fn();
    Object.defineProperty(video, "currentTime", {
      configurable: true,
      set: setCurrentTime,
      get: () => 0,
    });
    Object.defineProperty(video, "duration", { configurable: true, get: () => 158 });
    fireEvent.loadedMetadata(video);
    const slider = screen.getByRole("slider", { name: /seek/i });
    // jsdom lays nothing out, so the scrubber's geometry (read off event.currentTarget) is stubbed.
    const rectSpy = vi
      .spyOn(HTMLElement.prototype, "getBoundingClientRect")
      .mockReturnValue({ left: 0, width: 200 } as DOMRect);

    // Act — click a quarter of the way along the 200px track. jsdom's PointerEvent drops clientX
    // from its init, so set it on the native event directly.
    const event = createEvent.pointerDown(slider);
    Object.defineProperty(event, "clientX", { value: 50 });
    fireEvent(slider, event);

    // Assert — seeks to 25% of the duration.
    expect(setCurrentTime).toHaveBeenCalledWith(158 * 0.25);
    rectSpy.mockRestore();
  });

  it("shows the current chapter in the readout", () => {
    // Arrange
    renderPlayer();
    const video = screen.getByLabelText("Fractals · Lesson 1") as HTMLVideoElement;
    Object.defineProperty(video, "duration", { configurable: true, get: () => 158 });
    fireEvent.loadedMetadata(video);
    Object.defineProperty(video, "currentTime", { configurable: true, value: 74 });

    // Act — playback advances into the second chapter.
    fireEvent.timeUpdate(video);

    // Assert — the readout names the current chapter.
    expect(screen.getByText(/CH 2 .* SELF-SIMILARITY/)).toBeInTheDocument();
  });

  it("shows a title-card cover before first play and drops it once playing", () => {
    // Arrange / Act
    renderPlayer();

    // Assert — the cover carries the video title and a chapter-count meta before play…
    expect(screen.getByText("Fractals · Lesson 1")).toBeInTheDocument();
    expect(screen.getByText(/2 chapters/i)).toBeInTheDocument();

    // …and once the video reports playing, the cover is gone (the real frame shows through).
    const video = screen.getByLabelText("Fractals · Lesson 1") as HTMLVideoElement;
    fireEvent.play(video);
    expect(screen.queryByText("Fractals · Lesson 1")).not.toBeInTheDocument();

    // A later pause shows the real frame, not the cover — it does not come back.
    fireEvent.pause(video);
    expect(screen.queryByText("Fractals · Lesson 1")).not.toBeInTheDocument();
  });

  it("toggles the synced caption with the captions button", () => {
    // Arrange — at t=0 the first spoken line is captioned.
    renderPlayer();
    expect(screen.getByText(/a coastline has no single length/i)).toBeInTheDocument();

    // Act / Assert — the captions toggle hides it, then shows it again.
    fireEvent.click(screen.getByRole("button", { name: /hide captions/i }));
    expect(screen.queryByText(/a coastline has no single length/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /show captions/i }));
    expect(screen.getByText(/a coastline has no single length/i)).toBeInTheDocument();
  });

  it("offers no captions toggle for a silent video", () => {
    renderPlayer({ transcript: [] });
    expect(screen.queryByRole("button", { name: /captions/i })).not.toBeInTheDocument();
  });

  it("requests fullscreen from the fullscreen button", () => {
    // Arrange — jsdom lacks the Fullscreen API; provide the request on the element prototype.
    const requestFullscreen = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(HTMLElement.prototype, "requestFullscreen", {
      configurable: true,
      value: requestFullscreen,
    });
    renderPlayer();

    // Act / Assert — the fullscreen button asks the player to go fullscreen.
    fireEvent.click(screen.getByRole("button", { name: /enter fullscreen/i }));
    expect(requestFullscreen).toHaveBeenCalled();
  });

  it("flips the fullscreen button to Exit while this player is fullscreen", () => {
    // Arrange
    renderPlayer();
    const video = screen.getByLabelText("Fractals · Lesson 1") as HTMLVideoElement;
    const main = video.parentElement?.parentElement; // video → .stage → .main (the fullscreen target)
    Object.defineProperty(document, "fullscreenElement", { configurable: true, get: () => main });

    // Act — the document reports this player's element is now fullscreen.
    fireEvent(document, new Event("fullscreenchange"));

    // Assert — the button offers to exit.
    expect(screen.getByRole("button", { name: /exit fullscreen/i })).toBeInTheDocument();
  });
});

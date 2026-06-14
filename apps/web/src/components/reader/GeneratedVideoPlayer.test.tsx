import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { GeneratedVideoPlayer } from "./GeneratedVideoPlayer";

const URLS = {
  videoUrl: "https://signed.example/u/c/job-1/final.mp4?token=t",
  posterUrl: "https://signed.example/u/c/job-1/poster.jpg?token=t",
};

describe("GeneratedVideoPlayer", () => {
  it("shows the poster until clicked, then the native player on the signed URL", () => {
    // Arrange / Act — the shared facade with both URLs and no captions (a silent video).
    render(<GeneratedVideoPlayer {...URLS} captionsUrl={null} label="Play the course trailer" />);

    // Assert — the poster is the play target named by `label`; no <video> until clicked.
    const play = screen.getByRole("button", { name: "Play the course trailer" });
    expect(document.querySelector("video")).toBeNull();

    fireEvent.click(play);
    const video = document.querySelector("video");
    expect(video?.src).toBe(URLS.videoUrl);
    expect(video?.poster).toBe(URLS.posterUrl);
    expect(video?.hasAttribute("controls")).toBe(true);
    // Silent video → no captions track, no CORS opt-in.
    expect(video?.querySelector("track")).toBeNull();
    expect(video?.hasAttribute("crossorigin")).toBe(false);
  });

  it("falls back to a VIDEO glyph when there is no poster image", () => {
    // Arrange / Act — a video whose poster failed to render (posterUrl null).
    render(
      <GeneratedVideoPlayer
        videoUrl={URLS.videoUrl}
        posterUrl={null}
        captionsUrl={null}
        label="Play the topic overview"
      />,
    );

    // Assert — the play target still exists, with a text glyph instead of an <img>.
    const play = screen.getByRole("button", { name: "Play the topic overview" });
    expect(play.querySelector("img")).toBeNull();
    expect(play).toHaveTextContent("VIDEO");
  });

  it("attaches a default English captions track and opts into CORS for a narrated video", () => {
    // Arrange / Act — a narrated video ships a cross-origin captions URL.
    const captionsUrl = "https://signed.example/u/c/job-1/captions.vtt?token=t";
    render(<GeneratedVideoPlayer {...URLS} captionsUrl={captionsUrl} label="Play it" />);
    fireEvent.click(screen.getByRole("button", { name: "Play it" }));

    // Assert — the track loads cross-origin (WCAG 2.2 AA captions).
    const track = document.querySelector("video track");
    expect(track?.getAttribute("kind")).toBe("captions");
    expect(track?.getAttribute("srclang")).toBe("en");
    expect(track?.hasAttribute("default")).toBe(true);
    expect(document.querySelector("video")?.getAttribute("crossorigin")).toBe("anonymous");
  });
});

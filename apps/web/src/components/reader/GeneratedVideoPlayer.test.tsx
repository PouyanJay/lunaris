import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { GeneratedVideoPlayer } from "./GeneratedVideoPlayer";

const URLS = {
  videoUrl: "https://signed.example/u/c/job-1/final.mp4?token=t",
  posterUrl: "https://signed.example/u/c/job-1/poster.jpg?token=t",
};

const STALE_URL = "https://signed.example/job-1/final.mp4?token=stale";
const FRESH_URL = "https://signed.example/job-1/final.mp4?token=fresh";

const currentVideo = () => document.querySelector("video") as HTMLVideoElement;

/** Render the player with a re-mint callback and start playback (the <video> is mounted). */
function playWith(refreshPlayback: () => void, videoUrl = STALE_URL) {
  const utils = render(
    <GeneratedVideoPlayer
      videoUrl={videoUrl}
      posterUrl={null}
      captionsUrl={null}
      label="Play it"
      refreshPlayback={refreshPlayback}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Play it" }));
  return utils;
}

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

  it("overlays the title on the poster and drops it once playing", () => {
    // Arrange / Act — the design's title-over-poster treatment (P6). Decorative: the play
    // button's label stays the accessible name.
    render(
      <GeneratedVideoPlayer
        {...URLS}
        captionsUrl={null}
        label="Play lesson video"
        overlayTitle="The TLS handshake"
      />,
    );
    expect(screen.getByText("The TLS handshake")).toBeInTheDocument();

    // Once playing, the native player owns the stage — no overlay over the controls.
    fireEvent.click(screen.getByRole("button", { name: "Play lesson video" }));
    expect(screen.queryByText("The TLS handshake")).not.toBeInTheDocument();
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

  it("re-mints the signed URL when the video fails to load it (the expired-URL recovery)", () => {
    // Arrange — a signed URL that has since expired (the reader sat on the page past its ~1h TTL).
    const refreshPlayback = vi.fn();
    playWith(refreshPlayback);

    // Act — the <video> reports a load error on the dead URL.
    fireEvent.error(currentVideo());

    // Assert — the slot is asked to re-mint a fresh URL.
    expect(refreshPlayback).toHaveBeenCalledTimes(1);
  });

  it("does not re-mint the same dead URL twice (no retry loop)", () => {
    // Arrange — a URL whose re-mint will also fail (the error fires again on the same URL).
    const refreshPlayback = vi.fn();
    playWith(refreshPlayback);

    // Act — two errors on the same URL.
    fireEvent.error(currentVideo());
    fireEvent.error(currentVideo());

    // Assert — only one re-mint: a genuinely dead URL fails once instead of looping the re-fetch.
    expect(refreshPlayback).toHaveBeenCalledTimes(1);
  });

  it("re-mints again for a fresh URL after the first recovery", () => {
    // Arrange — play, then the first URL errors and is re-minted (a new prop arrives).
    const refreshPlayback = vi.fn();
    const { rerender } = playWith(refreshPlayback, STALE_URL);
    fireEvent.error(currentVideo());

    // Act — the fresh URL later expires too and errors.
    rerender(
      <GeneratedVideoPlayer
        videoUrl={FRESH_URL}
        posterUrl={null}
        captionsUrl={null}
        label="Play it"
        refreshPlayback={refreshPlayback}
      />,
    );
    fireEvent.error(currentVideo());

    // Assert — each distinct URL earns its own re-mint.
    expect(refreshPlayback).toHaveBeenCalledTimes(2);
  });

  it("does nothing on error when no re-mint is wired (a degraded slot just stays put)", () => {
    // Arrange / Act — no refreshPlayback: the error handler must be a safe no-op, not a crash.
    render(<GeneratedVideoPlayer {...URLS} captionsUrl={null} label="Play it" />);
    fireEvent.click(screen.getByRole("button", { name: "Play it" }));

    // Assert — firing the error throws nothing and the player is still mounted.
    expect(() => fireEvent.error(document.querySelector("video") as HTMLVideoElement)).not.toThrow();
    expect(document.querySelector("video")).not.toBeNull();
  });
});

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VideoFacade } from "./VideoFacade";

const VIDEO_ID = "dQw4w9WgXcQ";

describe("VideoFacade", () => {
  it("shows a poster with no third-party iframe until played", () => {
    render(<VideoFacade videoId={VIDEO_ID} title="Phonics intro" />);

    expect(screen.getByRole("button", { name: "Play video: Phonics intro" })).toBeInTheDocument();
    // The cheap, tracker-free state: the YouTube frame is not mounted yet.
    expect(document.querySelector("iframe")).toBeNull();
  });

  it("expands the nocookie player in place on the play click", () => {
    render(<VideoFacade videoId={VIDEO_ID} title="Phonics intro" />);

    fireEvent.click(screen.getByRole("button", { name: "Play video: Phonics intro" }));

    const frame = document.querySelector("iframe") as HTMLIFrameElement;
    expect(frame).not.toBeNull();
    expect(frame.src).toContain("youtube-nocookie.com/embed/dQw4w9WgXcQ");
    expect(frame.src).toContain("autoplay=1");
  });

  it("opens a focus-trapped fullscreen lightbox and closes on Escape", () => {
    render(<VideoFacade videoId={VIDEO_ID} title="Phonics intro" />);

    fireEvent.click(screen.getByRole("button", { name: /full screen/i }));

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog.querySelector("iframe")?.getAttribute("src")).toContain("nocookie");

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

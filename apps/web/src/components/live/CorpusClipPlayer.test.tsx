import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CorpusClipPlayer } from "./CorpusClipPlayer";

const clip = {
  assetId: "clip-1",
  title: "Current and resistance",
  startS: 2,
  endS: 5,
  transcript: [{ startS: 2, endS: 5, text: "Current falls as resistance rises." }],
  sourceLabel: "Circuit course · Lesson 1",
};
const getSource = vi.fn(async () => "https://media.example.test/video.mp4");
beforeEach(() => {
  getSource.mockClear();
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

async function loaded() {
  fireEvent.click(screen.getByRole("button", { name: "Load clip" }));
  await waitFor(() => expect(document.querySelector("video")).toHaveAttribute("src"));
  const video = document.querySelector("video")!;
  Object.defineProperty(video, "duration", { configurable: true, value: 8 });
  fireEvent.loadedMetadata(video);
  return video;
}

it("requires explicit loading and playback, exposing captions and source", async () => {
  const start = vi.fn();
  render(
    <CorpusClipPlayer
      clip={clip}
      getSource={getSource}
      playbackScope="turn1"
      onPlaybackStart={start}
    />,
  );
  expect(getSource).not.toHaveBeenCalled();
  expect(screen.getByText(clip.sourceLabel)).toBeVisible();
  const video = await loaded();
  expect(video.currentTime).toBe(2);
  expect(video.play).not.toHaveBeenCalled();
  expect(video.querySelector('track[kind="captions"]')).toBeInTheDocument();
  fireEvent.click(screen.getByText("Transcript"));
  expect(screen.getByText(clip.transcript[0]!.text)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Play clip" }));
  await waitFor(() => expect(video.play).toHaveBeenCalledOnce());
  expect(start).toHaveBeenCalledOnce();
});

it("clamps seeking and stops at the verified end", async () => {
  render(<CorpusClipPlayer clip={clip} getSource={getSource} playbackScope="turn1" />);
  const video = await loaded();
  video.currentTime = 0;
  fireEvent.seeked(video);
  expect(video.currentTime).toBe(2);
  video.currentTime = 7;
  fireEvent.timeUpdate(video);
  expect(video.currentTime).toBe(5);
  expect(video.pause).toHaveBeenCalled();
});

it.each([NaN, Infinity, 0, 93])("rejects invalid clip bounds %s before fetching", (endS) => {
  const source = vi.fn();
  render(<CorpusClipPlayer clip={{ ...clip, endS }} getSource={source} playbackScope="turn1" />);
  expect(screen.getByRole("alert")).toHaveTextContent("Clip unavailable");
  expect(source).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "Load clip" })).not.toBeInTheDocument();
});

it("discards late media resolution on turn change", async () => {
  let resolve!: (url: string) => void;
  const pending = vi.fn(
    (_assetId: string, _signal: AbortSignal) =>
      new Promise<string>((done) => {
        resolve = done;
      }),
  );
  const { rerender } = render(
    <CorpusClipPlayer clip={clip} getSource={pending} playbackScope="turn1" />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Load clip" }));
  rerender(<CorpusClipPlayer clip={clip} getSource={pending} playbackScope="turn2" />);
  await act(async () => resolve("https://media.example.test/old.mp4"));
  expect(document.querySelector("video")).not.toHaveAttribute("src");
  expect(pending.mock.calls[0]![1].aborted).toBe(true);
});

it("requires an explicit refresh after expired media and rejects short media", async () => {
  const source = vi.fn(async () => "https://media.example.test/video.mp4");
  render(<CorpusClipPlayer clip={clip} getSource={source} playbackScope="turn1" />);
  const video = await loaded();
  fireEvent.error(video);
  expect(screen.getByRole("alert")).toHaveTextContent("Refresh");
  expect(source).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Refresh clip" }));
  await waitFor(() => expect(source).toHaveBeenCalledTimes(2));
  Object.defineProperty(video, "duration", { configurable: true, value: 4 });
  fireEvent.loadedMetadata(video);
  expect(screen.getByRole("alert")).toHaveTextContent("Clip unavailable");
});

it("interrupts pending playback and releases media on unmount", async () => {
  const props = { clip, getSource, playbackScope: "turn1", interruptionKey: 0 };
  const { rerender, unmount } = render(<CorpusClipPlayer {...props} />);
  const video = await loaded();
  let finish!: () => void;
  vi.mocked(video.play).mockImplementation(
    () =>
      new Promise<void>((resolve) => {
        finish = resolve;
      }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Play clip" }));
  rerender(<CorpusClipPlayer {...props} interruptionKey={1} />);
  await act(async () => finish());
  expect(video.pause).toHaveBeenCalled();
  unmount();
  expect(video).not.toHaveAttribute("src");
});

it("shows recovery for denied source access without exposing provider details", async () => {
  render(
    <CorpusClipPlayer
      clip={clip}
      playbackScope="turn1"
      getSource={async () => {
        throw new Error("secret provider details");
      }}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Load clip" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Refresh");
  expect(screen.queryByText(/secret provider/)).not.toBeInTheDocument();
});

it("rejects captions outside the verified excerpt", () => {
  render(
    <CorpusClipPlayer
      clip={{ ...clip, transcript: [{ startS: 0, endS: 8, text: "Wrong segment" }] }}
      playbackScope="turn1"
      getSource={getSource}
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Clip unavailable");
});

it("times out source loading with explicit recovery and cancels late results", async () => {
  vi.useFakeTimers();
  let resolve!: (source: string) => void;
  const source = vi.fn(
    (_id: string, _signal: AbortSignal) =>
      new Promise<string>((done) => {
        resolve = done;
      }),
  );
  try {
    render(<CorpusClipPlayer clip={clip} playbackScope="turn1" getSource={source} />);
    fireEvent.click(screen.getByRole("button", { name: "Load clip" }));
    await act(async () => {
      vi.advanceTimersByTime(15000);
    });
    expect(screen.getByRole("alert")).toHaveTextContent("Refresh");
    expect(source.mock.calls[0]![1].aborted).toBe(true);
    await act(async () => resolve("https://media.example.test/late.mp4"));
    expect(document.querySelector("video")).not.toHaveAttribute("src");
  } finally {
    vi.useRealTimers();
  }
});

it("preserves keyboard focus from loading to playback without stealing moved focus", async () => {
  render(
    <>
      <CorpusClipPlayer clip={clip} playbackScope="turn1" getSource={getSource} />
      <button>Elsewhere</button>
    </>,
  );
  const load = screen.getByRole("button", { name: "Load clip" });
  load.focus();
  const video = await loaded();
  expect(screen.getByRole("button", { name: "Play clip" })).toHaveFocus();
  fireEvent.error(video);
  fireEvent.click(screen.getByRole("button", { name: "Refresh clip" }));
  screen.getByRole("button", { name: "Elsewhere" }).focus();
  await waitFor(() => expect(video).toHaveAttribute("src"));
  fireEvent.loadedMetadata(video);
  expect(screen.getByRole("button", { name: "Elsewhere" })).toHaveFocus();
});

it("announces pending playback and times it out with explicit recovery", async () => {
  render(<CorpusClipPlayer clip={clip} playbackScope="turn1" getSource={getSource} />);
  const video = await loaded();
  let resolve!: () => void;
  vi.mocked(video.play).mockImplementation(
    () =>
      new Promise<void>((done) => {
        resolve = done;
      }),
  );
  vi.useFakeTimers();
  try {
    fireEvent.click(screen.getByRole("button", { name: "Play clip" }));
    expect(screen.getByRole("status")).toHaveTextContent("Buffering clip…");
    await act(async () => {
      vi.advanceTimersByTime(15000);
    });
    expect(screen.getByRole("button", { name: "Refresh clip" })).toBeVisible();
    await act(async () => resolve());
    expect(video.pause).toHaveBeenCalled();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  } finally {
    vi.useRealTimers();
  }
});

it("announces mid-playback buffering and allows immediate cancellation", async () => {
  render(<CorpusClipPlayer clip={clip} playbackScope="turn1" getSource={getSource} />);
  const video = await loaded();
  fireEvent.play(video);
  fireEvent.waiting(video);
  expect(screen.getByRole("status")).toHaveTextContent("Buffering clip…");
  fireEvent.click(screen.getByRole("button", { name: "Cancel playback" }));
  expect(video.pause).toHaveBeenCalled();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

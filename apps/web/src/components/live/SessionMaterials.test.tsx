import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { SessionMaterials } from "./SessionMaterials";
import { SessionMediaContext } from "./SessionMediaContext";
import { SessionMediaCoordinator } from "./SessionMediaCoordinator";
import type { NodeAsset } from "../../lib/liveMaterials";

const asset: NodeAsset = {
  assetId: "lesson1",
  kind: "lesson",
  origin: "ingested",
  locator: "lesson:1",
  sourceDigest: "a".repeat(64),
  title: "Records",
  excerpt: "Records store data.",
  sourceLabel: "Patient data course",
  clip: null,
  verification: { runId: "r", verifierVersion: "v1", sourceDigest: "a".repeat(64) },
};
const props = {
  apiBaseUrl: "https://api.test",
  sessionId: "s",
  turnSeq: 1,
  runId: "r",
  move: "introduce",
  materials: [asset],
};
beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
});
it("shows verified source material and ungraded question without an answer form", () => {
  render(
    <SessionMaterials
      {...props}
      materials={[
        asset,
        {
          ...asset,
          assetId: "q",
          kind: "assessment",
          locator: "assessment:1",
          excerpt: "What does a record store?",
        },
      ]}
    />,
  );
  expect(screen.getByText("Records store data.")).toBeVisible();
  expect(screen.getByText("What does a record store?")).toBeVisible();
  expect(screen.getByText(/ungraded practice/i)).toBeVisible();
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
});
it.each([null, { ...asset.verification!, sourceDigest: "b".repeat(64) }])(
  "withholds unverified or mismatched material and all retrieval hints: %j",
  (verification) => {
    const view = render(<SessionMaterials {...props} materials={[{ ...asset, verification }]} />);
    expect(screen.queryByText(asset.excerpt)).not.toBeInTheDocument();
    view.rerender(<SessionMaterials {...props} move="retrieve" />);
    expect(screen.queryByText(asset.excerpt)).not.toBeInTheDocument();
  },
);
it("loads authorized media on demand and synchronously stops voice before clip playback", async () => {
  const coordinator = new SessionMediaCoordinator();
  const stopVoice = vi.fn();
  coordinator.register("voice", stopVoice);
  const fetcher = vi.fn(
    async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(JSON.stringify({ url: "https://media.test/video.mp4" }), { status: 200 }),
  );
  vi.stubGlobal("fetch", fetcher);
  const clipAsset: NodeAsset = {
    ...asset,
    assetId: "video1",
    kind: "video_clip",
    locator: `video:j:${"b".repeat(64)}:0:0`,
    clip: {
      jobId: "j",
      sourceDigest: "b".repeat(64),
      locator: `video:j:${"b".repeat(64)}:0:0`,
      startS: 2,
      endS: 5,
      durationS: 6,
      title: "Records clip",
      transcript: [{ startS: 2, endS: 5, text: "Records store data." }],
    },
  };
  render(
    <SessionMediaContext.Provider value={coordinator}>
      <SessionMaterials {...props} materials={[clipAsset]} />
    </SessionMediaContext.Provider>,
  );
  expect(fetcher).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Load clip" }));
  await waitFor(() => expect(document.querySelector("video")).toHaveAttribute("src"));
  expect(fetcher.mock.calls[0]?.[0]).toBe(
    "https://api.test/api/live/sessions/s/materials/video1/media?turn=1",
  );
  expect(fetcher.mock.calls[0]?.[1]).toMatchObject({
    cache: "no-store",
    signal: expect.any(AbortSignal),
  });
  const video = document.querySelector("video")!;
  Object.defineProperty(video, "duration", { value: 6, configurable: true });
  fireEvent.loadedMetadata(video);
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Play clip" })));
  expect(stopVoice).toHaveBeenCalledOnce();
  expect(stopVoice.mock.invocationCallOrder[0]).toBeLessThan(
    vi.mocked(video.play).mock.invocationCallOrder[0]!,
  );
  act(() => coordinator.activate("voice"));
  expect(video.pause).toHaveBeenCalled();
  let release!: () => void;
  act(() => {
    release = coordinator.block("answer");
  });
  const playCalls = vi.mocked(video.play).mock.calls.length;
  fireEvent.click(screen.getByRole("button", { name: "Play clip" }));
  expect(video.play).toHaveBeenCalledTimes(playCalls);
  expect(screen.getByRole("button", { name: "Play clip" })).toBeDisabled();
  act(() => {
    release();
  });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Play clip" })));
  expect(video.play).toHaveBeenCalledTimes(playCalls + 1);
});

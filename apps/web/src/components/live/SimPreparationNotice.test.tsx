import { act, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { SimPreparationNotice } from "./SimPreparationNotice";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
it.each([
  ["building", /preparing a simulator.*continue/i],
  ["approved", /ready for.*next turn/i],
  ["rejected", /could not.*continue/i],
])("shows an honest %s generation state", async (status, message) => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ status }))));
  render(<SimPreparationNotice apiBaseUrl="http://api" sessionId="s" turnSeq={1} />);
  expect(await screen.findByRole("status")).toHaveTextContent(message);
});

it("keeps checking when the initial read precedes background enqueue", async () => {
  vi.useFakeTimers();
  const statuses = ["unavailable", "queued", "approved"];
  const fetch = vi
    .fn()
    .mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify({ status: statuses.shift() }))),
    );
  vi.stubGlobal("fetch", fetch);
  render(<SimPreparationNotice apiBaseUrl="http://api" sessionId="s" turnSeq={1} />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(6000);
  });
  expect(fetch).toHaveBeenCalledTimes(3);
  expect(screen.getByRole("status")).toHaveTextContent(/ready for.*next turn/i);
});

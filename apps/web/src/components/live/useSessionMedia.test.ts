import { renderHook } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { useSessionMedia } from "./useSessionMedia";

it("stops registered playback when answering, switching scopes and unmounting", () => {
  const view = renderHook(({ scope, busy }) => useSessionMedia(scope, busy), {
    initialProps: { scope: "api:s:1:r", busy: false },
  });
  const stop = vi.fn();
  view.result.current.register("clip", stop);
  view.rerender({ scope: "api:s:1:r", busy: true });
  expect(stop).toHaveBeenCalledOnce();
  expect(view.result.current.activate("clip")).toBe(false);
  view.rerender({ scope: "api:s:2:r2", busy: false });
  expect(stop).toHaveBeenCalledTimes(2);
  const next = vi.fn();
  view.result.current.register("clip", next);
  view.unmount();
  expect(next).toHaveBeenCalledOnce();
});

it("keeps playback blocked until every active request settles", () => {
  const view = renderHook(() => useSessionMedia("scope", false));
  const answer = view.result.current.block("answer");
  const copilot = view.result.current.block("copilot");
  answer();
  expect(view.result.current.activate("clip")).toBe(false);
  copilot();
  expect(view.result.current.activate("clip")).toBe(true);
});

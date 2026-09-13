import { afterEach, expect, it, vi } from "vitest";
import { transcribeVoice } from "./transcribeVoice";

const source = { turnSeq: 2, runId: "source-run" };
const op = "b16c2dd0-5fa0-4a06-a1b4-c92a164b65ea";
afterEach(() => vi.unstubAllGlobals());

it("sends the recorded clip with stable identity and validates the returned draft", async () => {
  const transcript = {
    text: "A fraction is a part of a whole.",
    source,
    operationId: op,
    provider: "fixture",
    model: "v1",
  };
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(transcript)));
  vi.stubGlobal("fetch", fetcher);
  const result = await transcribeVoice(
    { apiBaseUrl: "", sessionId: "s", source, operationId: op },
    new Blob(["wave"], { type: "audio/wav" }),
    new AbortController().signal,
  );
  expect(result).toEqual(transcript);
  const [url, init] = fetcher.mock.calls[0]!;
  expect(url).toContain("/api/live/sessions/s/voice/transcriptions?turnSeq=2&runId=source-run");
  expect(new Headers(init.headers).get("Idempotency-Key")).toBe(op);
  expect(new Headers(init.headers).get("Content-Type")).toBe("audio/wav");
});

it.each([
  { source: { ...source, runId: "stale" } },
  { operationId: "other" },
  { text: "x".repeat(4001) },
  { provider: null },
])("rejects a mismatched or invalid transcription response: %j", async (change) => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({
            text: "Hello",
            source,
            operationId: op,
            provider: "fixture",
            model: "v1",
            ...change,
          }),
        ),
      ),
  );
  await expect(
    transcribeVoice(
      { apiBaseUrl: "", sessionId: "s", source, operationId: op },
      new Blob(["wave"]),
      new AbortController().signal,
    ),
  ).rejects.toThrow();
});

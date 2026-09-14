import { useLayoutEffect, useMemo, useSyncExternalStore } from "react";
import { createVoicePlayback } from "../../../lib/voice/playback";
import type { VoiceSource } from "../../../lib/voice/types";

/** Stops obsolete speech without cancelling the learning turn. Call play from a user gesture. */
export function useVoicePlayback({
  apiBaseUrl,
  sessionId,
  source,
}: {
  apiBaseUrl: string;
  sessionId: string;
  source: VoiceSource | null;
}) {
  const playback = useMemo(
    () => createVoicePlayback({ apiBaseUrl, sessionId }),
    [apiBaseUrl, sessionId],
  );
  const state = useSyncExternalStore(playback.subscribe, playback.getSnapshot);
  const turnSeq = source?.turnSeq;
  const runId = source?.runId;
  const exchangeSequence = source?.exchangeSequence;
  useLayoutEffect(() => () => playback.stop(), [playback, turnSeq, runId, exchangeSequence]);
  return {
    ...state,
    play: () => (source ? playback.play(source) : Promise.resolve()),
    stop: playback.stop,
  };
}

import type { VoiceSource, VoiceTranscript } from "../../../lib/voice/types";
import type { IncomingAnswer } from "../IncomingAnswerContext";

/** A late recording cannot populate the answer box for a newer turn. */
export function voiceDraftFor(
  draft: { scope: string; transcript: VoiceTranscript } | null,
  source: VoiceSource | null,
  scope: string,
): IncomingAnswer | null {
  return draft &&
    source &&
    draft.scope === scope &&
    draft.transcript.source.turnSeq === source.turnSeq &&
    draft.transcript.source.runId === source.runId
    ? { id: draft.transcript.operationId, text: draft.transcript.text }
    : null;
}

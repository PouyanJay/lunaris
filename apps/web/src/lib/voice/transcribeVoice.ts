import { authedFetch } from "../apiClient";
import type { VoiceSource, VoiceTranscript } from "./types";

interface Options {
  apiBaseUrl: string;
  sessionId: string;
  source: VoiceSource;
  operationId: string;
}

/** Upload one recording and return an identity-checked draft; never submit an answer. */
export async function transcribeVoice(
  options: Options,
  recording: Blob,
  signal: AbortSignal,
): Promise<VoiceTranscript> {
  const query = new URLSearchParams({
    turnSeq: String(options.source.turnSeq),
    runId: options.source.runId,
  });
  const response = await authedFetch(
    `${options.apiBaseUrl}/api/live/sessions/${encodeURIComponent(options.sessionId)}/voice/transcriptions?${query}`,
    {
      method: "POST",
      headers: { "Content-Type": "audio/wav", "Idempotency-Key": options.operationId },
      body: recording,
      signal,
    },
  );
  if (!response.ok) throw new Error("Transcription is unavailable. You can type your answer.");
  const value: unknown = await response.json();
  return validatedTranscript(value, options);
}

function validatedTranscript(value: unknown, options: Options): VoiceTranscript {
  if (!value || typeof value !== "object") throw new Error("Invalid transcript.");
  const result = value as Partial<VoiceTranscript>;
  if (
    typeof result.text !== "string" ||
    !result.text.trim() ||
    result.text.length > 4000 ||
    typeof result.provider !== "string" ||
    !result.provider ||
    result.provider.length > 100 ||
    typeof result.model !== "string" ||
    !result.model ||
    result.model.length > 100 ||
    result.operationId !== options.operationId ||
    result.source?.turnSeq !== options.source.turnSeq ||
    result.source?.runId !== options.source.runId ||
    (result.source?.exchangeSequence ?? null) !== (options.source.exchangeSequence ?? null)
  )
    throw new Error("Invalid or outdated transcript. You can type your answer.");
  return result as VoiceTranscript;
}

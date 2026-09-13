/** A server-persisted speech source; no client-authored tutor text crosses this boundary. */
export interface VoiceSource {
  turnSeq: number;
  runId: string;
  exchangeSequence?: number | null;
}

/** Final draft and provider attribution, returned before any assessment submission. */
export interface VoiceTranscript {
  text: string;
  source: VoiceSource;
  operationId: string;
  provider: string;
  model: string;
}

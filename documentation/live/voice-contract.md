# Live voice transport (Phase 4)

Voice adapts the existing session; it never submits an assessment itself. The browser reviews a final transcription and sends it through the same composer as typed text. Microphone capture and audio playback require explicit user activation. Stopping playback does not cancel an admitted learning turn.

## Shared contract

- Source: `{turnSeq: positive integer, runId: existing turn run ID, exchangeSequence?: 1..20}`. Absent exchange means the persisted tutor text; present means the latest persisted simulator reaction. Clients never supply speech text. Session ID is the route scope; source must still match the session's current turn.
- Transcription: `POST /api/live/sessions/{id}/voice/transcriptions?turnSeq=...&runId=...`, authenticated, `Idempotency-Key: UUID`, `Content-Type: audio/wav`, binary body. Mono PCM16 WAV, 16kHz, at most60seconds/1,920,044bytes. Response `{text, source, operationId, provider, model}`; text ≤4,000characters. Provenance originates at the provider adapter. No automatic answer submission.
- Speech: `POST /api/live/sessions/{id}/voice/speech`, authenticated JSON `{source, operationId: UUID}`. Response mono little-endian signed PCM16 at24kHz, `Content-Type: audio/pcm`, `X-Audio-Sample-Rate: 24000`. Chunks need not align to sample boundaries; the playback client must preserve a trailing byte. Request/Session correlation headers and `Cache-Control: no-store` accompany voice responses.
- Provider protocol: `transcribe(RecordedAudio, run_id) -> Transcription`; `speak(text, run_id) -> AsyncIterator[bytes]`. Both server-side, with bounded deadlines, credentials and metering added in #256.
- Session reader protocol: async owner-scoped `load`; reading for voice does not mutate transcript or mastery.
- Operation IDs identify explicit attempts. Durable admission/replay arrives in #255/#259; the skeleton is injection-only and unavailable in production. No uncertain paid retry is authorized by this contract.

## Error and lifecycle behavior

404 hides another owner's session;409 rejects stale sources;413 rejects oversized recordings;415 rejects MIME;422 rejects invalid audio/source;503 falls back to text when voice is unavailable. No raw audio, transcript, credentials or provider error bodies belong in operational logs. Cancelled recording drafts are discarded. Obsolete playback is stopped locally. Deletion/closure and replay are verified with durable admission in the dependent tickets.

## Ownership and integration

#255 owns new admission/storage implementation and migrations. #256 owns new provider/metering files. #257 owns capture/transcription client files. #258 owns playback files. #259 composes production APIs. #260 alone integrates SessionView/ComposerBridge/simulator reactions. These workers must not independently modify shared contracts. Root resolves contract changes before their consumers proceed.

## Provider references

[ElevenLabs transcription](https://elevenlabs.io/docs/api-reference/speech-to-text/convert) and [streaming speech](https://elevenlabs.io/docs/api-reference/text-to-speech/stream). Live uses George (`JBFqnCBsd6RMkjVDRZzb`) and preserves transcript text while normalizing speech pronunciation (HIPAA → Hippa; EHR → E-H-R).

Phase #220 tracks readiness. This document describes interfaces, not a claim of production voice delivery.

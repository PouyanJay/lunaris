# Live voice transport (Phase 4)

Voice adapts the existing session; it never submits an assessment itself. The browser reviews a final transcription and sends it through the same composer as typed text. Microphone capture and audio playback require explicit user activation. Stopping playback does not cancel an admitted learning turn.

## Shared contract

- Source: `{turnSeq: positive integer, runId: existing turn run ID, exchangeSequence?: 1..20}`. Absent exchange means the persisted tutor text; present means the latest persisted simulator reaction. Clients never supply speech text. Session ID is the route scope; source must still match the session's current turn.
- Transcription: `POST /api/live/sessions/{id}/voice/transcriptions?turnSeq=...&runId=...`, authenticated, `Idempotency-Key: UUID`, `Content-Type: audio/wav`, binary body. Mono PCM16 WAV, 16kHz, at most60seconds/1,920,044bytes. Response `{text, source, operationId, provider, model}`; text ≤4,000characters. Provenance originates at the provider adapter. No automatic answer submission.
- Speech: `POST /api/live/sessions/{id}/voice/speech`, authenticated JSON `{source, operationId: UUID}`. Response mono little-endian signed PCM16 at24kHz, `Content-Type: audio/pcm`, `X-Audio-Sample-Rate: 24000`. Chunks need not align to sample boundaries; the playback client must preserve a trailing byte. Request/Session correlation headers and `Cache-Control: no-store` accompany voice responses.
- Provider protocol: `transcribe(RecordedAudio, run_id) -> Transcription`; `speak(text, run_id) -> AsyncIterator[bytes]`. Both server-side, with bounded deadlines, credentials and metering added in #256.
- Session reader protocol: async owner-scoped `load`; reading for voice does not mutate transcript or mastery.
- Operation IDs identify explicit attempts. Durable admission binds each ID to its owner, session, source and input fingerprint. Completed transcripts and private generated audio replay without another provider call for 24 hours. Uncertain or expired in-flight operations retain their receipt and cannot be retried as new paid work. No uncertain paid retry is authorized by this contract.

## Error and lifecycle behavior

404 hides another owner's session;408 rejects a stalled upload;409 rejects stale sources;429 rejects admission or observed budget limits;413 rejects oversized recordings;415 rejects MIME;422 rejects invalid audio/source;503 falls back to text when voice is unavailable. No raw audio, transcript, credentials or provider error bodies belong in operational logs. Cancelled recording drafts are discarded. Obsolete playback is stopped locally. Durable admission fences deletion, closure and stale sources. Closed goodbye speech remains readable; new recordings require an active or placing session.

## Admission and retention

`LUNARIS_LIVE_VOICE_ENABLED=true` enables the composed API; it defaults off until final rollout. Uploads are bounded to 15 seconds. Provider operations have a 90-second outer deadline and generated PCM is capped at 5,760,000 bytes. Voice eligibility respects the text session deadline with a separate maximum of one hour; longer text-session configuration still works.

Admission allows at most two concurrent voice operations and 120 operations per session, with a $3 cumulative voice reservation ceiling. Reservations use conservative estimates ($0.001 per recording second and $0.0003 per pronunciation-expanded speech character), not actual provider prices. The existing observed session-spend check also applies before provider invocation. These are separate controls, not a combined atomic text-and-voice spending guarantee. Actual duration/character usage is metered; unknown model prices remain explicitly unknown.

Generated audio lives in a private bucket. A bounded API-lifetime sweep runs every minute, even with voice disabled, to scrub expired derived results and process deletion tombstones through the Storage API. Raw microphone recordings are never persisted. Client disconnect closes the provider in the same producer task and drains accepted usage; it never cancels the learning turn.

## Using voice

Choose **Speak**, finish recording, review or edit the transcript, then **Send**. Dictation enters the existing answer composer and preserves typed text; if the combined answer is too long, explicitly choose whether to replace it with the recording. Cards without a text composer show an editable recording preview. **Read aloud** plays the current tutor turn; **Read reaction** plays the latest simulator response. **Stop audio** stops local playback.

Authenticated learners use their ElevenLabs credential saved in Settings → Voice. Missing credentials, denied microphone permission, and provider failures leave typed answers available. Microphone capture requires a secure browser context. Voice does not change simulator practice into mastery evidence.

## Rollout

The production environment variable `LIVE_VOICE_ENABLED` is passed to the API through the existing human-gated deployment; it defaults to false. Set it to true for the final approved Phase 4 rollout. Turning it off disables new voice requests while text and private-audio cleanup continue. No browser secret or platform-key fallback is introduced.

Phase implementation tickets #254–#261 are integrated on the phase branch. #262 tracks real-provider evaluation, the final PR, rollout, and acceptance. Automated browser checks use generated microphone input and fixture speech; they do not establish physical-device or real-provider quality. Existing Live reload behavior starts a new session; voice checks assert that the old answer is not resubmitted and the microphone and audio do not restart automatically.

## Provider references

[ElevenLabs transcription](https://elevenlabs.io/docs/api-reference/speech-to-text/convert) and [streaming speech](https://elevenlabs.io/docs/api-reference/text-to-speech/stream). Live uses George (`JBFqnCBsd6RMkjVDRZzb`) and preserves transcript text while normalizing speech pronunciation (HIPAA → Hippa; EHR → E-H-R).

Phase #220 tracks readiness. This document describes interfaces, not a claim of production voice delivery.

import { useCallback, useLayoutEffect, useRef, useState } from "react";
import { createMicrophoneCapture } from "../../../lib/voice/captureMicrophone";
import { transcribeVoice } from "../../../lib/voice/transcribeVoice";
import type { VoiceSource, VoiceTranscript } from "../../../lib/voice/types";

type Status = "idle" | "requesting" | "recording" | "transcribing" | "error";
interface Attempt {
  generation: number;
  recording: Blob;
  operationId: string;
  source: VoiceSource;
}

/** Capture an editable draft; retries retain the same operation identity. */
export function useVoiceCapture({
  apiBaseUrl,
  sessionId,
  source,
  onTranscript,
}: {
  apiBaseUrl: string;
  sessionId: string;
  source: VoiceSource | null;
  onTranscript: (transcript: VoiceTranscript) => void;
}) {
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  const busy = useRef(false);
  const microphone = useRef<ReturnType<typeof createMicrophoneCapture> | null>(null);
  const request = useRef<AbortController | null>(null);
  const retry = useRef<Attempt | null>(null);
  const callback = useRef(onTranscript);
  useLayoutEffect(() => {
    callback.current = onTranscript;
  }, [onTranscript]);
  const cancel = useCallback(() => {
    generation.current++;
    busy.current = false;
    microphone.current?.cancel();
    microphone.current = null;
    request.current?.abort();
    request.current = null;
    retry.current = null;
    setStatus("idle");
    setError(null);
  }, []);
  const turnSeq = source?.turnSeq;
  const runId = source?.runId;
  const exchangeSequence = source?.exchangeSequence;
  useLayoutEffect(() => cancel, [cancel, apiBaseUrl, sessionId, turnSeq, runId, exchangeSequence]);
  const upload = async (attempt: Attempt) => {
    const abort = new AbortController();
    request.current = abort;
    busy.current = true;
    setStatus("transcribing");
    setError(null);
    const timeout = setTimeout(() => abort.abort(), 45_000);
    try {
      const transcript = await transcribeVoice(
        { apiBaseUrl, sessionId, source: attempt.source, operationId: attempt.operationId },
        attempt.recording,
        abort.signal,
      );
      if (generation.current !== attempt.generation) return;
      retry.current = null;
      setStatus("idle");
      callback.current(transcript);
    } catch {
      if (generation.current !== attempt.generation) return;
      setStatus("error");
      setError("Transcription is unavailable. Retry this recording or type your answer.");
    } finally {
      clearTimeout(timeout);
      if (generation.current === attempt.generation) {
        busy.current = false;
        request.current = null;
      }
    }
  };
  const finish = async () => {
    const capture = microphone.current;
    if (!capture || busy.current || !source) return;
    busy.current = true;
    const current = generation.current;
    setStatus("transcribing");
    try {
      const recording = await capture.finish();
      if (generation.current !== current) return;
      microphone.current = null;
      const attempt = { generation: current, recording, operationId: crypto.randomUUID(), source };
      retry.current = attempt;
      await upload(attempt);
    } catch {
      if (generation.current !== current) return;
      busy.current = false;
      setStatus("error");
      capture.cancel();
      microphone.current = null;
      setError("No usable recording was captured. Try again or type your answer.");
    }
  };
  return {
    status,
    error,
    cancel,
    finish,
    canRetry: status === "error" && retry.current !== null,
    retry: async () => {
      if (!busy.current && retry.current) await upload(retry.current);
    },
    start: async () => {
      if (!source || busy.current || microphone.current) return;
      cancel();
      const current = generation.current;
      busy.current = true;
      setStatus("requesting");
      const capture = createMicrophoneCapture({
        onLimit: () => {
          void finish();
        },
      });
      microphone.current = capture;
      try {
        await capture.start();
        if (generation.current !== current) return;
        busy.current = false;
        setStatus("recording");
      } catch {
        if (generation.current !== current) return;
        microphone.current = null;
        busy.current = false;
        setStatus("error");
        setError(
          "Microphone access is unavailable. Check browser permissions or type your answer.",
        );
      }
    },
  };
}

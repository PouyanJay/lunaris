import { SessionMediaContext } from "../SessionMediaContext";
import { useContext, useLayoutEffect, useRef, useState } from "react";
import type { VoiceSource, VoiceTranscript } from "../../../lib/voice/types";
import { useVoiceCapture } from "./useVoiceCapture";
import { useVoicePlayback } from "./useVoicePlayback";

export interface VoiceSessionControlsProps {
  apiBaseUrl: string;
  sessionId: string;
  answerSource: VoiceSource | null;
  speechSource: VoiceSource | null;
  canAnswer: boolean;
  busy: boolean;
  onAnswer: (text: string) => void;
  /** Deliver drafts to an existing composer without creating another answer form. */
  onTranscript?: (transcript: VoiceTranscript) => void;
  speechKind?: "tutor" | "simulator";
}

const sourceKey = (source: VoiceSource | null) =>
  JSON.stringify([source?.turnSeq, source?.runId, source?.exchangeSequence ?? null]);

/** Coordinates local voice lifecycle and fences drafts against session changes. */
export function useSessionVoiceControls({
  apiBaseUrl,
  sessionId,
  answerSource,
  speechSource,
  canAnswer,
  busy,
  onAnswer,
  onTranscript,
}: VoiceSessionControlsProps) {
  const media = useContext(SessionMediaContext);
  const scope = JSON.stringify([apiBaseUrl, sessionId, sourceKey(answerSource), canAnswer, busy]);
  const currentScope = useRef(scope);
  const handledOperations = useRef(new Set<string>());
  const [deliveredScope, setDeliveredScope] = useState<string | null>(null);
  const [draft, setDraft] = useState<{ scope: string; transcript: VoiceTranscript } | null>(null);
  useLayoutEffect(() => {
    currentScope.current = scope;
  }, [scope]);
  const capture = useVoiceCapture({
    apiBaseUrl,
    sessionId,
    source: canAnswer && !busy ? answerSource : null,
    onTranscript: (transcript) => {
      if (
        currentScope.current === scope &&
        canAnswer &&
        !busy &&
        sourceKey(transcript.source) === sourceKey(answerSource) &&
        !handledOperations.current.has(transcript.operationId)
      ) {
        if (onTranscript) {
          handledOperations.current.add(transcript.operationId);
          setDraft(null);
          setDeliveredScope(scope);
          onTranscript(transcript);
        } else {
          setDraft({ scope, transcript });
        }
      }
    },
  });
  const playback = useVoicePlayback({ apiBaseUrl, sessionId, source: speechSource });
  const cancelCapture = capture.cancel;
  const stopPlayback = playback.stop;
  useLayoutEffect(
    () =>
      media?.register("voice", () => {
        cancelCapture();
        stopPlayback();
        setDraft(null);
        setDeliveredScope(null);
      }),
    [media, cancelCapture, stopPlayback],
  );
  useLayoutEffect(() => {
    setDraft(null);
    setDeliveredScope(null);
    cancelCapture();
    stopPlayback();
    return () => {
      cancelCapture();
      stopPlayback();
    };
  }, [scope, cancelCapture, stopPlayback]);
  useLayoutEffect(() => {
    const stopHidden = () => {
      if (document.visibilityState !== "hidden") return;
      cancelCapture();
      stopPlayback();
      setDraft(null);
      setDeliveredScope(null);
    };
    document.addEventListener("visibilitychange", stopHidden);
    return () => document.removeEventListener("visibilitychange", stopHidden);
  }, [cancelCapture, stopPlayback]);

  const visibleDraft = draft?.scope === scope && canAnswer && !busy ? draft.transcript : null;
  const clearDraft = () => {
    setDraft(null);
    setDeliveredScope(null);
  };
  return {
    capture,
    playback,
    visibleDraft,
    delivered: deliveredScope === scope && canAnswer && !busy,
    clearDraft,
    play: () => {
      if (media?.activate("voice") === false) return;
      void playback.play();
    },
    start: () => {
      if (media?.activate("voice") === false) return;
      stopPlayback();
      clearDraft();
      void capture.start();
    },
    cancel: () => {
      cancelCapture();
      clearDraft();
    },
    confirm: (text: string) => {
      if (
        !visibleDraft ||
        currentScope.current !== scope ||
        !canAnswer ||
        busy ||
        handledOperations.current.has(visibleDraft.operationId)
      )
        return;
      handledOperations.current.add(visibleDraft.operationId);
      clearDraft();
      cancelCapture();
      stopPlayback();
      onAnswer(text);
    },
  };
}

import { Button } from "../../primitives/Button";
import { AnswerForm } from "../AnswerForm";
import { useSessionVoiceControls, type VoiceSessionControlsProps } from "./useSessionVoiceControls";
import styles from "./VoiceSessionControls.module.css";

/** Optional voice transport: reviewed transcripts use the host's ordinary answer callback. */
export function VoiceSessionControls(props: VoiceSessionControlsProps) {
  const { answerSource, speechSource, canAnswer, busy, onTranscript, speechKind = "tutor" } = props;
  const voice = useSessionVoiceControls(props);
  const { capture, playback, visibleDraft } = voice;
  const activeCapture = ["requesting", "recording", "transcribing"].includes(capture.status);
  const activePlayback = ["loading", "playing"].includes(playback.status);
  const captureStatus = {
    idle: "",
    requesting: "Waiting for microphone permission…",
    recording: "Recording · up to 60 seconds",
    transcribing: "Transcribing…",
    error: "",
  }[capture.status];

  const statusText =
    captureStatus ||
    (playback.status === "loading"
      ? "Preparing audio…"
      : playback.status === "playing"
        ? "Playing audio"
        : "");
  if (!answerSource && !speechSource) return null;

  return (
    <section className={styles.region} aria-label="Voice controls">
      <div className={styles.actions}>
        {canAnswer && (
          <>
            {capture.status === "recording" ? (
              <Button onClick={() => void capture.finish()}>Finish recording</Button>
            ) : (
              <Button disabled={busy || !answerSource || activeCapture} onClick={voice.start}>
                Speak
              </Button>
            )}
            {activeCapture && (
              <Button variant="ghost" onClick={voice.cancel}>
                {capture.status === "transcribing" ? "Cancel transcription" : "Cancel recording"}
              </Button>
            )}
            {capture.canRetry && !busy && (
              <Button onClick={() => void capture.retry()}>Retry transcription</Button>
            )}
          </>
        )}
        {activePlayback ? (
          <Button onClick={playback.stop}>Stop audio</Button>
        ) : (
          <Button disabled={!speechSource || busy || activeCapture} onClick={voice.play}>
            {speechKind === "simulator" ? "Read reaction" : "Read aloud"}
          </Button>
        )}
      </div>
      {statusText && (
        <p className={styles.status} role="status">
          {statusText}
        </p>
      )}
      {(capture.error || playback.error) && (
        <p className={styles.error} role="alert">
          {capture.error || playback.error}
        </p>
      )}
      {canAnswer && (
        <p className={styles.hint}>
          Speak, review your transcript, then send. You can still type your answer.
        </p>
      )}
      {voice.delivered && (
        <p className={styles.hint} role="status">
          Your transcript is ready. Review it before sending.
        </p>
      )}
      {visibleDraft && !onTranscript && (
        <div className={styles.preview}>
          <p className={styles.hint}>Review and edit your transcript before sending.</p>
          <AnswerForm
            key={visibleDraft.operationId}
            criterion={null}
            initialAnswer={visibleDraft.text}
            busy={busy}
            embedded
            onAnswer={voice.confirm}
          />
          <Button variant="ghost" onClick={voice.clearDraft}>
            Discard transcript
          </Button>
        </div>
      )}
    </section>
  );
}

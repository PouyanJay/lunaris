import { useId } from "react";
import { useCorpusClipPlayback } from "./useCorpusClipPlayback";
import { Button } from "../primitives/Button";
import { formatMediaDuration } from "../../lib/mediaDuration";
import styles from "./CorpusClipPlayer.module.css";

interface Clip {
  assetId: string;
  title: string;
  startS: number;
  endS: number;
  transcript: { startS: number; endS: number; text: string }[];
  sourceLabel: string;
}
interface CorpusClipPlayerProps {
  clip: Clip;
  getSource: (assetId: string, signal: AbortSignal) => Promise<string>;
  /** Changes discard media and pending requests when the standing turn changes. */
  playbackScope: string;
  /** Stop other audio before this clip begins; never starts a microphone. */
  onPlaybackStart?: () => void;
  /** Changing this value interrupts playback and outstanding source resolution. */
  interruptionKey?: string | number;
}

function validClip(clip: Clip): boolean {
  return (
    Number.isFinite(clip.startS) &&
    Number.isFinite(clip.endS) &&
    clip.startS >= 0 &&
    clip.endS > clip.startS &&
    clip.endS - clip.startS <= 90 &&
    clip.transcript.length > 0 &&
    clip.transcript.every(
      (cue) =>
        Number.isFinite(cue.startS) &&
        Number.isFinite(cue.endS) &&
        cue.startS >= clip.startS &&
        cue.endS <= clip.endS &&
        cue.endS > cue.startS &&
        cue.text.trim(),
    )
  );
}
function cueTime(seconds: number): string {
  const whole = Math.floor(seconds);
  return `${String(Math.floor(whole / 3600)).padStart(2, "0")}:${String(Math.floor(whole / 60) % 60).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")}.${String(Math.floor((seconds - whole) * 1000)).padStart(3, "0")}`;
}
function captions(clip: Clip): string {
  return `data:text/vtt;charset=utf-8,${encodeURIComponent(
    "WEBVTT\n\n" +
      clip.transcript
        .map(
          (cue) =>
            `${cueTime(cue.startS)} --> ${cueTime(cue.endS)}\n${cue.text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")}\n`,
        )
        .join("\n"),
  )}`;
}

/** Bounded, explicitly started playback of a verified material; media gestures award no credit. */
export function CorpusClipPlayer(props: CorpusClipPlayerProps) {
  if (!validClip(props.clip))
    return <p role="alert">Clip unavailable. Continue with the lesson.</p>;
  return <ClipPlayback key={JSON.stringify([props.playbackScope, props.clip])} {...props} />;
}

function ClipPlayback({
  clip,
  getSource,
  onPlaybackStart,
  interruptionKey,
}: CorpusClipPlayerProps) {
  const id = useId();
  const { videoRef, url, state, playing, waiting, time, load, play, seek, mediaEvents } =
    useCorpusClipPlayback({ clip, getSource, onPlaybackStart, interruptionKey });
  return (
    <section className={styles.root} aria-labelledby={`${id}-title`}>
      <header className={styles.header}>
        <h3 id={`${id}-title`}>{clip.title}</h3>
        <p>{clip.sourceLabel}</p>
      </header>
      <video
        ref={videoRef}
        className={styles.video}
        src={url}
        preload="metadata"
        playsInline
        aria-label={clip.title}
        {...mediaEvents}
      >
        <track kind="captions" srcLang="en" label="Transcript" src={captions(clip)} default />
      </video>
      <div className={styles.controls}>
        {state !== "unavailable" && (
          <Button
            aria-disabled={state === "loading"}
            onClick={() => {
              if (state === "loading") return;
              if (state === "ready") void play();
              else void load();
            }}
          >
            {state === "loading"
              ? "Loading clip…"
              : state === "error"
                ? "Refresh clip"
                : state !== "ready"
                  ? "Load clip"
                  : waiting
                    ? "Cancel playback"
                    : playing
                      ? "Pause clip"
                      : "Play clip"}
          </Button>
        )}
        {state === "ready" && (
          <>
            <label className={styles.seek}>
              Seek clip
              <input
                type="range"
                min={clip.startS}
                max={clip.endS}
                step="0.1"
                value={time}
                aria-valuetext={`${formatMediaDuration(time - clip.startS)} of ${formatMediaDuration(clip.endS - clip.startS)}`}
                onChange={(event) => seek(Number(event.target.value))}
              />
            </label>
            <span className={styles.time}>
              {formatMediaDuration(time - clip.startS)} /{" "}
              {formatMediaDuration(clip.endS - clip.startS)}
            </span>
          </>
        )}
      </div>
      {state === "loading" && <p role="status">Loading clip…</p>}
      {waiting && <p role="status">Buffering clip…</p>}
      {state === "error" && (
        <p role="alert">
          The clip could not play or its access expired. Refresh the clip to try again, or read the
          transcript.
        </p>
      )}
      {state === "unavailable" && (
        <p role="alert">Clip unavailable. Read the transcript or continue with the lesson.</p>
      )}
      <details className={styles.transcript}>
        <summary>Transcript</summary>
        {clip.transcript.map((cue, index) => (
          <p key={index}>{cue.text}</p>
        ))}
      </details>
    </section>
  );
}

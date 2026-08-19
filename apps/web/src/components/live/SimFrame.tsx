import { useEffect, useRef, useState } from "react";

import styles from "./SimFrame.module.css";

/** The message a simulator sends when the learner has done something worth reporting.
 *
 *  Pinned as a literal on both sides, like every other cross-deployable contract in Live: the
 *  document in the frame is served by the API and this code ships in the SPA, so a shared constant
 *  would only prove agreement at commit time. Drift here is a simulator a learner can act in whose
 *  work never becomes evidence — silent on both sides. */
export const SIM_REPORT = "lunaris.sim.report";

interface SimReport {
  type: typeof SIM_REPORT;
  appId: string;
  /** The simulator's own account of what the learner did, in words.
   *
   *  Words rather than a state blob, because this goes in through the ordinary answer path and is
   *  graded by the same separate grader against the same staged criterion. A simulator knows what
   *  happened in it; the browser does not, and must not be the thing that decides. */
  report: string;
}

interface SimFrameProps {
  /** Where the simulator loads from. Already refused by the server unless it is `http(s)` or a
   *  same-origin path, so this does not re-decide what a frame may run. */
  url: string;
  title: string;
  /** Which simulator the turn mounted. A report naming a different one is ignored. */
  appId: string;
  /** False on a past turn, where the frame is a record of what was mounted rather than a live
   *  instrument. It still renders — a transcript that dropped the simulator would be a transcript
   *  missing the thing the learner was actually assessed by. */
  answerable: boolean;
  busy: boolean;
  onAnswer: (report: string) => void;
}

/** A simulator, sandboxed, and the one message it is allowed to send back (Tier 3, P2b T6).
 *
 *  **`sandbox` without `allow-same-origin` is the whole security posture, and it is deliberate.**
 *  The document loads from our own API origin, so a frame granted same-origin would run with our
 *  cookies, our storage and our fetch credentials — and Phase 3's simulators are *generated*, which
 *  makes that the difference between a sandbox and a shell. Denied it, the frame gets an opaque
 *  origin: it can run scripts and it can reach nothing of ours.
 *
 *  That posture is why the message check is by **source and not by origin**. An opaque-origin frame
 *  posts with `origin === "null"`, which is a value any other framed document can also present, so
 *  it identifies nothing. `event.source === iframe.contentWindow` is the check that actually says
 *  "this came from the frame I mounted".
 *
 *  What the frame is trusted with, stated plainly: it may say what the learner did, and that
 *  sentence becomes their answer. It cannot grade it — the separate grader does, against the
 *  criterion the turn staged (U1) — so the worst a hostile simulator achieves is a bad answer for
 *  its own learner, which is the same power the learner already has by typing one. */
export function SimFrame({ url, title, appId, answerable, busy, onAnswer }: SimFrameProps) {
  const frame = useRef<HTMLIFrameElement>(null);
  // A report is a one-shot: the turn advances the moment it lands, and a second one would be graded
  // against whatever question replaced it. The frame is not told to stop, because it is somebody
  // else's document — refusing to listen is the half we control.
  const [sent, setSent] = useState(false);

  useEffect(() => {
    if (!answerable || sent) {
      return;
    }
    const onMessage = (event: MessageEvent) => {
      if (event.source !== frame.current?.contentWindow) {
        return;
      }
      const data = event.data as Partial<SimReport> | null;
      if (data?.type !== SIM_REPORT || data.appId !== appId) {
        return;
      }
      const report = typeof data.report === "string" ? data.report.trim() : "";
      if (!report) {
        return;
      }
      setSent(true);
      onAnswer(report);
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [answerable, sent, appId, onAnswer]);

  return (
    <div className={styles.mount}>
      <iframe
        ref={frame}
        className={styles.frame}
        src={url}
        title={title}
        // Scripts, and nothing else. No `allow-same-origin` (see above), no forms, no popups, no
        // top-level navigation — a simulator that could navigate the top frame could take a learner
        // off Lunaris mid-session.
        sandbox="allow-scripts"
        // Its own referrer policy as well as the API's headers: a generated document should not
        // learn which session a learner is in from the URL that framed it.
        referrerPolicy="no-referrer"
        loading="lazy"
      />
      <p className={styles.status} role="status">
        {busy
          ? "Marking what you did…"
          : sent
            ? "Sent what you did in the simulator."
            : answerable
              ? "Work in the simulator, then send what you did from inside it."
              : "This simulator is part of the record of that turn."}
      </p>
    </div>
  );
}

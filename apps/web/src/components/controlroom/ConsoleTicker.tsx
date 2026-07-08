import { useEffect, useRef } from "react";

import type { TimelineEntry } from "../../lib/buildTimeline";
import { StatusDot } from "../primitives/StatusDot";
import styles from "./ConsoleTicker.module.css";

/** Auto-follow threshold: keep following new rows while the reader sits near the foot. */
const FOLLOW_PIN_PX = 48;

interface ConsoleTickerProps {
  entries: TimelineEntry[];
  /** Pulses the live dot while the run streams; a finished/replayed run reads as a still log. */
  live: boolean;
}

/** The agent console (P8): every capability call and reasoning beat as one compact ticker —
 *  tool rows (glyph · mono tool chip · args · result) and italic reasoning lines. The same fold
 *  the transcript renders, re-lensed; the transcript keeps the branded, expandable cards. */
export function ConsoleTicker({ entries, live }: ConsoleTickerProps) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const pinnedRef = useRef(true);

  // Follow new rows while pinned near the foot; release when the reader scrolls up.
  useEffect(() => {
    const body = bodyRef.current;
    if (!body || !pinnedRef.current) return;
    body.scrollTop = body.scrollHeight;
  }, [entries.length]);

  const onScroll = () => {
    const body = bodyRef.current;
    if (!body) return;
    pinnedRef.current = body.scrollHeight - body.scrollTop - body.clientHeight < FOLLOW_PIN_PX;
  };

  return (
    <section className={styles.console} aria-label="Agent console">
      <header className={styles.head}>
        <span className="eyebrow">Agent console</span>
        {live && <StatusDot label="live" tone="accent" live />}
        <span className={`${styles.hint} mono`}>every capability runs as a tool</span>
      </header>
      <div ref={bodyRef} className={`${styles.body} scroller`} onScroll={onScroll}>
        {entries.length === 0 ? (
          <p className={styles.empty}>Waiting for the agent’s first move…</p>
        ) : (
          <ul className={styles.rows}>
            {entries.map((entry) => (
              <li key={entry.key} className={styles.row}>
                {entry.kind === "tool" ? (
                  <>
                    <span
                      className={`${styles.glyph} mono`}
                      data-state={entry.result === null ? "running" : "done"}
                      aria-hidden="true"
                    >
                      {entry.result === null ? "●" : "✓"}
                    </span>
                    <span className={`${styles.toolChip} mono`}>{entry.tool}</span>
                    <span className={`${styles.args} mono`}>{compactArgs(entry.args)}</span>
                    {presentableResult(entry.result) && (
                      <span className={`${styles.result} mono`}>{entry.result}</span>
                    )}
                    <span className="sr-only">
                      {entry.result === null ? "running" : "completed"}
                    </span>
                  </>
                ) : entry.kind === "source" ? (
                  <>
                    <span
                      className={`${styles.glyph} mono`}
                      data-state={entry.source.accepted ? "done" : "rejected"}
                      aria-hidden="true"
                    >
                      {entry.source.accepted ? "✓" : "✕"}
                    </span>
                    <span className={`${styles.args} mono`}>{entry.source.domain}</span>
                    <span className={`${styles.result} mono`}>
                      {entry.source.accepted ? "accepted" : "rejected"}
                      {entry.source.trustTier ? ` · ${entry.source.trustTier}` : ""}
                    </span>
                  </>
                ) : (
                  <span className={styles.reasoning}>{entry.text}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

/** One-line compaction of tool args for the ticker (the transcript renders them branded). */
function compactArgs(args: Record<string, unknown> | null): string {
  if (!args) return "";
  return Object.entries(args)
    .map(([key, value]) => `${key}=${typeof value === "string" ? value : JSON.stringify(value)}`)
    .join(" ");
}

/** Whether a tool result reads as a one-line outcome. JSON payloads (often truncated mid-stream)
 *  never leak into the ticker — the transcript's branded renderers own them; the ✓ glyph already
 *  says the call completed. */
function presentableResult(result: string | null): boolean {
  if (result === null || result === "") return false;
  const head = result.trimStart();
  return !head.startsWith("{") && !head.startsWith("[");
}

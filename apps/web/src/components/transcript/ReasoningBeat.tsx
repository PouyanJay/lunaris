import { useMemo } from "react";

import { parseReasoning } from "../../lib/parseReasoning";
import { JsonArtifact } from "./JsonArtifact";
import styles from "./ReasoningBeat.module.css";

interface ReasoningBeatProps {
  /** The agent's reasoning text (possibly with JSON/code blobs embedded). */
  text: string;
  /** True when this is the live, still-streaming beat — shows a caret on its trailing prose. */
  streaming: boolean;
}

/** One reasoning beat: prose rendered as text, with any embedded JSON/code blobs lifted into bounded
 *  {@link JsonArtifact}s so a raw dump can't take over the transcript. A live caret trails the last
 *  prose run while the beat is still streaming (a trailing blob shows its own "streaming…" state). */
export function ReasoningBeat({ text, streaming }: ReasoningBeatProps) {
  const segments = useMemo(() => parseReasoning(text), [text]);
  const lastIndex = segments.length - 1;

  return (
    <div className={styles.beat}>
      {segments.map((segment, index) =>
        segment.kind === "prose" ? (
          <p key={`p-${index}`} className={styles.prose}>
            {segment.text}
            {streaming && index === lastIndex && (
              <span className={styles.caret} aria-hidden="true" data-testid="reasoning-caret" />
            )}
          </p>
        ) : (
          <JsonArtifact key={`j-${index}`} source={segment.source} closed={segment.closed} />
        ),
      )}
    </div>
  );
}

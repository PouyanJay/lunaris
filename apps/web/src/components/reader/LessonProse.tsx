import { Fragment } from "react";

import { splitSentences } from "./claimMatch";
import { paragraphize } from "./prose";
import styles from "./LessonProse.module.css";

interface LessonProseProps {
  prose: string;
  /** sentence index → the annotation id whose claim matched it (renders that sentence as a link). */
  sentenceMarks: Map<number, string>;
  activeClaimId: string | null;
  onSelectClaim: (id: string) => void;
}

/** A phase's prose, broken into readable paragraphs, with any claim-matched sentence rendered as an
 *  inline cross-link (`<mark>`-styled button) to its rail annotation. Clicking a marked sentence
 *  selects its claim (highlighting the rail entry); the rail selecting the claim highlights the
 *  sentence here. A sentence with no confident claim match is plain prose — its claim links to the
 *  phase instead (handled by the reader). */
export function LessonProse({
  prose,
  sentenceMarks,
  activeClaimId,
  onSelectClaim,
}: LessonProseProps) {
  const sentences = splitSentences(prose);
  // Pre-P7-arc / empty prose: render the raw string so nothing is ever dropped.
  if (sentences.length === 0) {
    return <p className={styles.prose}>{prose}</p>;
  }
  const paragraphs = paragraphize(prose);

  return (
    <div className={styles.prose}>
      {paragraphs.map((sentenceIndexes, paragraphIndex) => (
        <p key={paragraphIndex} className={styles.paragraph}>
          {sentenceIndexes.map((sentenceIndex, position) => {
            const sentence = sentences[sentenceIndex] ?? "";
            const spacer = position < sentenceIndexes.length - 1 ? " " : "";
            const claimId = sentenceMarks.get(sentenceIndex);
            if (!claimId) {
              return <Fragment key={sentenceIndex}>{`${sentence}${spacer}`}</Fragment>;
            }
            const active = claimId === activeClaimId;
            return (
              <Fragment key={sentenceIndex}>
                <button
                  type="button"
                  data-claim-id={claimId}
                  className={`${styles.mark} ${active ? styles.markActive : ""}`}
                  aria-pressed={active}
                  aria-label={`Show the source note for: ${sentence}`}
                  onClick={() => onSelectClaim(claimId)}
                >
                  {sentence}
                </button>
                {spacer}
              </Fragment>
            );
          })}
        </p>
      ))}
    </div>
  );
}

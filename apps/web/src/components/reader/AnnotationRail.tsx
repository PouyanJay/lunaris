import { useEffect, useRef } from "react";

import { StatusDot } from "../primitives/StatusDot";
import { type Annotation, groupByPhase, verifierStatusTone } from "./annotations";
import { ClaimProvenance } from "./ClaimProvenance";
import { scrollIntoViewSafe } from "./scrollIntoViewSafe";
import styles from "./AnnotationRail.module.css";

interface AnnotationRailProps {
  annotations: Annotation[];
  activeClaimId: string | null;
  onSelect: (id: string) => void;
  /** Rendered as a drawer on narrow screens; the close control is shown only then (CSS). */
  onClose?: () => void;
  reduceMotion?: boolean;
}

/** The verifier annotations as a parallel layer beside the reading column (req 1): each claim's
 *  status + grounding source, lifted out of the prose so the lesson reads clean. Selecting an entry
 *  highlights the place it refers to in the prose (its matched sentence, or its phase); a prose
 *  cross-link selects the entry here. Grouped by teaching phase so the rail mirrors the lesson. */
export function AnnotationRail({
  annotations,
  activeClaimId,
  onSelect,
  onClose,
  reduceMotion = false,
}: AnnotationRailProps) {
  const itemRefs = useRef(new Map<string, HTMLLIElement>());

  // When a prose cross-link selects a claim, bring its rail entry into view.
  useEffect(() => {
    if (!activeClaimId) return;
    scrollIntoViewSafe(itemRefs.current.get(activeClaimId), reduceMotion);
  }, [activeClaimId, reduceMotion]);

  const groups = groupByPhase(annotations);

  return (
    <aside className={styles.rail} aria-label="Sources and checks">
      <header className={styles.head}>
        <div>
          <p className="eyebrow">Verification</p>
          <h3 className={styles.title}>Sources &amp; checks</h3>
        </div>
        {onClose && (
          <button
            type="button"
            className={styles.close}
            onClick={onClose}
            aria-label="Close sources and checks"
          >
            ✕
          </button>
        )}
      </header>

      {annotations.length === 0 ? (
        <p className={styles.empty}>No claims to verify in this lesson.</p>
      ) : (
        groups.map((group) => (
          <section key={group.phaseKey} className={styles.group}>
            <p className={styles.groupLabel}>{group.phaseLabel}</p>
            <ul className={styles.list}>
              {group.items.map((annotation) => {
                const active = annotation.id === activeClaimId;
                return (
                  <li
                    key={annotation.id}
                    ref={(node) => {
                      if (node) itemRefs.current.set(annotation.id, node);
                      else itemRefs.current.delete(annotation.id);
                    }}
                    className={`${styles.item} ${active ? styles.itemActive : ""}`}
                  >
                    <button
                      type="button"
                      className={styles.trigger}
                      aria-pressed={active}
                      aria-label={`Locate in the lesson: ${annotation.claim.text}`}
                      onClick={() => onSelect(annotation.id)}
                    >
                      <StatusDot
                        label={annotation.claim.verifierStatus}
                        tone={verifierStatusTone(annotation.claim.verifierStatus)}
                      />
                      <span className={styles.text}>{annotation.claim.text}</span>
                    </button>
                    {annotation.matchedSentence === null && (
                      <p className={styles.approx}>
                        ↳ Linked to the “{annotation.phaseLabel}” section
                      </p>
                    )}
                    {annotation.citation ? (
                      <ClaimProvenance citation={annotation.citation} />
                    ) : (
                      <p className={styles.uncited}>No source on record</p>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        ))
      )}
    </aside>
  );
}

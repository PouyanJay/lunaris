import { useEffect, useRef } from "react";

import { useAutoHideScroll } from "../../hooks/useAutoHideScroll";
import { BookmarkToggle } from "../bookmarks/BookmarkToggle";
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
  /** Collapse the rail to give the reading column full width (wide screens only, shown via CSS). */
  onCollapse?: () => void;
  reduceMotion?: boolean;
  /** Where these claims live — lets a cited claim be bookmarked as a source (keyed on its
   *  citation; claims carry no server id). Absent = no save affordance (e.g. offline). */
  sourceContext?: { courseId: string; courseTitle: string; lessonId: string | null };
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
  onCollapse,
  reduceMotion = false,
  sourceContext,
}: AnnotationRailProps) {
  const itemRefs = useRef(new Map<string, HTMLLIElement>());
  const railRef = useRef<HTMLElement>(null);
  useAutoHideScroll(railRef);

  // When a prose cross-link selects a claim, bring its rail entry into view.
  useEffect(() => {
    if (!activeClaimId) return;
    scrollIntoViewSafe(itemRefs.current.get(activeClaimId), reduceMotion);
  }, [activeClaimId, reduceMotion]);

  const groups = groupByPhase(annotations);
  // The verification banner tells the truth about this lesson's grounding: full verification
  // only when every claim held up, the honest fraction otherwise. Sources are counted distinct —
  // several claims often ground on one citation.
  const supportedCount = annotations.filter(
    (entry) => entry.claim.verifierStatus === "supported",
  ).length;
  const sourceCount = new Set(
    annotations.map((entry) => entry.citation?.id).filter((id) => id !== undefined),
  ).size;
  const allSupported = supportedCount === annotations.length;
  const sourcesLabel = `${sourceCount} ${sourceCount === 1 ? "source" : "sources"}`;

  return (
    <aside ref={railRef} className={`${styles.rail} scroller`} aria-label="Sources and checks">
      <header className={styles.head}>
        <div>
          <p className="eyebrow">Verification</p>
          <h3 className={styles.title}>Sources &amp; checks</h3>
        </div>
        {onCollapse && (
          <button
            type="button"
            className={styles.collapse}
            onClick={onCollapse}
            aria-label="Collapse sources and checks"
            title="Collapse"
          >
            <span aria-hidden="true">›</span>
          </button>
        )}
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

      {annotations.length > 0 && (
        <p className={`${styles.banner} ${allSupported ? "" : styles.bannerPartial}`.trim()}>
          <svg
            className={styles.bannerIcon}
            viewBox="0 0 24 24"
            width="16"
            height="16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            {allSupported ? <path d="M20 6 9 17l-5-5" /> : <path d="M12 6v7m0 4v.5" />}
          </svg>
          <span>
            {allSupported ? (
              <>
                Every factual claim in this lesson is verified against{" "}
                <strong className={styles.bannerCount}>{sourcesLabel}</strong>.
              </>
            ) : (
              <>
                {supportedCount} of {annotations.length} claims verified against{" "}
                <strong className={styles.bannerCount}>{sourcesLabel}</strong>.
              </>
            )}
          </span>
        </p>
      )}

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
                      <div className={styles.provenanceRow}>
                        <ClaimProvenance citation={annotation.citation} />
                        {sourceContext && (
                          <BookmarkToggle
                            subject={annotation.citation.title ?? "this source"}
                            draft={{
                              kind: "source",
                              courseId: sourceContext.courseId,
                              targetId: annotation.citation.id,
                              courseTitle: sourceContext.courseTitle,
                              title: annotation.citation.title,
                              lessonId: sourceContext.lessonId,
                              // The claim this source grounds — what the bookmarks card quotes.
                              snippet: annotation.claim.text.slice(0, 2000),
                              trustTier: annotation.citation.trustTier ?? null,
                              credibility: annotation.citation.credibility ?? null,
                            }}
                          />
                        )}
                      </div>
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

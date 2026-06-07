import { useId, useRef } from "react";

import { useAutoHideScroll } from "../../hooks/useAutoHideScroll";
import type { BriefLoadState } from "../../types/clarifier";
import type { DiscoveryDepth } from "../../types/course";
import { Button } from "../primitives/Button";
import { CollapsibleSection } from "../primitives/CollapsibleSection";
import { ClarifierQuestionField } from "../personalize/ClarifierQuestionField";
import styles from "./ConfigRail.module.css";

// Pre-authorized search depth (P6.3): how hard auto-discovery hunts for evidence before authoring.
// Standard is the smart default; Thorough widens the budget at a higher search cost (the override).
const DEPTHS: { value: DiscoveryDepth; label: string; hint: string }[] = [
  { value: "standard", label: "Standard", hint: "Moderate search — the recommended default." },
  { value: "thorough", label: "Thorough", hint: "Searches deeper for more sources." },
];

interface ConfigRailProps {
  /** The topic being configured (from the main column); empty until the learner names one. */
  topic: string;
  /** The learner-tier brief lifecycle (owned by the parent so its answers feed the build). */
  brief: BriefLoadState;
  /** Read (or re-read) the brief for the current topic — the personalize trigger / error retry. */
  onLoadBrief: () => void;
  /** A clarifier answer changed (question id → value). */
  onAnswerChange: (id: string, value: string) => void;
  /** The chosen search depth (smart default + override). */
  depth: DiscoveryDepth;
  onDepthChange: (depth: DiscoveryDepth) => void;
  /** Operator/admin settings live in the Settings panel — this opens it. */
  onOpenSettings: () => void;
  /** Collapse the rail to give the main column full width (wide screens; shown via CSS). */
  onCollapse?: () => void;
  /** Close the rail drawer (narrow screens; shown via CSS). */
  onClose?: () => void;
}

/**
 * The persistent course-setup rail: the editable projection of the brief + build settings, in three
 * progressively-disclosed tiers — (1) learner personalization, always visible, hosting the inferred
 * clarifier (reuses {@link ClarifierQuestionField}); (2) build controls behind an "Advanced"
 * disclosure (search depth); (3) an operator pointer to Settings (no duplicated admin controls). The
 * rail replaces the buried Personalize modal; its chrome (resize/collapse/drawer) is owned by the
 * parent via `useRailLayout`. All learner-tier states are handled: blank / loading / error / ready.
 */
export function ConfigRail({
  topic,
  brief,
  onLoadBrief,
  onAnswerChange,
  depth,
  onDepthChange,
  onOpenSettings,
  onCollapse,
  onClose,
}: ConfigRailProps) {
  const railRef = useRef<HTMLElement>(null);
  const learnerTitleId = useId();
  const depthName = useId();
  // The rail's own thin, auto-hiding scrollbar (matches the reader rail).
  useAutoHideScroll(railRef);

  return (
    <aside ref={railRef} className={`${styles.rail} scroller`} aria-label="Course setup">
      <header className={styles.head}>
        <div>
          <p className="eyebrow">Configure</p>
          <h2 className={styles.title}>Course setup</h2>
        </div>
        {onCollapse && (
          <button
            type="button"
            className={styles.collapse}
            onClick={onCollapse}
            aria-label="Collapse course setup"
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
            aria-label="Close course setup"
          >
            ✕
          </button>
        )}
      </header>

      {/* Tier 1 — learner personalization, always visible. */}
      <section className={styles.tier} aria-labelledby={learnerTitleId}>
        <div className={styles.tierHead}>
          <p className="eyebrow">Personalize</p>
          <h3 id={learnerTitleId} className={styles.tierTitle}>
            For you
          </h3>
        </div>

        {brief.status === "blank" && topic.trim() === "" && (
          <p className={styles.muted}>Name a topic to tailor the course to you.</p>
        )}

        {brief.status === "blank" && topic.trim() !== "" && (
          <div className={styles.stack}>
            <p className={styles.muted}>
              We&rsquo;ll read your goal and pre-fill the details &mdash; confirm or adjust them, then
              build. Skip this and we&rsquo;ll use the inference.
            </p>
            <Button variant="secondary" onClick={onLoadBrief}>
              Personalize this topic
            </Button>
          </div>
        )}

        {brief.status === "loading" && (
          <p className={styles.muted} role="status">
            Reading your goal&hellip;
          </p>
        )}

        {brief.status === "error" && (
          <div className={styles.stack}>
            <p className={styles.error} role="alert">
              {brief.message}
            </p>
            <Button variant="secondary" onClick={onLoadBrief}>
              Try again
            </Button>
          </div>
        )}

        {brief.status === "ready" && (
          <div className={styles.stack}>
            <p className={styles.read}>
              We read this as{" "}
              <strong>{brief.data.brief.goal || brief.data.brief.subject}</strong>.
            </p>
            <div className={styles.questions}>
              {brief.data.clarifier.questions.map((question) => (
                <ClarifierQuestionField
                  key={question.id}
                  question={question}
                  value={brief.answers[question.id] ?? ""}
                  onChange={(value) => onAnswerChange(question.id, value)}
                />
              ))}
            </div>
          </div>
        )}
      </section>

      {/* Tier 2 — build controls behind a disclosure. Only knobs with a real backend effect ship. */}
      <CollapsibleSection eyebrow="Build" title="Advanced" defaultOpen={false}>
        <fieldset className={styles.depth}>
          <legend className={styles.depthLegend}>Search depth</legend>
          <div className={styles.depthOptions}>
            {DEPTHS.map(({ value, label, hint }) => (
              <label key={value} className={styles.depthOption}>
                <input
                  type="radio"
                  name={depthName}
                  className={styles.depthRadio}
                  value={value}
                  checked={depth === value}
                  onChange={() => onDepthChange(value)}
                />
                <span className={styles.depthLabel}>{label}</span>
                <span className={styles.depthHint}>{hint}</span>
              </label>
            ))}
          </div>
        </fieldset>
      </CollapsibleSection>

      {/* Tier 3 — operator/admin lives in Settings; point there rather than duplicate it. */}
      <section className={styles.operator}>
        <p className="eyebrow">Operator</p>
        <p className={styles.muted}>Keys, pipeline, and trusted sources live in Settings.</p>
        <Button variant="secondary" onClick={onOpenSettings}>
          Open Settings&hellip;
        </Button>
      </section>
    </aside>
  );
}

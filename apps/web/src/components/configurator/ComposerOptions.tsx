import type { ReactNode } from "react";

import { Menu, type MenuOption } from "../primitives/Menu";
import { menuRowCaretClass, menuRowClass } from "../primitives/menuRow";
import type { ComposerLevel } from "../../lib/composerLevel";
import type { Product } from "../../lib/product";
import type { DiscoveryDepth } from "../../types/course";
import styles from "./ComposerOptions.module.css";

interface ComposerOptionsProps {
  /** Which product the topic goes to. The bar is Studio's entirely: under Live nothing here can
   *  reach the outcome, so none of it is offered. */
  mode: Product;
  depth: DiscoveryDepth;
  onDepthChange: (depth: DiscoveryDepth) => void;
  level: ComposerLevel;
  onLevelChange: (level: ComposerLevel) => void;
  officialOnly: boolean;
  onOfficialOnlyChange: (value: boolean) => void;
  /** Personalization, rendered as the last chip in the bar. Supplied by the parent, which owns the
   *  brief lifecycle. */
  personalize?: ReactNode;
  /** Opens the Settings panel, where the trusted-domain list actually lives. A callback rather than
   *  a Link: this component stays presentational and free of router context, which is the same rule
   *  that keeps it free of auth context. */
  onOpenTrustedSources?: (() => void) | undefined;
}

const DEPTHS: MenuOption<DiscoveryDepth>[] = [
  { value: "standard", label: "Standard", description: "Fewer sources, faster build" },
  { value: "thorough", label: "Thorough", description: "Wider research. Slower, better grounded" },
];

const LEVELS: MenuOption<ComposerLevel>[] = [
  { value: "recommended", label: "Recommended", description: "Match what we read from your topic" },
  { value: "beginner", label: "Beginner", description: "Assume no prior exposure" },
  { value: "intermediate", label: "Intermediate", description: "Assume the fundamentals" },
  { value: "advanced", label: "Advanced", description: "Skip the basics and go deep" },
];

/** The trust setting reads better as a choice between two named states than as an on/off, because
 *  "off" would have to mean "any source", which is a decision rather than an absence. */
type SourceScope = "any" | "official";

const SOURCES: MenuOption<SourceScope>[] = [
  { value: "any", label: "Any source", description: "Use the best evidence found" },
  {
    value: "official",
    label: "Official only",
    description: "Restrict to primary and authoritative sources",
  },
];

/** The build settings, docked as a bar inside the foot of the composer.
 *
 *  Each setting is a chip that opens a menu explaining what choosing it does, rather than a row of
 *  controls competing with the topic for attention. The bar belongs to Studio: Live composes its
 *  lesson as it teaches, so a build setting could not change its outcome, and a control that cannot
 *  affect anything is worse than no control. Live's own config arrives with the runtime that can
 *  honour it. */
export function ComposerOptions({
  mode,
  depth,
  onDepthChange,
  level,
  onLevelChange,
  officialOnly,
  onOfficialOnlyChange,
  personalize,
  onOpenTrustedSources,
}: ComposerOptionsProps) {
  if (mode === "live") return null;

  return (
    <div className={styles.bar}>
      <Menu label="Depth" value={depth} options={DEPTHS} onChange={onDepthChange} />
      <Menu label="Level" value={level} options={LEVELS} onChange={onLevelChange} />
      <Menu
        label="Sources"
        value={officialOnly ? "official" : "any"}
        options={SOURCES}
        onChange={(scope) => onOfficialOnlyChange(scope === "official")}
        footer={
          // A real destination, not an ornament: the Settings panel that owns the domain list. A
          // row that led nowhere would be the exact thing this bar exists to remove.
          onOpenTrustedSources ? (
            <button type="button" className={menuRowClass} onClick={onOpenTrustedSources}>
              Trusted domains
              <svg
                className={menuRowCaretClass}
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M9 6l6 6-6 6" />
              </svg>
            </button>
          ) : undefined
        }
      />
      {personalize}
    </div>
  );
}

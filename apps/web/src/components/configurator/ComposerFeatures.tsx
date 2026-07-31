import type { Product } from "../../lib/product";
import styles from "./ComposerFeatures.module.css";

interface Feature {
  eyebrow: string;
  title: string;
  body: string;
  /** A simple stroked glyph (24×24 viewBox path data), decorative. */
  path: string;
}

const STUDIO_FEATURES: Feature[] = [
  {
    eyebrow: "Grounded",
    title: "Verified against real sources",
    body: "Every factual claim is checked against retrieved evidence — unsupported ones are cut, not shipped.",
    path: "M12 3l7 4v5c0 4-3 7-7 8-4-1-7-4-7-8V7l7-4zM9.5 12l2 2 3.5-4",
  },
  {
    eyebrow: "Sequenced",
    title: "Prerequisites mapped first",
    body: "Concepts are ordered into a prerequisite graph, so each lesson builds on the ones before it.",
    path: "M6 4h5v5H6V4zm7 11h5v5h-5v-5zM8.5 9v3.5A2.5 2.5 0 0011 15h2.5",
  },
  {
    eyebrow: "Transparent",
    title: "Watch it build, live",
    body: "See the agent research, plan, and write in real time — every tool call and decision streams to you.",
    path: "M3 12s3.5-6 9-6 9 6 9 6-3.5 6-9 6-9-6-9-6zm9 2.5A2.5 2.5 0 1012 9.5a2.5 2.5 0 000 5z",
  },
];

/** Live's equivalent. Deliberately a separate set rather than reworded copy: Live researches no
 *  sources and has no build to watch, so two of Studio's three promises are simply not true of it,
 *  and a shared list would have to be vague enough to cover both. */
const LIVE_FEATURES: Feature[] = [
  {
    eyebrow: "Sequenced",
    title: "Prerequisites mapped first",
    body: "Your topic is decomposed into a concept graph, so the session always teaches something you are ready for.",
    path: "M6 4h5v5H6V4zm7 11h5v5h-5v-5zM8.5 9v3.5A2.5 2.5 0 0011 15h2.5",
  },
  {
    eyebrow: "Responsive",
    title: "Taught in real time",
    body: "A tutor explains, asks, and reacts to what you do — the lesson is composed as you go, not read from a script.",
    path: "M4 5h16v10H9l-5 4V5zm4 5h8M8 12h5",
  },
  {
    eyebrow: "Adaptive",
    title: "Remembers what you know",
    body: "Every answer updates an estimate of what you have mastered, so practice lands where it is still needed.",
    path: "M12 3a6 6 0 016 6c0 2.5-1.5 3.8-2.4 5.1-.6.9-.6 1.4-.6 2.4H9c0-1 0-1.5-.6-2.4C7.5 12.8 6 11.5 6 9a6 6 0 016-6zM9.5 20h5",
  },
];

interface ComposerFeaturesProps {
  /** Which product's promises to show. The cards describe what submitting will actually do, so
   *  showing Studio's under Live would promise work Live never performs. */
  mode?: Product;
}

/** Three restrained, informational cards under the composer explaining what submitting does —
 *  hairline panels with a stroked glyph, eyebrow, title, and one line, not marketing tiles. */
export function ComposerFeatures({ mode = "studio" }: ComposerFeaturesProps) {
  const live = mode === "live";
  return (
    <ul
      className={styles.grid}
      aria-label={live ? "What a Lunaris Live session does" : "What a Lunaris Studio build does"}
    >
      {(live ? LIVE_FEATURES : STUDIO_FEATURES).map((feature) => (
        <li key={feature.title} className={styles.card}>
          <svg
            className={styles.icon}
            viewBox="0 0 24 24"
            width="20"
            height="20"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.75"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d={feature.path} />
          </svg>
          <p className={`eyebrow ${styles.eyebrow}`}>{feature.eyebrow}</p>
          <h3 className={styles.title}>{feature.title}</h3>
          <p className={styles.body}>{feature.body}</p>
        </li>
      ))}
    </ul>
  );
}

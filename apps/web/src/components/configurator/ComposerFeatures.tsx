import styles from "./ComposerFeatures.module.css";

interface Feature {
  eyebrow: string;
  title: string;
  body: string;
  /** A simple stroked glyph (24×24 viewBox path data), decorative. */
  path: string;
}

const FEATURES: Feature[] = [
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

/** Three restrained, informational cards under the composer explaining what a Lunaris build does —
 *  hairline panels with a stroked glyph, eyebrow, title, and one line, not marketing tiles. */
export function ComposerFeatures() {
  return (
    <ul className={styles.grid} aria-label="What a Lunaris build does">
      {FEATURES.map((feature) => (
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

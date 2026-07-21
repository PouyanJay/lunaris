import styles from "./VideoCover.module.css";

interface VideoCoverProps {
  /** The title drawn on the cover (the lesson/module/video title). Omit for a text-free black cover. */
  title?: string | undefined;
  /** A small eyebrow above the title (e.g. "N chapters · MM:SS"). Omit to show none. */
  meta?: string | undefined;
}

/** The designed title card shown over a video's (often dark) poster frame before it plays, so every
 *  video reads as having a real cover. Solid black by design — it sits over media and must stay dark
 *  in both themes (like the CourseCover fixed-art). Decorative (aria-hidden) and non-interactive:
 *  the surrounding play button is the action and clicks fall through to it. */
export function VideoCover({ title, meta }: VideoCoverProps) {
  return (
    <div className={styles.cover} aria-hidden="true">
      {meta ? <span className={styles.eyebrow}>{meta}</span> : null}
      {title ? <h3 className={styles.title}>{title}</h3> : null}
    </div>
  );
}

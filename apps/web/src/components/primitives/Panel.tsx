import type { ComponentProps, ReactNode } from "react";

import styles from "./Panel.module.css";

type PanelProps = ComponentProps<"section"> & {
  /** Optional header text. Named `heading` (not `title`) so the native tooltip attribute
   *  stays available to consumers. */
  heading?: ReactNode;
  /** Trailing muted annotation in the header row (e.g. "inferred", "optional"). */
  cue?: ReactNode;
  /** `subtle` (default) sits on --bg-subtle; `raised` adds a soft shadow on --surface;
   *  `plain` is --surface with a hairline only. */
  variant?: "subtle" | "raised" | "plain";
};

/** A bordered surface — the product's basic container. "Panels, not floating cards": hairline
 *  border, tight radius, soft-or-no shadow. The optional header carries a heading plus a
 *  trailing cue; the body stacks children on the 12px rhythm. */
export function Panel({
  heading,
  cue,
  variant = "subtle",
  className,
  children,
  ...props
}: PanelProps) {
  return (
    <section
      className={`${styles.panel} ${className ?? ""}`.trim()}
      data-variant={variant}
      {...props}
    >
      {heading != null && (
        <div className={styles.head}>
          <span className={styles.heading}>{heading}</span>
          {cue != null && <span className={styles.cue}>{cue}</span>}
        </div>
      )}
      <div className={styles.body}>{children}</div>
    </section>
  );
}

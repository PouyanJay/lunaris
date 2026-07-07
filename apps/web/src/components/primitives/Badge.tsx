import type { ComponentProps } from "react";

import styles from "./Badge.module.css";

/** The tint families a badge can carry. Operation hues (read/create/update/delete) suit tool and
 *  API activity; `meta` is the quiet default; `symbol`/`accent` mark notation and brand emphasis. */
export type BadgeCategory =
  | "read"
  | "create"
  | "update"
  | "delete"
  | "meta"
  | "symbol"
  | "accent";

type BadgeProps = ComponentProps<"span"> & {
  category?: BadgeCategory;
};

/** A tinted, hairline-bordered monospace token chip for keywords, operations, and symbol
 *  notation. The category only re-tints the chip — the word inside carries the meaning, so
 *  colour is never the sole signal (WCAG). */
export function Badge({ category = "meta", className, children, ...props }: BadgeProps) {
  return (
    <span
      className={`mono ${styles.badge} ${className ?? ""}`.trim()}
      data-category={category}
      {...props}
    >
      {children}
    </span>
  );
}

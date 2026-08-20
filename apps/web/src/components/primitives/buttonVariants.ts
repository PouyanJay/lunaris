import styles from "./Button.module.css";

/** How much weight an action carries.
 *
 *  Exported from its own module so every control wearing this skin names the same set: a second
 *  hand-written copy is how a sixth variant would reach one and not the other, with no type error
 *  to say so. Beside the component rather than inside it because a file that exports both a
 *  component and a constant loses fast refresh (the `calloutVariants` precedent). */
export type ButtonVariant = "primary" | "secondary" | "ghost" | "accent" | "danger";

/** The composed class list for an action's skin — one definition, so `Button` and `ButtonLink`
 *  cannot drift in how they assemble it either. */
export function buttonClassName(variant: ButtonVariant, className?: string): string {
  return `${styles.button} ${styles[variant]} ${className ?? ""}`.trim();
}

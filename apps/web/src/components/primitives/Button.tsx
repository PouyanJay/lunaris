import { forwardRef, type ComponentProps } from "react";

import styles from "./Button.module.css";

type ButtonProps = ComponentProps<"button"> & {
  variant?: "primary" | "secondary" | "ghost" | "accent" | "danger";
};

/** Neutral-by-default action. The primary variant is graphite (not the accent) so the
 *  accent stays reserved for focus/selection — the "serious enterprise" signal. The accent
 *  variant is the brand-amber hero CTA, used sparingly (e.g. Generate course). The danger
 *  variant is reserved for confirming an irreversible action (e.g. delete). The ghost variant is
 *  quiet until reached for: present, but not competing with the content it sits beside. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", className, type = "button", ...props },
  ref,
) {
  const classes = `${styles.button} ${styles[variant]} ${className ?? ""}`.trim();
  return <button ref={ref} type={type} className={classes} {...props} />;
});

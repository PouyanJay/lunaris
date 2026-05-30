import { forwardRef, type ComponentProps } from "react";

import styles from "./Button.module.css";

type ButtonProps = ComponentProps<"button"> & {
  variant?: "primary" | "secondary";
};

/** Neutral-by-default action. The primary variant is graphite (not the accent) so the
 *  accent stays reserved for focus/selection — the "serious enterprise" signal. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", className, type = "button", ...props },
  ref,
) {
  const classes = `${styles.button} ${styles[variant]} ${className ?? ""}`.trim();
  return <button ref={ref} type={type} className={classes} {...props} />;
});

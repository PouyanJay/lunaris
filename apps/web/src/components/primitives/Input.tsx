import { forwardRef, useId, type ComponentProps, type ReactNode } from "react";

import styles from "./Input.module.css";

type InputProps = ComponentProps<"input"> & {
  /** Renders an associated <label>. Without it, pass an aria-label/aria-labelledby yourself. */
  label?: ReactNode;
  /** Inline validation message; flips the field to its invalid state and is announced with it. */
  error?: ReactNode;
};

/** A labelled text input. Focus surfaces the amber accent + soft wash (the one place a field
 *  signals attention); an `error` marks the field aria-invalid and links the message via
 *  aria-describedby so screen readers announce it with the value. */
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, id, className, ...props },
  ref,
) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const errorId = `${inputId}-error`;
  return (
    <div className={styles.field}>
      {label != null && (
        <label className={styles.label} htmlFor={inputId}>
          {label}
        </label>
      )}
      <input
        ref={ref}
        id={inputId}
        className={`${styles.input} ${className ?? ""}`.trim()}
        aria-invalid={error != null ? true : undefined}
        aria-describedby={error != null ? errorId : undefined}
        {...props}
      />
      {error != null && (
        <span id={errorId} className={styles.error}>
          {error}
        </span>
      )}
    </div>
  );
});

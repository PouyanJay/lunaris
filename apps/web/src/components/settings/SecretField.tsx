import { useId, useState } from "react";

import { saveSecret, type SecretStatus } from "../../lib/settings";
import { Button } from "../primitives/Button";
import { StatusDot } from "../primitives/StatusDot";
import styles from "./Settings.module.css";

interface SecretFieldProps {
  apiBaseUrl: string;
  name: string;
  label: string;
  hint: string;
  placeholder: string;
  status: SecretStatus | undefined;
  onSaved: (status: SecretStatus) => void;
}

type Feedback = { kind: "ok" | "error"; text: string } | null;

/** One write-only secret: shows whether it's set (+last4), takes a new value (masked), and
 *  saves it via the API. The current value is never displayed — only its status. */
export function SecretField({
  apiBaseUrl,
  name,
  label,
  hint,
  placeholder,
  status,
  onSaved,
}: SecretFieldProps) {
  const inputId = useId();
  const hintId = useId();
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback>(null);

  const isSet = status?.isSet ?? false;

  async function save() {
    const trimmed = value.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setFeedback(null);
    try {
      const next = await saveSecret(apiBaseUrl, name, trimmed);
      onSaved(next);
      setValue("");
      setFeedback({ kind: "ok", text: "Saved" });
    } catch (error) {
      setFeedback({ kind: "error", text: error instanceof Error ? error.message : "Save failed." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.field}>
      <div className={styles.fieldHead}>
        <label className={styles.label} htmlFor={inputId}>
          {label}
        </label>
        <StatusDot
          label={isSet ? `set ····${status?.last4 ?? ""}` : "not set"}
          tone={isSet ? "success" : "neutral"}
        />
      </div>
      <p id={hintId} className={styles.hint}>
        {hint}
      </p>
      <div className={styles.row}>
        <input
          id={inputId}
          className={styles.input}
          type="password"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder={isSet ? "Enter a new value to replace…" : placeholder}
          aria-describedby={hintId}
          autoComplete="off"
          spellCheck={false}
        />
        <Button type="button" onClick={save} disabled={busy} aria-label={`Save ${label}`}>
          {busy ? "Saving…" : "Save"}
        </Button>
      </div>
      {feedback && (
        <p
          className={feedback.kind === "error" ? styles.error : styles.ok}
          role={feedback.kind === "error" ? "alert" : "status"}
        >
          {feedback.text}
        </p>
      )}
    </div>
  );
}

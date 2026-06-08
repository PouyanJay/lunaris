import { useId, useState } from "react";

import {
  type CredentialStatus,
  deleteCredential,
  saveCredential,
  testCredential,
} from "../../lib/credentials";
import { Button } from "../primitives/Button";
import { StatusDot } from "../primitives/StatusDot";
import styles from "./Settings.module.css";

interface CredentialFieldProps {
  apiBaseUrl: string;
  provider: string;
  label: string;
  hint: string;
  placeholder: string;
  status: CredentialStatus | undefined;
  onChanged: (status: CredentialStatus) => void;
}

type Feedback = { kind: "ok" | "error"; text: string } | null;

/** One per-user BYOK provider key: shows whether it's set (+last4), takes a new value (masked),
 *  and saves / probes / removes it via the authed credentials API. The value is never displayed —
 *  only its status. Remove is a two-step inline confirm (no modal) so a key isn't lost by a stray
 *  click. */
export function CredentialField({
  apiBaseUrl,
  provider,
  label,
  hint,
  placeholder,
  status,
  onChanged,
}: CredentialFieldProps) {
  const inputId = useId();
  const hintId = useId();
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState<null | "saving" | "testing" | "removing">(null);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [confirmingRemove, setConfirmingRemove] = useState(false);

  const isSet = status?.isSet ?? false;
  const trimmed = value.trim();

  async function save() {
    if (!trimmed || busy !== null) return;
    setBusy("saving");
    setFeedback(null);
    try {
      const next = await saveCredential(apiBaseUrl, provider, trimmed);
      onChanged(next);
      setValue("");
      setFeedback({ kind: "ok", text: "Saved" });
    } catch (error) {
      setFeedback({ kind: "error", text: error instanceof Error ? error.message : "Save failed." });
    } finally {
      setBusy(null);
    }
  }

  async function test() {
    if (!trimmed || busy !== null) return;
    setBusy("testing");
    setFeedback(null);
    try {
      const result = await testCredential(apiBaseUrl, provider, trimmed);
      setFeedback(
        result.ok
          ? { kind: "ok", text: "Key looks valid" }
          : { kind: "error", text: result.detail ?? "The provider rejected this key." },
      );
    } catch (error) {
      setFeedback({
        kind: "error",
        text: error instanceof Error ? error.message : "Could not test the key.",
      });
    } finally {
      setBusy(null);
    }
  }

  async function remove() {
    if (busy) return;
    setBusy("removing");
    setFeedback(null);
    try {
      const next = await deleteCredential(apiBaseUrl, provider);
      onChanged(next);
      setConfirmingRemove(false);
      setFeedback({ kind: "ok", text: "Removed" });
    } catch (error) {
      setFeedback({
        kind: "error",
        text: error instanceof Error ? error.message : "Remove failed.",
      });
    } finally {
      setBusy(null);
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
        <Button
          variant="primary"
          onClick={save}
          disabled={!trimmed || busy !== null}
          aria-label={`Save ${label}`}
        >
          {busy === "saving" ? "Saving…" : "Save"}
        </Button>
        <Button
          variant="secondary"
          onClick={test}
          disabled={!trimmed || busy !== null}
          aria-label={`Test ${label}`}
        >
          {busy === "testing" ? "Testing…" : "Test"}
        </Button>
      </div>
      <div className={styles.fieldFoot}>
        {feedback ? (
          <p
            className={feedback.kind === "error" ? styles.feedbackError : styles.feedbackOk}
            role={feedback.kind === "error" ? "alert" : "status"}
          >
            {feedback.text}
          </p>
        ) : (
          <span />
        )}
        {isSet &&
          (confirmingRemove ? (
            <span className={styles.confirm}>
              Remove this key?
              <Button
                variant="danger"
                onClick={remove}
                disabled={busy !== null}
                aria-label={`Confirm remove ${label}`}
              >
                {busy === "removing" ? "Removing…" : "Remove"}
              </Button>
              <Button
                variant="secondary"
                onClick={() => setConfirmingRemove(false)}
                disabled={busy !== null}
              >
                Cancel
              </Button>
            </span>
          ) : (
            <Button
              variant="secondary"
              onClick={() => setConfirmingRemove(true)}
              disabled={busy !== null}
              aria-label={`Remove ${label}`}
            >
              Remove
            </Button>
          ))}
      </div>
    </div>
  );
}

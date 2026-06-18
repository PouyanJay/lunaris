import { useEffect, useId, useState } from "react";

import {
  fetchSignupGate,
  updateSignupGate,
  type SignupGate,
  type SignupGateUpdate,
} from "../../lib/signupGate";
import { Button } from "../primitives/Button";
import { Switch } from "../primitives/Switch";
import styles from "./SignupGate.module.css";

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; gate: SignupGate };

function messageFor(cause: unknown, fallback: string): string {
  return cause instanceof Error && cause.message ? cause.message : fallback;
}

/** Admin-only: manage the single shared invitation code that gates account creation — read/copy it,
 *  rotate it, and toggle whether sign-up requires it. The API enforces admin access; this surface is
 *  only shown when the caller is an admin. */
export function SignupGatePanel({ apiBaseUrl }: { apiBaseUrl: string }) {
  const [state, setState] = useState<State>({ status: "loading" });
  const [codeDraft, setCodeDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [reloadCount, setReloadCount] = useState(0);

  const codeId = useId();
  const enforceLabelId = useId();
  const statusId = useId();

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "loading" });
    fetchSignupGate(apiBaseUrl, controller.signal)
      .then((gate) => {
        if (controller.signal.aborted) return;
        setState({ status: "ready", gate });
        setCodeDraft(gate.inviteCode);
      })
      .catch((cause) => {
        if (controller.signal.aborted) return;
        setState({
          status: "error",
          message: messageFor(cause, "Could not load the invitation settings."),
        });
      });
    return () => controller.abort();
  }, [apiBaseUrl, reloadCount]);

  async function save(update: SignupGateUpdate, success: string) {
    setBusy(true);
    setError(null);
    setNotice(null);
    setCopied(false);
    try {
      const gate = await updateSignupGate(apiBaseUrl, update);
      setState({ status: "ready", gate });
      setCodeDraft(gate.inviteCode);
      setNotice(success);
    } catch (cause) {
      setError(messageFor(cause, "Could not save. Please try again."));
    } finally {
      setBusy(false);
    }
  }

  if (state.status === "loading") {
    return (
      <div className={styles.center}>
        <p className={styles.status} role="status" aria-live="polite">
          Loading…
        </p>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className={styles.center}>
        <div className={styles.panel}>
          <p className={styles.error} role="alert">
            {state.message}
          </p>
          <Button type="button" onClick={() => setReloadCount((n) => n + 1)}>
            Retry
          </Button>
        </div>
      </div>
    );
  }

  const { gate } = state;
  const codeChanged = codeDraft.trim() !== "" && codeDraft !== gate.inviteCode;

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(gate.inviteCode);
      setCopied(true);
    } catch {
      setError("Couldn't copy to the clipboard — select and copy the code manually.");
    }
  }

  return (
    <div className={styles.center}>
      <div className={styles.panel}>
        <p className={styles.intro}>
          New accounts must enter this shared invitation code. Hand it to people you invite; rotate
          it to cut off further sign-ups, or turn the requirement off to open registration.
        </p>

        <section className={styles.region}>
          <label className={styles.label} htmlFor={codeId}>
            Invitation code
          </label>
          <div className={styles.codeRow}>
            <input
              id={codeId}
              className={styles.code}
              type="text"
              value={codeDraft}
              spellCheck={false}
              autoComplete="off"
              disabled={busy}
              onChange={(event) => {
                setCodeDraft(event.target.value);
                setNotice(null);
                setCopied(false);
              }}
            />
            <Button type="button" onClick={() => void copyCode()} disabled={busy}>
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>
          <div className={styles.actions}>
            <Button
              type="button"
              variant="accent"
              disabled={!codeChanged || busy}
              onClick={() => void save({ inviteCode: codeDraft }, "Invitation code updated.")}
            >
              {busy ? "Saving…" : "Save code"}
            </Button>
          </div>
        </section>

        <section className={styles.region}>
          <div className={styles.toggleRow}>
            <div className={styles.toggleText}>
              <span className={styles.label} id={enforceLabelId}>
                Require invitation code
              </span>
              <p className={styles.caption}>
                When off, anyone can create an account without a code.
              </p>
            </div>
            <Switch
              checked={gate.enforced}
              disabled={busy}
              aria-labelledby={enforceLabelId}
              onChange={(next) =>
                void save(
                  { enforced: next },
                  next ? "An invitation code is now required." : "Open registration is now on.",
                )
              }
            />
          </div>
        </section>

        <div id={statusId} className={styles.statusRegion} aria-live="polite">
          {error && (
            <p className={styles.error} role="alert">
              {error}
            </p>
          )}
          {notice && <p className={styles.notice}>{notice}</p>}
        </div>
      </div>
    </div>
  );
}

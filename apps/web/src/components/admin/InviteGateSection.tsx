import { useEffect, useId, useState, type ReactNode } from "react";

import {
  fetchSignupGate,
  updateSignupGate,
  type SignupGate,
  type SignupGateUpdate,
} from "../../lib/signupGate";
import { Button } from "../primitives/Button";
import { Switch } from "../primitives/Switch";
import styles from "./AdminPortal.module.css";

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; gate: SignupGate };

function messageFor(cause: unknown, fallback: string): string {
  return cause instanceof Error && cause.message ? cause.message : fallback;
}

/** Manage the single shared invitation code: read/copy it, rotate it, and toggle whether sign-up
 *  requires it. A section of the Admin Portal — it owns its own loading/error state inline. */
export function InviteGateSection({ apiBaseUrl }: { apiBaseUrl: string }) {
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
        setState({ status: "error", message: messageFor(cause, "Could not load the gate.") });
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

  async function copyCode(code: string) {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
    } catch {
      setError("Couldn't copy to the clipboard — select and copy the code manually.");
    }
  }

  let body: ReactNode;
  if (state.status === "loading") {
    body = (
      <p className={styles.status} role="status" aria-live="polite">
        Loading…
      </p>
    );
  } else if (state.status === "error") {
    body = (
      <div className={styles.statusRegion}>
        <p className={styles.error} role="alert">
          {state.message}
        </p>
        <div>
          <Button type="button" onClick={() => setReloadCount((n) => n + 1)}>
            Retry
          </Button>
        </div>
      </div>
    );
  } else {
    const { gate } = state;
    const codeChanged = codeDraft.trim() !== "" && codeDraft !== gate.inviteCode;
    body = (
      <>
        <div className={styles.field}>
          <label className={styles.label} htmlFor={codeId}>
            Shared code
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
            <Button
              type="button"
              className={styles.iconButton}
              aria-label="Copy code"
              title="Copy code"
              disabled={busy}
              onClick={() => void copyCode(gate.inviteCode)}
            >
              <CopyIcon />
              {copied ? "Copied" : "Copy"}
            </Button>
            <Button
              type="button"
              variant="accent"
              className={styles.iconButton}
              aria-label="Save code"
              title="Save code"
              disabled={!codeChanged || busy}
              onClick={() => void save({ inviteCode: codeDraft }, "Invitation code updated.")}
            >
              <CheckIcon />
              {busy ? "Saving…" : "Save"}
            </Button>
          </div>
        </div>

        <div className={styles.toggleRow}>
          <div className={styles.toggleText}>
            <span className={styles.label} id={enforceLabelId}>
              Require invitation code
            </span>
            <p className={styles.caption}>When off, anyone can create an account without a code.</p>
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

        <div id={statusId} className={styles.statusRegion} aria-live="polite">
          {error && (
            <p className={styles.error} role="alert">
              {error}
            </p>
          )}
          {notice && <p className={styles.notice}>{notice}</p>}
        </div>
      </>
    );
  }

  return (
    <section className={styles.section}>
      <h2 className={styles.heading}>Invitation code</h2>
      <p className={styles.intro}>
        New accounts must enter this shared invitation code. Hand it to people you invite; rotate it
        to cut off further sign-ups, or turn the requirement off to open registration.
      </p>
      {body}
    </section>
  );
}

function CopyIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <rect x="5.5" y="5.5" width="8" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.4" />
      <path
        d="M10.5 5.5V4A1.5 1.5 0 0 0 9 2.5H4A1.5 1.5 0 0 0 2.5 4v5A1.5 1.5 0 0 0 4 10.5h1.5"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M3.5 8.5 6.5 11.5 12.5 4.5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

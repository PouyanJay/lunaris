import { useState, type FormEvent } from "react";

import { useAuth } from "../../hooks/useAuth";
import { resolveDisplayName } from "../../lib/profile";
import { Button } from "../primitives/Button";
import { Input } from "../primitives/Input";
import { Panel } from "../primitives/Panel";
import { CanvasNotice } from "../states/CanvasNotice";
import styles from "./Profile.module.css";

interface ProfileScreenProps {
  /** Return to the app after signing out (or when there's no session to show). */
  onGoHome: () => void;
}

/** The account's own page: change the display name (persisted to Supabase user_metadata) and sign
 *  out. Reached from the sidebar account row. Renders a designed notice — never a blank — when
 *  there's no session (auth disabled or already signed out). */
export function ProfileScreen({ onGoHome }: ProfileScreenProps) {
  const { user, updateDisplayName, signOut } = useAuth();

  if (!user) {
    return (
      <CanvasNotice
        eyebrow="Account"
        title="You're not signed in"
        body="Sign in to manage your profile and display name."
        actionLabel="Go home"
        onAction={onGoHome}
      />
    );
  }

  const name = resolveDisplayName(user);
  const email = user.email ?? "";

  async function onSignOut() {
    await signOut();
    onGoHome();
  }

  return (
    <div className={styles.center}>
      <div className={styles.stack}>
        <IdentityPanel name={name} email={email} />
        <DisplayNameForm currentName={name} onSave={updateDisplayName} />
        <SessionPanel onSignOut={onSignOut} />
      </div>
    </div>
  );
}

function IdentityPanel({ name, email }: { name: string; email: string }) {
  return (
    <Panel heading="Identity">
      <div className={styles.identity}>
        <span className={styles.avatar} aria-hidden="true">
          {(name || email || "?").charAt(0)}
        </span>
        <div className={styles.identityText}>
          <span className={styles.identityName}>{name}</span>
          <span className={`${styles.identityEmail} mono`} title={email}>
            {email}
          </span>
        </div>
      </div>
    </Panel>
  );
}

type SaveState =
  | { status: "idle" }
  | { status: "saving" }
  | { status: "saved" }
  | { status: "error"; message: string };

function DisplayNameForm({
  currentName,
  onSave,
}: {
  currentName: string;
  onSave: (displayName: string) => Promise<void>;
}) {
  const [name, setName] = useState(currentName);
  const [save, setSave] = useState<SaveState>({ status: "idle" });

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setSave({ status: "error", message: "Enter a display name." });
      return;
    }
    setSave({ status: "saving" });
    try {
      await onSave(trimmed);
      setSave({ status: "saved" });
    } catch (error: unknown) {
      setSave({
        status: "error",
        message: error instanceof Error ? error.message : "Couldn't save your name. Try again.",
      });
    }
  }

  return (
    <Panel heading="Display name">
      <form className={styles.form} onSubmit={onSubmit} noValidate>
        <Input
          label="Display name"
          value={name}
          onChange={(event) => {
            setName(event.target.value);
            if (save.status !== "idle") setSave({ status: "idle" });
          }}
          autoComplete="name"
          spellCheck={false}
          maxLength={80}
          error={save.status === "error" ? save.message : undefined}
        />
        <p className={styles.hint}>Shown in the sidebar and your Home greeting.</p>
        <div className={styles.formFoot}>
          <span className={styles.feedback} role="status" aria-live="polite">
            {save.status === "saved" && "Saved"}
          </span>
          <Button
            type="submit"
            variant="primary"
            disabled={save.status === "saving"}
            aria-busy={save.status === "saving"}
          >
            {save.status === "saving" ? "Saving…" : "Save name"}
          </Button>
        </div>
      </form>
    </Panel>
  );
}

function SessionPanel({ onSignOut }: { onSignOut: () => Promise<void> }) {
  const [signingOut, setSigningOut] = useState(false);

  async function handleSignOut() {
    setSigningOut(true);
    try {
      await onSignOut();
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <Panel heading="Session">
      <div className={styles.session}>
        <p className={styles.hint}>End your session on this device.</p>
        <Button
          type="button"
          variant="danger"
          onClick={() => void handleSignOut()}
          disabled={signingOut}
          aria-busy={signingOut}
        >
          {signingOut ? "Signing out…" : "Sign out"}
        </Button>
      </div>
    </Panel>
  );
}

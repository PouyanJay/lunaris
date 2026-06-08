import { useId, useState, type FormEvent } from "react";

import { useAuth } from "../../hooks/useAuth";
import { BrandMark } from "../shell/BrandMark";
import { Button } from "../primitives/Button";
import styles from "./AuthScreen.module.css";

type Mode = "signin" | "signup";

function messageFor(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "Something went wrong. Please try again.";
}

function submitLabel(submitting: boolean, isSignup: boolean): string {
  if (submitting) return isSignup ? "Creating account…" : "Signing in…";
  return isSignup ? "Create account" : "Sign in";
}

/** The login / sign-up gate shown when auth is required and no one is signed in.
 *
 *  Email + password (Supabase Auth). Signing up may require an email confirmation (cloud default),
 *  in which case a notice is shown instead of entering the app. Full keyboard + screen-reader
 *  support: labelled fields, an aria-live error/notice region, and a visible focus ring. */
export function AuthScreen() {
  const { signIn, signUp } = useAuth();
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const emailId = useId();
  const passwordId = useId();
  const statusId = useId();
  const isSignup = mode === "signup";

  async function submitSignUp() {
    const { needsConfirmation } = await signUp(email, password);
    if (needsConfirmation) {
      setNotice(`Check ${email} for a confirmation link to finish creating your account.`);
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      await (isSignup ? submitSignUp() : signIn(email, password));
    } catch (caught) {
      setError(messageFor(caught));
    } finally {
      setSubmitting(false);
    }
  }

  function switchMode() {
    setMode(isSignup ? "signin" : "signup");
    setError(null);
    setNotice(null);
  }

  return (
    <main className={styles.screen}>
      <div className={styles.panel}>
        <div className={styles.brand}>
          <BrandMark size={28} />
          <span className={styles.wordmark}>Lunaris</span>
        </div>
        <h1 className={styles.heading}>{isSignup ? "Create your account" : "Sign in"}</h1>
        <p className={styles.subheading}>
          {isSignup
            ? "You'll bring your own provider keys after signing in."
            : "Welcome back. Sign in to your courses."}
        </p>

        <form className={styles.form} onSubmit={handleSubmit} noValidate>
          <div className={styles.field}>
            <label className={styles.label} htmlFor={emailId}>
              Email
            </label>
            <input
              id={emailId}
              className={styles.input}
              type="email"
              autoComplete="email"
              autoFocus
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              disabled={submitting}
              aria-invalid={error !== null}
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor={passwordId}>
              Password
            </label>
            <input
              id={passwordId}
              className={styles.input}
              type="password"
              autoComplete={isSignup ? "new-password" : "current-password"}
              required
              minLength={6}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              disabled={submitting}
              aria-invalid={error !== null}
            />
          </div>

          <div id={statusId} aria-live="polite">
            {error && (
              <p className={styles.error} role="alert">
                {error}
              </p>
            )}
            {notice && <p className={styles.notice}>{notice}</p>}
          </div>

          <Button
            type="submit"
            variant="accent"
            className={styles.submit}
            disabled={submitting}
            aria-describedby={statusId}
          >
            {submitLabel(submitting, isSignup)}
          </Button>
        </form>

        <p className={styles.toggle}>
          {isSignup ? "Already have an account?" : "New to Lunaris?"}{" "}
          <button type="button" className={styles.toggleButton} onClick={switchMode}>
            {isSignup ? "Sign in" : "Create one"}
          </button>
        </p>
      </div>
    </main>
  );
}

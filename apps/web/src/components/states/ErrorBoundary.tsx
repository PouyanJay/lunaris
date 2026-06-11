import { Component, type ErrorInfo, type ReactNode } from "react";

import { Button } from "../primitives/Button";
import styles from "./DataStates.module.css";

interface ErrorBoundaryProps {
  children: ReactNode;
  /** Called on "Try again" so the owner can clear whatever state caused the crash. */
  onReset?: () => void;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/** The last line of defence against a render crash: instead of React unmounting the whole tree
 *  (a white screen with no recovery), the failure is announced with the same calm error pattern
 *  as the data views — and offers a reset plus a full reload. Class component by necessity:
 *  `componentDidCatch` has no hook equivalent. */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Surfaced to the console (the operational sink in the SPA) — the UI shows no stack trace.
    console.error("Unhandled render error", error, info.componentStack);
  }

  private readonly reset = () => {
    this.props.onReset?.();
    this.setState({ error: null });
  };

  private readonly reload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.error === null) return this.props.children;
    return (
      <div className={styles.center}>
        <div className={styles.message} role="alert">
          <span className="eyebrow">Unexpected error</span>
          <h2 className={styles.title}>Something went wrong</h2>
          <p className={styles.body}>
            The view crashed while rendering. Your courses and builds are safe on the server — try
            again, or reload the app if it keeps happening.
          </p>
          <div className={styles.action}>
            <Button variant="primary" onClick={this.reset}>
              Try again
            </Button>
            <Button variant="secondary" onClick={this.reload}>
              Reload the app
            </Button>
          </div>
        </div>
      </div>
    );
  }
}

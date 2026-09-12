import { useEffect, useState } from "react";
import { authedFetch } from "../../lib/apiClient";
import styles from "./SimFrame.module.css";

const MESSAGES: Record<string, string> = {
  queued:
    "Preparing a simulator for this concept. Continue with the explanation while it is being checked.",
  building:
    "Preparing a simulator for this concept. Continue with the explanation while it is being checked.",
  approved: "A simulator is ready for this concept’s next turn.",
  rejected: "We could not prepare a suitable simulator. Continue with the explanation.",
  indeterminate: "The simulator could not be completed. Continue with the explanation.",
  unavailable: "A simulator is unavailable for this concept. Continue with the explanation.",
};

/** Observe background preparation without blocking the lesson or starting another build. */
export function SimPreparationNotice({
  apiBaseUrl,
  sessionId,
  turnSeq,
}: {
  apiBaseUrl: string;
  sessionId: string;
  turnSeq: number;
}) {
  const key = `${sessionId}:${turnSeq}`;
  const [result, setResult] = useState<{ key: string; status: string } | null>(null);
  useEffect(() => {
    let current = true;
    let observations = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();
    const read = async () => {
      const deadline = setTimeout(() => controller.abort(), 10000);
      try {
        const response = await authedFetch(
          `${apiBaseUrl}/api/live/sessions/${encodeURIComponent(sessionId)}/sim-status`,
          {
            signal: controller.signal,
          },
        );
        if (!response.ok) throw new Error("Unavailable");
        const { status } = (await response.json()) as { status: string };
        if (!current) return;
        setResult({ key, status });
        observations += 1;
        if (
          status === "queued" ||
          status === "building" ||
          (status === "unavailable" && observations < 20)
        )
          timer = setTimeout(() => void read(), 3000);
      } catch {
        if (current) setResult({ key, status: "unavailable" });
      } finally {
        clearTimeout(deadline);
      }
    };
    void read();
    return () => {
      current = false;
      controller.abort();
      clearTimeout(timer);
    };
  }, [apiBaseUrl, sessionId, key]);
  const message = result?.key === key ? MESSAGES[result.status] : undefined;
  return message ? (
    <p className={styles.status} role="status">
      {message}
    </p>
  ) : null;
}

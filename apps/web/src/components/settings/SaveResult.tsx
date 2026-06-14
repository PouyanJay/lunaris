import type { SaveFeedback } from "../../hooks/useConfigSaver";
import styles from "./Config.module.css";

/** The inline save confirmation/error beneath a config control — an announced live region (alert on
 *  error, status on success). Shared by the config panels so a save confirms identically. */
export function SaveResult({ feedback }: { feedback: SaveFeedback | undefined }) {
  if (!feedback) return null;
  return (
    <p
      className={feedback.tone === "error" ? styles.error : styles.ok}
      role={feedback.tone === "error" ? "alert" : "status"}
    >
      {feedback.message}
    </p>
  );
}

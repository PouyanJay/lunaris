import { useEffect, useId, useState } from "react";

import { answersToClarification, recommendedAnswers } from "../../lib/clarification";
import { fetchBrief } from "../../lib/fetchBrief";
import { CourseLoadError } from "../../lib/loadCourse";
import type { BriefResponse, Clarification } from "../../types/clarifier";
import { Button } from "../primitives/Button";
import { ClarifierQuestionField } from "./ClarifierQuestionField";
import styles from "./PersonalizePanel.module.css";

interface PersonalizePanelProps {
  apiBaseUrl: string;
  topic: string;
  onConfirm: (topic: string, clarification: Clarification) => void;
  onCancel: () => void;
}

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: BriefResponse; answers: Record<string, string> };

/**
 * The opt-in "infer-and-confirm" step (P7.5): interpret the topic into a brief + clarifier
 * (POST /api/briefs), let the learner confirm or adjust the inference (each question pre-picks it),
 * then build with the confirmed answers. An in-canvas panel (not a modal) matching the settings
 * panel; the default Generate path skips this entirely. All states: loading / error+retry / ready.
 */
export function PersonalizePanel({
  apiBaseUrl,
  topic,
  onConfirm,
  onCancel,
}: PersonalizePanelProps) {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [reloadSeq, setReloadSeq] = useState(0);
  const titleId = useId();
  const readId = useId();

  useEffect(() => {
    setState({ status: "loading" });
    const controller = new AbortController();
    fetchBrief(apiBaseUrl, topic, controller.signal)
      // The abort guard covers React StrictMode's double-invoke (the first controller aborts before
      // the second fires) as well as unmount mid-flight.
      .then((data) => {
        if (controller.signal.aborted) return;
        setState({ status: "ready", data, answers: recommendedAnswers(data.clarifier) });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message =
          error instanceof CourseLoadError
            ? error.message
            : "We couldn't read your goal. Try again.";
        setState({ status: "error", message });
      });
    return () => controller.abort();
  }, [apiBaseUrl, topic, reloadSeq]);

  const setAnswer = (id: string, value: string) =>
    setState((prev) =>
      prev.status === "ready" ? { ...prev, answers: { ...prev.answers, [id]: value } } : prev,
    );

  return (
    <div className={styles.center}>
      <section className={styles.panel} aria-labelledby={titleId}>
        <header className={styles.header}>
          <div>
            <span className="eyebrow">Personalize</span>
            <h2 id={titleId} className={styles.title}>
              Tune your course
            </h2>
          </div>
          <Button variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
        </header>

        {state.status === "loading" && (
          <p className={styles.status} role="status">
            Reading your goal&hellip;
          </p>
        )}

        {state.status === "error" && (
          <div className={styles.body}>
            <p className={styles.error} role="alert">
              {state.message}
            </p>
            <div className={styles.actions}>
              <Button variant="primary" onClick={() => setReloadSeq((seq) => seq + 1)}>
                Try again
              </Button>
              <Button variant="secondary" onClick={onCancel}>
                Back
              </Button>
            </div>
          </div>
        )}

        {state.status === "ready" && (
          <form
            className={styles.body}
            aria-describedby={readId}
            onSubmit={(event) => {
              event.preventDefault();
              onConfirm(topic, answersToClarification(state.answers));
            }}
          >
            <p id={readId} className={styles.read}>
              We read this as <strong>{state.data.brief.goal || state.data.brief.subject}</strong>.
              Confirm or adjust, then build &mdash; or skip and we&rsquo;ll use the inference.
            </p>
            <div className={styles.questions}>
              {state.data.clarifier.questions.map((question) => (
                <ClarifierQuestionField
                  key={question.id}
                  question={question}
                  value={state.answers[question.id] ?? ""}
                  onChange={(value) => setAnswer(question.id, value)}
                />
              ))}
            </div>
            <div className={styles.actions}>
              <Button type="submit" variant="accent">
                Build course
              </Button>
              <Button type="button" variant="secondary" onClick={onCancel}>
                Back
              </Button>
            </div>
          </form>
        )}
      </section>
    </div>
  );
}

import { useId, useState } from "react";
import { Button } from "../primitives/Button";
import { Select } from "../primitives/Select";
import styles from "./CorpusSource.module.css";

interface CorpusSourceProps {
  courses: { courseId: string; title: string }[];
  courseId: string;
  onSelect: (courseId: string) => void;
  onPrepare: (courseId: string) => void;
  busy?: boolean;
  error?: string | null;
  source?: { title: string; status: "pending" } | null;
}

/** Explicit course preparation with an honest, still-unverified source receipt. */
export function CorpusSource({
  courses,
  courseId,
  onSelect,
  onPrepare,
  busy = false,
  error,
  source,
}: CorpusSourceProps) {
  const id = useId();
  const [selectionError, setSelectionError] = useState(false);
  if (courses.length === 0) {
    return (
      <section className={styles.root} aria-label="Course source">
        <p>No source courses are available. Create a course in Studio to begin.</p>
        <a href="/">Open Studio</a>
      </section>
    );
  }
  return (
    <section className={styles.root} aria-label="Course source" aria-busy={busy}>
      <form
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          if (busy) return;
          if (!courses.some((course) => course.courseId === courseId)) {
            setSelectionError(true);
            document.getElementById(id)?.focus();
            return;
          }
          setSelectionError(false);
          onPrepare(courseId);
        }}
      >
        <label id={`${id}-label`} htmlFor={id}>
          Source course
        </label>
        <Select
          id={id}
          aria-labelledby={`${id}-label`}
          aria-invalid={selectionError || undefined}
          aria-describedby={selectionError ? `${id}-error` : undefined}
          value={courseId}
          options={[
            { value: "", label: "Choose a course" },
            ...courses.map((course) => ({ value: course.courseId, label: course.title })),
          ]}
          onChange={(value) => {
            setSelectionError(false);
            onSelect(value);
          }}
          disabled={busy}
        />
        <Button type="submit" disabled={busy}>
          {busy ? "Preparing course…" : "Prepare course"}
        </Button>
      </form>
      {busy && (
        <p role="status" className={styles.status}>
          Preparing course…
        </p>
      )}
      {source && !busy && (
        <div className={styles.receipt}>
          <p>{source.title}</p>
          <p role="status" className={styles.status}>
            Awaiting verification
          </p>
        </div>
      )}
      {selectionError && (
        <p id={`${id}-error`} role="alert">
          Choose a source course before preparing.
        </p>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}

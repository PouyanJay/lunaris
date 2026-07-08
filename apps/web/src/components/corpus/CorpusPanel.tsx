import { useId, useRef, useState } from "react";

import {
  addTextSource,
  addUrlSource,
  CorpusError,
  deleteCorpusSource,
  regroundCourse,
  uploadFileSource,
} from "../../lib/corpus";
import { ACQUISITION_MODE_LABEL, type IngestResult } from "../../types/course";
import { type CorpusState, useCorpus } from "../../hooks/useCorpus";
import { Button } from "../primitives/Button";
import { SegmentedControl, type Segment } from "../primitives/SegmentedControl";
import { SourceTrust } from "../primitives/SourceTrust";
import states from "../states/DataStates.module.css";
import styles from "./CorpusPanel.module.css";

type AddMode = "text" | "url" | "file";

const MODES: Segment<AddMode>[] = [
  { value: "text", label: "Paste" },
  { value: "url", label: "URL" },
  { value: "file", label: "File" },
];

interface CorpusPanelProps {
  apiBaseUrl: string;
  courseId: string;
  /** Reload the opened course after a re-ground, so updated (green) citations show in the reader. */
  onReground?: () => void;
}

/** The per-course Corpus tab (P6.1): add your own trusted sources (paste / URL / file) to ground the
 *  course, and curate them. The verifier checks each claim against this corpus. */
export function CorpusPanel({ apiBaseUrl, courseId, onReground }: CorpusPanelProps) {
  const { state, reload } = useCorpus(apiBaseUrl, courseId);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [regrounding, setRegrounding] = useState(false);
  const [regroundError, setRegroundError] = useState<string | null>(null);
  const [regrounded, setRegrounded] = useState(false);

  async function onRegroundClick() {
    setRegrounding(true);
    setRegroundError(null);
    setRegrounded(false);
    try {
      await regroundCourse(apiBaseUrl, courseId);
      setRegrounded(true);
      onReground?.();
    } catch (error) {
      setRegroundError(
        error instanceof CorpusError ? error.message : "Couldn't re-ground the course.",
      );
    } finally {
      setRegrounding(false);
    }
  }

  async function onDelete(sourceId: string) {
    setDeletingId(sourceId);
    setDeleteError(null);
    try {
      await deleteCorpusSource(apiBaseUrl, courseId, sourceId);
      reload();
    } catch (error) {
      setDeleteError(error instanceof CorpusError ? error.message : "Couldn't delete that source.");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className={styles.panel}>
      <header className={styles.head}>
        <span className="eyebrow">Grounding corpus</span>
        <h2 className={styles.title}>Sources for this course</h2>
        <p className={styles.hint}>
          Add your own trusted documents — paste notes, link a page, or upload a PDF/DOCX. Every
          claim in the course is verified against this corpus.
        </p>
        <div className={styles.regroundRow}>
          <Button variant="primary" onClick={onRegroundClick} disabled={regrounding}>
            {regrounding ? "Re-grounding…" : "Re-ground course"}
          </Button>
          {regrounded && (
            <span className={styles.feedbackOk} role="status">
              Re-grounded — open Lessons to see the updated citations.
            </span>
          )}
          {regroundError && (
            <span className={styles.feedbackError} role="alert">
              {regroundError}
            </span>
          )}
        </div>
      </header>

      <AddSource apiBaseUrl={apiBaseUrl} courseId={courseId} onAdded={reload} />

      <SourceList
        state={state}
        reload={reload}
        onDelete={onDelete}
        deletingId={deletingId}
        deleteError={deleteError}
      />
    </div>
  );
}

function AddSource({
  apiBaseUrl,
  courseId,
  onAdded,
}: {
  apiBaseUrl: string;
  courseId: string;
  onAdded: () => void;
}) {
  const titleId = useId();
  const bodyId = useId();
  const urlId = useId();
  const fileId = useId();
  const [mode, setMode] = useState<AddMode>("text");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<IngestResult | null>(null);

  function reset() {
    setTitle("");
    setText("");
    setUrl("");
    setFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function callAddApi(): Promise<IngestResult> {
    if (mode === "text") return addTextSource(apiBaseUrl, courseId, title.trim(), text);
    if (mode === "url") return addUrlSource(apiBaseUrl, courseId, url.trim());
    return uploadFileSource(apiBaseUrl, courseId, file as File);
  }

  async function submit() {
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const outcome = await callAddApi();
      setResult(outcome);
      if (outcome.accepted) {
        reset();
        onAdded();
      }
    } catch (caught) {
      setError(caught instanceof CorpusError ? caught.message : "Couldn't add that source.");
    } finally {
      setSubmitting(false);
    }
  }

  const canSubmit =
    !submitting &&
    ((mode === "text" && text.trim().length > 0) ||
      (mode === "url" && url.trim().length > 0) ||
      (mode === "file" && file !== null));

  return (
    <section className={styles.add} aria-label="Add a source">
      <SegmentedControl
        segments={MODES}
        value={mode}
        onChange={(next) => {
          setMode(next);
          setError(null);
          setResult(null);
        }}
        label="Source type"
      />

      <form
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          if (canSubmit) void submit();
        }}
      >
        {mode === "text" && (
          <>
            <label className="sr-only" htmlFor={titleId}>
              Title (optional)
            </label>
            <input
              id={titleId}
              className={styles.input}
              type="text"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Title (optional)"
              maxLength={300}
              autoComplete="off"
            />
            <label className="sr-only" htmlFor={bodyId}>
              Text
            </label>
            <textarea
              id={bodyId}
              className={styles.textarea}
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="Paste notes or reference text…"
              rows={5}
            />
          </>
        )}
        {mode === "url" && (
          <>
            <label className="sr-only" htmlFor={urlId}>
              URL
            </label>
            <input
              id={urlId}
              className={styles.input}
              type="url"
              inputMode="url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://example.edu/reference"
              autoComplete="off"
              spellCheck={false}
            />
          </>
        )}
        {mode === "file" && (
          <>
            <label className="sr-only" htmlFor={fileId}>
              Document
            </label>
            <input
              id={fileId}
              ref={fileInputRef}
              className={styles.file}
              type="file"
              accept=".pdf,.docx,.md,.markdown,.txt,.text"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </>
        )}

        <div className={styles.actions}>
          <Button type="submit" variant="primary" disabled={!canSubmit}>
            {submitting ? "Adding…" : "Add source"}
          </Button>
        </div>
      </form>

      {error && (
        <p className={styles.feedbackError} role="alert">
          {error}
        </p>
      )}
      {result && !result.accepted && (
        <p className={styles.feedbackError} role="alert">
          Not added: {result.reason ?? "the source was declined"}.
        </p>
      )}
      {result && result.accepted && (
        <p className={styles.feedbackOk} role="status">
          Added — {result.chunks} chunk{result.chunks === 1 ? "" : "s"} ingested.
        </p>
      )}
    </section>
  );
}

function SourceList({
  state,
  reload,
  onDelete,
  deletingId,
  deleteError,
}: {
  state: CorpusState;
  reload: () => void;
  onDelete: (sourceId: string) => void;
  deletingId: string | null;
  deleteError: string | null;
}) {
  if (state.status === "loading") {
    return (
      <ul className={styles.skeleton} role="status" aria-label="Loading sources…">
        {[0, 1, 2].map((row) => (
          <li key={row} className={styles.skeletonRow} />
        ))}
      </ul>
    );
  }

  if (state.status === "error") {
    return (
      <div className={states.center}>
        <div className={states.message} role="alert">
          <span className="eyebrow">Corpus</span>
          <h3 className={states.title}>Couldn't load the corpus</h3>
          <p className={states.body}>{state.message}</p>
          <div className={states.action}>
            <Button variant="primary" onClick={reload}>
              Try again
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (state.status === "empty") {
    return (
      <div className={states.center}>
        <div className={states.message}>
          <span className="eyebrow">Corpus</span>
          <h3 className={states.title}>No sources yet</h3>
          <p className={states.body}>
            Add your notes, a reference URL, or a document above. The course's claims are grounded
            against the sources you add here.
          </p>
        </div>
      </div>
    );
  }

  return (
    <>
      {deleteError && (
        <p className={styles.feedbackError} role="alert">
          {deleteError}
        </p>
      )}
      <ul className={styles.list} aria-label="Corpus sources">
        {state.sources.map((source) => (
          <li key={source.sourceId} className={styles.item}>
            <div className={styles.itemMain}>
              {source.url ? (
                <a
                  className={styles.itemTitle}
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {source.title ?? source.url}
                </a>
              ) : (
                <span className={styles.itemTitle}>{source.title ?? "Untitled source"}</span>
              )}
              <div className={styles.itemMeta}>
                {source.trustTier && (
                  <SourceTrust tier={source.trustTier} credibility={source.credibility} />
                )}
                {source.acquisitionMode && (
                  <span
                    className={`mono ${styles.provenance}`}
                    title="How this source entered the corpus"
                    aria-label={`Acquisition mode: ${ACQUISITION_MODE_LABEL[source.acquisitionMode]}`}
                  >
                    {ACQUISITION_MODE_LABEL[source.acquisitionMode]}
                  </span>
                )}
                <span className={`mono ${styles.chunks}`}>
                  {source.chunkCount} chunk{source.chunkCount === 1 ? "" : "s"}
                </span>
              </div>
            </div>
            <Button
              variant="danger"
              onClick={() => onDelete(source.sourceId)}
              disabled={deletingId === source.sourceId}
              aria-label={`Remove ${source.title ?? "source"}`}
            >
              {deletingId === source.sourceId ? "Removing…" : "Remove"}
            </Button>
          </li>
        ))}
      </ul>
    </>
  );
}

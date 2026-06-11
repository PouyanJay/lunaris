import { authedFetch } from "./apiClient";
import type { CorpusSource, IngestResult } from "../types/course";

/** A failure reaching or using the corpus API (network or non-OK response). */
export class CorpusError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "CorpusError";
  }
}

async function postSource(
  apiBaseUrl: string,
  body: Record<string, unknown>,
): Promise<IngestResult> {
  let response: Response;
  try {
    response = await authedFetch(`${apiBaseUrl}/api/corpus/sources`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (cause) {
    throw new CorpusError("Could not reach the corpus service.", { cause });
  }
  if (!response.ok) {
    throw new CorpusError(`Couldn't add the source (HTTP ${response.status}).`);
  }
  return response.json() as Promise<IngestResult>;
}

/** List a course's manually-ingested sources (GET /api/corpus?courseId=…). */
export async function fetchCorpusSources(
  apiBaseUrl: string,
  courseId: string,
  signal?: AbortSignal,
): Promise<CorpusSource[]> {
  const query = new URLSearchParams({ courseId });
  let response: Response;
  try {
    response = await authedFetch(
      `${apiBaseUrl}/api/corpus?${query}`,
      signal ? { signal } : undefined,
    );
  } catch (cause) {
    throw new CorpusError("Could not reach the corpus service.", { cause });
  }
  if (!response.ok) {
    throw new CorpusError(`Couldn't load the corpus (HTTP ${response.status}).`);
  }
  return response.json() as Promise<CorpusSource[]>;
}

/** Add a pasted-text source. */
export async function addTextSource(
  apiBaseUrl: string,
  courseId: string,
  title: string,
  text: string,
): Promise<IngestResult> {
  return postSource(apiBaseUrl, { courseId, kind: "text", title, text });
}

/** Add a URL source (the server fetches + extracts it). */
export async function addUrlSource(
  apiBaseUrl: string,
  courseId: string,
  url: string,
): Promise<IngestResult> {
  return postSource(apiBaseUrl, { courseId, kind: "url", url });
}

/** Upload a document (PDF/DOCX/MD/TXT) as a source (POST /api/corpus/sources/file, multipart). */
export async function uploadFileSource(
  apiBaseUrl: string,
  courseId: string,
  file: File,
): Promise<IngestResult> {
  const form = new FormData();
  form.append("courseId", courseId);
  form.append("file", file);
  let response: Response;
  try {
    response = await authedFetch(`${apiBaseUrl}/api/corpus/sources/file`, {
      method: "POST",
      body: form,
    });
  } catch (cause) {
    throw new CorpusError("Could not reach the corpus service.", { cause });
  }
  if (!response.ok) {
    throw new CorpusError(`Couldn't upload the file (HTTP ${response.status}).`);
  }
  return response.json() as Promise<IngestResult>;
}

/** Re-run the course's build so it re-grounds against the current corpus (POST .../rebuild).
 *  Heavyweight (re-runs the pipeline); the caller shows a pending state + reloads the course after. */
export async function regroundCourse(apiBaseUrl: string, courseId: string): Promise<void> {
  let response: Response;
  try {
    response = await authedFetch(
      `${apiBaseUrl}/api/courses/${encodeURIComponent(courseId)}/rebuild`,
      {
        method: "POST",
      },
    );
  } catch (cause) {
    throw new CorpusError("Could not reach the course service.", { cause });
  }
  if (!response.ok) {
    throw new CorpusError(`Re-grounding failed (HTTP ${response.status}).`);
  }
}

/** Remove a source (all its chunks) from the corpus (DELETE /api/corpus/{sourceId}?courseId=…).
 *  The course id rides along so the server verifies ownership + membership before deleting. */
export async function deleteCorpusSource(
  apiBaseUrl: string,
  courseId: string,
  sourceId: string,
): Promise<void> {
  const query = new URLSearchParams({ courseId });
  let response: Response;
  try {
    response = await authedFetch(
      `${apiBaseUrl}/api/corpus/${encodeURIComponent(sourceId)}?${query}`,
      {
        method: "DELETE",
      },
    );
  } catch (cause) {
    throw new CorpusError("Could not reach the corpus service.", { cause });
  }
  if (!response.ok) {
    throw new CorpusError(`Couldn't delete the source (HTTP ${response.status}).`);
  }
}

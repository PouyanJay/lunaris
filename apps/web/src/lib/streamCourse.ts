import { authedFetch } from "./apiClient";
import type { Clarification } from "../types/clarifier";
import type { AgentEvent, Course, DiscoveryDepth, ProgressEvent } from "../types/course";
import type { ComputeSource } from "./computeSource";
import { CourseLoadError, parseCourse } from "./loadCourse";

interface StreamCourseOptions {
  /** Called for each coarse pipeline-stage event as it arrives. */
  onProgress?: (event: ProgressEvent) => void;
  /** Called for each fine-grained agent-transcript beat (reasoning / tool call / todo). */
  onAgent?: (event: AgentEvent) => void;
  /** Called once with the run id from the X-Run-Id header, before any frame — the device
   *  bridge worker needs it immediately (the first completion can be parked before the
   *  first progress event lands). */
  onRunId?: (runId: string) => void;
  /** Called once with the course id from the X-Course-Id header, before any frame — lets a caller
   *  whose stream drops re-attach to the durable build by polling this id for the finished course. */
  onCourseId?: (courseId: string) => void;
  /** The learner's opt-in confirm answers (P7.5); absent → today's inferred-only build. */
  clarification?: Clarification;
  /** How hard auto-discovery searches (P6.3); absent → the moderate `standard` default. */
  discoveryDepth?: DiscoveryDepth;
  /** Where a keyless build's LLM runs (the compute dropdown): `device` serves completions
   *  from this browser over the run's bridge; absent → the API's server default. */
  compute?: ComputeSource;
  /** Abort the in-flight build (e.g. the user navigates away or starts a new topic). */
  signal?: AbortSignal;
}

/**
 * Generate a course for `topic` and stream its build over Server-Sent Events, invoking
 * `onProgress` per stage and resolving with the finished course (the terminal `course`
 * frame). Consumed via `fetch` + a `ReadableStream` reader rather than `EventSource` so
 * the request is abortable and testable. An optional `clarification` (the confirmed answers
 * from the Personalize panel) rides as a JSON query param. Network, HTTP, and "stream ended
 * without a course" failures all surface as `CourseLoadError` — one error channel for the caller.
 */
export async function streamCourse(
  apiBaseUrl: string,
  topic: string,
  {
    onProgress,
    onAgent,
    onRunId,
    onCourseId,
    clarification,
    discoveryDepth,
    compute,
    signal,
  }: StreamCourseOptions,
): Promise<Course> {
  const params = new URLSearchParams({ topic });
  if (clarification) params.set("clarification", JSON.stringify(clarification));
  if (discoveryDepth) params.set("discovery_depth", discoveryDepth);
  if (compute) params.set("compute", compute);
  const url = `${apiBaseUrl}/api/courses/stream?${params}`;
  let response: Response;
  try {
    response = await authedFetch(url, signal ? { signal } : {});
  } catch (cause) {
    throw new CourseLoadError("Could not reach the course service.", { cause });
  }
  if (!response.ok) {
    throw new CourseLoadError(`Course generation failed (HTTP ${response.status}).`);
  }
  if (!response.body) {
    throw new CourseLoadError("The course stream returned no body.");
  }
  const runId = response.headers.get("X-Run-Id");
  if (runId) onRunId?.(runId);
  const courseId = response.headers.get("X-Course-Id");
  if (courseId) onCourseId?.(courseId);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let course: Course | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE frames are separated by a blank line; process every complete frame in the buffer.
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const frame = parseFrame(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      if (frame?.event === "progress") {
        onProgress?.(frame.data as ProgressEvent);
      } else if (frame?.event === "agent") {
        onAgent?.(frame.data as AgentEvent);
      } else if (frame?.event === "course") {
        course = parseCourse(frame.data);
      }
      boundary = buffer.indexOf("\n\n");
    }
  }

  if (!course) {
    // The body closed before the terminal `course` frame. On a long build this is most often a
    // transient disconnect (proxy/idle timeout), not a failure — flag it so the caller can
    // re-attach to the durable run rather than reporting a broken build.
    throw new CourseLoadError("The build stream ended before the course was ready.", {
      streamIncomplete: true,
    });
  }
  return course;
}

/** Parse one SSE frame into its event name + decoded JSON data, or null if it has no data. */
function parseFrame(frame: string): { event: string; data: unknown } | null {
  let event = "message";
  let data = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice("event:".length).trim();
    else if (line.startsWith("data:")) data += line.slice("data:".length).trim();
  }
  if (!data) return null;
  try {
    return { event, data: JSON.parse(data) };
  } catch {
    return null;
  }
}

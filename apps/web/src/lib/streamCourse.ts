import type { AgentEvent, Course, ProgressEvent } from "../types/course";
import { CourseLoadError, parseCourse } from "./loadCourse";

interface StreamCourseOptions {
  /** Called for each coarse pipeline-stage event as it arrives. */
  onProgress?: (event: ProgressEvent) => void;
  /** Called for each fine-grained agent-transcript beat (reasoning / tool call / todo). */
  onAgent?: (event: AgentEvent) => void;
  /** Abort the in-flight build (e.g. the user navigates away or starts a new topic). */
  signal?: AbortSignal;
}

/**
 * Generate a course for `topic` and stream its build over Server-Sent Events, invoking
 * `onProgress` per stage and resolving with the finished course (the terminal `course`
 * frame). Consumed via `fetch` + a `ReadableStream` reader rather than `EventSource` so
 * the request is abortable and testable. Network, HTTP, and "stream ended without a
 * course" failures all surface as `CourseLoadError` — one error channel for the caller.
 */
export async function streamCourse(
  apiBaseUrl: string,
  topic: string,
  { onProgress, onAgent, signal }: StreamCourseOptions,
): Promise<Course> {
  const url = `${apiBaseUrl}/api/courses/stream?${new URLSearchParams({ topic })}`;
  let response: Response;
  try {
    response = await fetch(url, signal ? { signal } : {});
  } catch (cause) {
    throw new CourseLoadError("Could not reach the course service.", { cause });
  }
  if (!response.ok) {
    throw new CourseLoadError(`Course generation failed (HTTP ${response.status}).`);
  }
  if (!response.body) {
    throw new CourseLoadError("The course stream returned no body.");
  }

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
    throw new CourseLoadError("The build stream ended before the course was ready.");
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

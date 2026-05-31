import type { Course } from "../types/course";

/** Where the explorer reads the course-object from. A static artifact today; swap for an
 *  API endpoint (e.g. `/api/courses/:id`) without touching callers. */
export const DEFAULT_COURSE_URL = "/sample-course.json";

export class CourseLoadError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "CourseLoadError";
  }
}

/**
 * Parse + structurally validate a raw course-object payload. Throws CourseLoadError with a
 * human-readable cause on anything malformed, so the UI can show a real error state rather
 * than rendering an empty canvas from bad data.
 */
export function parseCourse(raw: unknown): Course {
  if (!isRecord(raw)) {
    throw new CourseLoadError("Course payload is not an object.");
  }
  const graph = raw.graph;
  if (!isRecord(graph) || !Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) {
    throw new CourseLoadError("Course is missing a prerequisite graph (nodes / edges).");
  }
  for (const node of graph.nodes) {
    if (!isRecord(node) || typeof node.id !== "string" || typeof node.label !== "string") {
      throw new CourseLoadError("A knowledge component is missing an id or label.");
    }
  }
  for (const edge of graph.edges) {
    if (!isRecord(edge) || typeof edge.from !== "string" || typeof edge.to !== "string") {
      throw new CourseLoadError("A prerequisite edge is missing its from / to endpoints.");
    }
  }
  // Shape verified above; the schema is the producer's contract.
  return raw as unknown as Course;
}

/** Fetch + parse a static course-object from `url`. Network and HTTP failures surface as
 *  CourseLoadError so the caller has one error channel to render. */
export async function loadCourse(
  url: string = DEFAULT_COURSE_URL,
  signal?: AbortSignal,
): Promise<Course> {
  let response: Response;
  try {
    response = await fetch(url, signal ? { signal } : undefined);
  } catch (cause) {
    throw new CourseLoadError("Could not reach the course service.", { cause });
  }
  if (!response.ok) {
    throw new CourseLoadError(`Course request failed (HTTP ${response.status}).`);
  }
  return parseResponse(response);
}

/** Generate a course for `topic` via the live API (POST /api/courses) and parse the result. */
export async function generateCourse(
  apiBaseUrl: string,
  topic: string,
  signal?: AbortSignal,
): Promise<Course> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/api/courses`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ topic }),
      ...(signal ? { signal } : {}),
    });
  } catch (cause) {
    throw new CourseLoadError("Could not reach the course service.", { cause });
  }
  if (!response.ok) {
    throw new CourseLoadError(`Course generation failed (HTTP ${response.status}).`);
  }
  return parseResponse(response);
}

/** Fetch + parse a previously built course by id (GET /api/courses/:id) — opening a run from the
 *  sidebar history. Network / HTTP / malformed failures all surface as CourseLoadError. */
export async function fetchCourseById(
  apiBaseUrl: string,
  id: string,
  signal?: AbortSignal,
): Promise<Course> {
  let response: Response;
  try {
    response = await fetch(
      `${apiBaseUrl}/api/courses/${encodeURIComponent(id)}`,
      signal ? { signal } : undefined,
    );
  } catch (cause) {
    throw new CourseLoadError("Could not reach the course service.", { cause });
  }
  if (!response.ok) {
    const detail = response.status === 404 ? "This run's course is no longer available." : null;
    throw new CourseLoadError(detail ?? `Couldn't open this course (HTTP ${response.status}).`);
  }
  return parseResponse(response);
}

/** Resolve the course for the current environment: the live API when VITE_API_URL is set,
 *  otherwise the bundled static seed. The web stays usable offline either way. */
export function resolveCourse(signal?: AbortSignal): Promise<Course> {
  const apiBaseUrl = import.meta.env.VITE_API_URL;
  const topic = import.meta.env.VITE_COURSE_TOPIC ?? "how binary search works";
  return apiBaseUrl
    ? generateCourse(apiBaseUrl, topic, signal)
    : loadCourse(DEFAULT_COURSE_URL, signal);
}

async function parseResponse(response: Response): Promise<Course> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch (cause) {
    throw new CourseLoadError("Course response was not valid JSON.", { cause });
  }
  return parseCourse(payload);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

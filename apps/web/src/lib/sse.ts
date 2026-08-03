/** One decoded Server-Sent Events frame: its event name and its JSON payload. */
export interface SseFrame {
  event: string;
  data: unknown;
}

/**
 * Read a response body as a stream of SSE frames.
 *
 * Consumed via a `ReadableStream` reader rather than `EventSource` so the request stays abortable,
 * authenticated, and testable — every streaming surface in the product needs all three. Frames with
 * no data (heartbeat comments, which keep an idle connection alive through a silent stretch) are
 * skipped rather than surfaced, and an unparseable frame is dropped rather than taking the stream
 * down with it: one malformed beat must not cost a build that is still running.
 */
export async function* readSseFrames(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<SseFrame, void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // Frames are separated by a blank line; yield every complete one in the buffer and keep the
    // remainder, which may be a frame cut in half by the chunk boundary.
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const frame = parseFrame(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      if (frame) yield frame;
      boundary = buffer.indexOf("\n\n");
    }
  }
}

/** Parse one raw frame into its event name + decoded JSON data, or null if it carries neither. */
function parseFrame(frame: string): SseFrame | null {
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

# Journey: live-build-stream

## Feature
Make the web app an interactive tool: type a topic → Generate → **watch the agent
pipeline build the course live** (real server-streamed per-stage progress) → explore the
generated course in the existing prerequisite-graph explorer.

## Problem today
`apps/web` auto-POSTs one hardcoded topic ("how binary search works") to `POST /api/courses`
on page load and renders the finished graph. No topic input, no Generate, no build view.
`POST /api/courses` is synchronous and emits no progress.

## Scope (3 surfaces)
1. **Orchestrator** (`packages/agent`): `IProgressSink` Protocol + `ProgressEvent` Pydantic
   schema + emit an ordered event at each stage boundary
   (run_started → concepts_extracted → graph_built → curriculum_designed →
   module_authored×N → claims_verified → run_completed). Injected (DIP); NoOp default keeps
   existing call sites working. Keep structlog events + run_id correlation + provenance intact.
2. **API** (`apps/api`): `GET /api/courses/stream?topic=...` → `text/event-stream` (SSE,
   EventSource-compatible). Wires an async-queue sink, streams each ProgressEvent as it
   happens, ends with a final event carrying the finished camelCase course. Keep `POST
   /api/courses`. Respect `LUNARIS_PIPELINE` stub|live. X-Run-Id correlation.
3. **Web** (`apps/web`): topic input + Generate (enterprise-ui, all states, WCAG 2.2 AA);
   live build-progress view (EventSource, per-stage fill-in with counts); on the final event
   hand off to `PrereqGraphExplorer`. Offline (no `VITE_API_URL`) → static seed. Handle
   loading/streaming/empty/error/abort.

## Success criteria
- In-process ASGI test: the stream yields the ordered stage events then the final published
  course (stub pipeline), with run_id correlation across layers.
- Web tests: input → progress → result, and error states.
- Variant coverage: stub (deterministic) + live (behind the eval/key gate).
- enterprise-ui self-review clean on all web. Default demo = stub (instant, no key); also
  works with `LUNARIS_PIPELINE=live`.

## Non-goals
- Resumable/replayable streams, multi-client fan-out, persistence of progress.
- Changing the pipeline stages themselves or provenance.

## Decisions (resolved from codebase/conventions)
- `ProgressEvent` lives in `lunaris_runtime.schema` (it's a wire contract → `CourseModel`,
  camelCase) and carries a monotonic `sequence` ordinal for ordering **instead of a
  wall-clock timestamp**, to keep the deterministic suite stable (the structlog trail already
  carries timestamps for ops). [source: schema/base.py CourseModel convention + eval-discipline]
- `IProgressSink` lives in `packages/agent` (`lunaris_agent/progress/`) — the orchestrator owns
  the emission contract; co-located `protocol.py` matches the repo pattern (models/, critic/,
  each subagent/). [source: agent package layout]
- SSE endpoint is `GET` (EventSource is GET-only) with `topic` as a query param. [source: spec]
- Demo defaults to stub pipeline (no key, instant). [source: spec + run.sh default]
- Web consumes the SSE stream via `fetch` + `ReadableStream` (not `EventSource`): testable with
  the existing fetch-mock harness, supports `AbortController` cancel, avoids EventSource's jsdom
  gaps. The endpoint stays GET text/event-stream (EventSource-compatible too). [source: web test harness]
- App branches on `VITE_API_URL`: set → live flow (idle TopicForm → streaming BuildProgress →
  ready explorer → error); unset → offline static seed (current behavior, graceful). [source: spec]

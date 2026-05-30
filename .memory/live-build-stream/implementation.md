# Implementation log: live-build-stream

## Task list
- [ ] **T1 — Orchestrator progress-sink** (`packages/agent` + `lunaris_runtime.schema`):
  `ProgressStage` enum, `ProgressEvent` schema, `IProgressSink` + `NoOpProgressSink`, orchestrator
  emits ordered events at each stage. RED: recording-sink integration test over the stub pipeline.
  Status: GREEN+committed. ProgressStage enum + ProgressEvent (runtime schema), IProgressSink +
  NoOpProgressSink (lunaris_agent/progress/), Orchestrator.run(progress=...) emits the ordered
  backbone via a run-local `emit` closure (no instance state). 2 tests; 105 py total; ruff clean.
- [ ] **T2 — API SSE endpoint** (`apps/api`): `GET /api/courses/stream?topic=` → text/event-stream;
  async-queue sink; ordered events + final course; X-Run-Id; keep POST. RED: in-process ASGI SSE test.
  Status: GREEN+reviewed+committed. QueueProgressSink + CourseService.stream() (async-gen: run task
  + queue race, cancels on early exit, logs course_stream_failed w/ run_id) + GET /api/courses/stream
  (StreamingResponse text/event-stream, X-Run-Id, _sse_frame helper). 4 tests (ordered events+course,
  422, log correlation, early-disconnect cancel). Live-verified: 11 progress + 1 course frame.
  3-agent review (no BLOCKING) addressed: _StreamItem private, service-layer error log, helper extract.
- [x] **T3+T4 — Web live-build flow** (`apps/web`): GREEN+reviewed. ProgressStage/ProgressEvent TS types;
  `streamCourse` (fetch + ReadableStream SSE parser, not EventSource — abortable + testable);
  `useCourseStream` hook (idle→streaming→ready→error, AbortController lifecycle); `TopicForm` (labelled
  input, validate-on-submit, example chips); `BuildProgress` (live checklist + counts + aria-live);
  `App` branches SeedApp(offline)/StudioApp(live). 45 web tests; typecheck/lint/format/build green.
  **Visually verified in-browser (Playwright)**: idle form, live BUILDING checklist, result explorer.
  2-agent review (1 BLOCKING: test/fixtures dup → fixed; hoisted BuildProgress helpers; 10px→eyebrow).
- [x] **T5 — offline + error/abort + variants**: offline=SeedApp (existing tests), error state + retry
  (tested), abort = useCourseStream aborts prior controller + on unmount (T2 covers server-side cancel),
  empty-topic validation (tested). Variant: stub (deterministic, tested) + live (same orchestrator path,
  gated by ANTHROPIC_API_KEY; stub flow verified live in-browser).

## Walking skeleton
T1+T2 together form the skeleton's backend half (web → API SSE → orchestrator → events + course);
T3+T4 close the loop to the UI. First green: the T2 ASGI test asserting ordered events + final course.

## Log IDs
- run_id correlation: ProgressEvent.run_id == X-Run-Id == structlog run_id.

## Progress log
- (init) Pre-flight green: ruff clean, 103 py tests, web typecheck+lint clean, supabase up.

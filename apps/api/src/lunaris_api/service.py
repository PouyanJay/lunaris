import asyncio
from collections.abc import AsyncIterator, Callable

import structlog
from lunaris_agent import CoursePipeline, LessonRegenerator
from lunaris_runtime.persistence import CourseStore, IRunStore
from lunaris_runtime.schema import AgentEvent, Course, CourseRun, ProgressEvent, RunStatus

from .progress_sink import QueueAgentSink, QueueProgressSink, StreamItem

logger = structlog.get_logger()

# Bounds for the run-history list, shared with the GET /api/runs router so the HTTP validation and
# the service-layer clamp stay in lockstep (single source of truth).
RUNS_LIMIT_DEFAULT = 50
RUNS_LIMIT_MIN = 1
RUNS_LIMIT_MAX = 200

# Builds the per-run course pipeline (stub / live orchestrator / deep agent) from the shared store.
PipelineFactory = Callable[[CourseStore], CoursePipeline]

# A streamed item: a ("progress", ProgressEvent) stage, an ("agent", AgentEvent) transcript beat,
# or the terminal ("course", Course). Internal to the service<->router contract; the kind string
# maps directly to the SSE event name.
_StreamItem = tuple[str, ProgressEvent | AgentEvent | Course]


class CourseServiceError(Exception):
    """Base for CourseService domain errors."""


class LessonRegenerationUnsupportedError(CourseServiceError):
    """Raised when the active pipeline cannot regenerate a single lesson (e.g. the deep agent)."""


class CourseService:
    """Application service over the course pipeline — the API's only door to the agent.

    Builds a course pipeline per run via the injected factory (stub / live orchestrator / deep
    agent) and persists through the shared ``CourseStore``, so the HTTP layer stays free of
    pipeline wiring.
    """

    def __init__(
        self,
        store: CourseStore,
        pipeline_factory: PipelineFactory,
        run_store: IRunStore | None = None,
    ) -> None:
        self._store = store
        self._factory = pipeline_factory
        # Best-effort: a failed history write must never propagate and break a build (mirrors how
        # the progress/agent sinks default to a no-op for batch callers).
        self._run_store = run_store

    async def create(self, topic: str, *, course_id: str, run_id: str) -> Course:
        pipeline = self._factory(self._store)
        await self._record_start(run_id=run_id, course_id=course_id, topic=topic)
        try:
            course = await pipeline.run(topic, course_id=course_id, run_id=run_id)
        except Exception:
            await self._record_failure(course_id)
            raise
        await self._record_finish(course)
        return course

    async def stream(
        self, topic: str, *, course_id: str, run_id: str
    ) -> AsyncIterator[_StreamItem]:
        """Run the pipeline, yielding each progress/agent event as it happens, then the course.

        The pipeline runs in a background task feeding one shared queue (coarse ``progress`` stages
        and fine-grained ``agent`` transcript beats, interleaved in emission order); we forward each
        item as it lands and, once the run completes, drain any tail and yield the finished
        course-object. The run task is always cancelled on early exit (a disconnected client) so a
        dropped SSE stream never leaks a running pipeline.

        A pipeline failure is logged here with ``run_id`` (so a truncated stream is still
        triangulatable across layers) and re-raised; the client-visible error frame is a
        later refinement.
        """
        queue: asyncio.Queue[StreamItem] = asyncio.Queue()
        run_task: asyncio.Task[Course] | None = None
        await self._record_start(run_id=run_id, course_id=course_id, topic=topic)
        try:
            pipeline = self._factory(self._store)
            run_task = asyncio.create_task(
                pipeline.run(
                    topic,
                    course_id=course_id,
                    run_id=run_id,
                    progress=QueueProgressSink(queue),
                    agent=QueueAgentSink(queue),
                )
            )
            while True:
                next_event_task = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait(
                    {next_event_task, run_task}, return_when=asyncio.FIRST_COMPLETED
                )
                if next_event_task in done:
                    yield next_event_task.result()  # already a (kind, payload) tuple
                    continue
                # The run finished: cancel the pending get, flush any queued tail, stop.
                next_event_task.cancel()
                while not queue.empty():
                    yield queue.get_nowait()
                break
            course = run_task.result()  # .result() propagates a pipeline failure here
            await self._record_finish(course)
            yield ("course", course)
        except Exception:
            logger.error("course_stream_failed", course_id=course_id, run_id=run_id, exc_info=True)
            await self._record_failure(course_id)
            raise
        finally:
            if run_task is not None and not run_task.done():
                run_task.cancel()

    def get(self, course_id: str) -> Course | None:
        try:
            return self._store.load(course_id)
        except FileNotFoundError:
            return None

    async def regenerate_lesson(
        self, course_id: str, lesson_id: str, *, run_id: str
    ) -> Course | None:
        """Re-author one lesson of an existing course and return the updated course.

        Returns ``None`` if the course or lesson is unknown. Raises the unsupported error if the
        active pipeline can't regenerate a single lesson (e.g. the deep-agent builder).
        """
        pipeline = self._factory(self._store)
        if not isinstance(pipeline, LessonRegenerator):
            raise LessonRegenerationUnsupportedError(type(pipeline).__name__)
        return await pipeline.regenerate_lesson(course_id, lesson_id, run_id=run_id)

    async def list_runs(self, *, limit: int = RUNS_LIMIT_DEFAULT) -> list[CourseRun]:
        """Return an empty list when no run store is wired (batch / no-history callers), so the
        endpoint degrades gracefully instead of failing. ``limit`` is clamped to a sane range for
        direct callers; the HTTP router already validates it upstream.
        """
        if self._run_store is None:
            return []
        bounded = max(RUNS_LIMIT_MIN, min(limit, RUNS_LIMIT_MAX))
        return await self._run_store.list_recent(limit=bounded)

    async def _record_start(self, *, run_id: str, course_id: str, topic: str) -> None:
        """Record the run as ``RUNNING`` — best-effort (a history failure never breaks a build)."""
        if self._run_store is None:
            return
        try:
            await self._run_store.start(run_id=run_id, course_id=course_id, topic=topic)
        except Exception:
            logger.warning(
                "run_history_start_failed", course_id=course_id, run_id=run_id, exc_info=True
            )

    async def _record_finish(self, course: Course) -> None:
        """Mark the run COMPLETED with the artifact's KC/module counts — best-effort."""
        if self._run_store is None:
            return
        try:
            await self._run_store.finish(
                course_id=course.id,
                status=RunStatus.COMPLETED,
                kc_count=len(course.graph.nodes),
                module_count=len(course.modules),
            )
        except Exception:
            logger.warning("run_history_finish_failed", course_id=course.id, exc_info=True)

    async def _record_failure(self, course_id: str) -> None:
        """Mark the run FAILED — best-effort (a no-op if the start row was never written)."""
        if self._run_store is None:
            return
        try:
            await self._run_store.finish(
                course_id=course_id, status=RunStatus.FAILED, kc_count=0, module_count=0
            )
        except Exception:
            logger.warning("run_history_mark_failed_error", course_id=course_id, exc_info=True)

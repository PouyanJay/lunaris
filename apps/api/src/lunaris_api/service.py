import asyncio
import re
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


class RunHistoryUnavailableError(CourseServiceError):
    """Raised when the run-history backend can't be read (Supabase unreachable, table missing).

    Reads, unlike the best-effort writes, surface their failure rather than degrade to an empty
    list (which would lie "no runs yet"); the router maps this to a 503."""


class InvalidCourseIdError(CourseServiceError):
    """Raised when a course_id isn't the safe shape (alphanumeric, ``-``, ``_``). Guards the
    filesystem path against traversal before it becomes ``<id>.json``. Router → 400."""


class CourseDeletionConflictError(CourseServiceError):
    """Raised when deleting a course whose run is still building — cancel it first. Router → 409."""


class CourseNotFoundError(CourseServiceError):
    """Raised when deleting a course with no stored file and no run-history row. Router → 404."""


# A safe course_id is a non-empty run of [A-Za-z0-9_-] — no path separators, dots, or ``..`` that
# could escape the course directory when the id becomes ``<id>.json``. Real ids are uuid4().hex.
_SAFE_COURSE_ID = re.compile(r"[A-Za-z0-9_-]+")


def _is_safe_course_id(course_id: str) -> bool:
    return _SAFE_COURSE_ID.fullmatch(course_id) is not None


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
        later refinement. On client disconnect the consumer is cancelled mid-build — the run is
        recorded FAILED on the way out so it is never left stuck RUNNING in history.
        """
        queue: asyncio.Queue[StreamItem] = asyncio.Queue()
        run_task: asyncio.Task[Course] | None = None
        # Tracks whether a terminal status (COMPLETED/FAILED) was recorded. A client disconnect
        # throws GeneratorExit/CancelledError (both BaseException, NOT Exception) at the suspended
        # ``yield``, bypassing the ``except Exception`` below; the ``finally`` uses this flag to
        # record FAILED for an interrupted run instead of leaving it stuck RUNNING.
        recorded = False
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
            recorded = True
            yield ("course", course)
        except Exception:
            logger.error("course_stream_failed", course_id=course_id, run_id=run_id, exc_info=True)
            await self._record_failure(course_id)
            recorded = True
            raise
        finally:
            if run_task is not None and not run_task.done():
                run_task.cancel()
            if not recorded:
                # The consumer was cancelled (client disconnect) before the run reached a terminal
                # event, so neither branch above ran — the run would otherwise stay stuck RUNNING in
                # history. Record it FAILED on the way out. Awaiting here is safe during async-gen
                # finalization because we do not ``yield`` in ``finally``; ``_record_failure`` is
                # best-effort (never raises).
                logger.info("run_recorded_failed_on_disconnect", course_id=course_id, run_id=run_id)
                await self._record_failure(course_id)

    def get(self, course_id: str) -> Course | None:
        # An unsafe id can't name a stored course (ids are uuid4().hex); treat it as not-found
        # rather than let it reach path_for — the same traversal guard delete_course applies.
        if not _is_safe_course_id(course_id):
            return None
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
        if not _is_safe_course_id(course_id):
            return None  # unsafe id can't name a stored course → not-found (router → 404)
        pipeline = self._factory(self._store)
        if not isinstance(pipeline, LessonRegenerator):
            raise LessonRegenerationUnsupportedError(type(pipeline).__name__)
        return await pipeline.regenerate_lesson(course_id, lesson_id, run_id=run_id)

    async def delete_course(self, course_id: str) -> None:
        """Delete a course and its per-course assets: the stored course-object + run-history row.

        Guards (one door for all callers): rejects an unsafe id before touching the filesystem;
        refuses to delete a course whose run is still building (cancel it first); raises not-found
        if neither asset exists. Otherwise idempotent — clearing a stray file or row alone succeeds.
        """
        if not _is_safe_course_id(course_id):
            raise InvalidCourseIdError(course_id)
        await self._ensure_not_running(course_id)
        await self._purge_course_assets(course_id)

    async def _ensure_not_running(self, course_id: str) -> None:
        """Block deleting a course whose build is still in progress. With no run store wired there's
        no run history and so no live build to protect, so the guard is intentionally skipped."""
        if self._run_store is None:
            return
        run = await self._run_store.get(course_id=course_id)
        if run is not None and run.status == RunStatus.RUNNING:
            raise CourseDeletionConflictError(course_id)

    async def _purge_course_assets(self, course_id: str) -> None:
        """Remove the stored file + the run row; not-found if neither existed."""
        file_deleted = self._store.delete(course_id)
        row_deleted = (
            await self._run_store.delete(course_id=course_id)
            if self._run_store is not None
            else False
        )
        if not file_deleted and not row_deleted:
            raise CourseNotFoundError(course_id)
        logger.info(
            "course_deleted",
            course_id=course_id,
            file_deleted=file_deleted,
            row_deleted=row_deleted,
        )

    async def list_runs(self, *, limit: int = RUNS_LIMIT_DEFAULT) -> list[CourseRun]:
        """Return an empty list when no run store is wired (batch / no-history callers), so the
        endpoint degrades gracefully instead of failing. ``limit`` is clamped to a sane range for
        direct callers; the HTTP router already validates it upstream.
        """
        if self._run_store is None:
            return []
        bounded = max(RUNS_LIMIT_MIN, min(limit, RUNS_LIMIT_MAX))
        try:
            return await self._run_store.list_recent(limit=bounded)
        except Exception as exc:
            # A configured backend that fails to read is a real outage — surface it (vs. a silent
            # empty list, which would lie "no runs yet"). Logged with the run_id from contextvars so
            # the failure is triangulatable across layers; the router maps it to a recoverable 503.
            logger.warning("run_history_list_failed", limit=bounded, exc_info=True)
            raise RunHistoryUnavailableError("Run history backend is unavailable") from exc

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

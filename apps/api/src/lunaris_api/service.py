import asyncio
from collections.abc import AsyncIterator, Callable

import structlog
from lunaris_agent import CoursePipeline
from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.schema import Course, ProgressEvent

from .progress_sink import QueueProgressSink

logger = structlog.get_logger()

# Builds the per-run course pipeline (stub / live orchestrator / deep agent) from the shared store.
PipelineFactory = Callable[[CourseStore], CoursePipeline]

# A streamed item: a ("progress", ProgressEvent) update, or the terminal ("course", Course).
# Internal to the service<->router contract; the kind string maps directly to the SSE event name.
_StreamItem = tuple[str, ProgressEvent | Course]


class CourseService:
    """Application service over the course pipeline — the API's only door to the agent.

    Builds a course pipeline per run via the injected factory (stub / live orchestrator / deep
    agent) and persists through the shared ``CourseStore``, so the HTTP layer stays free of
    pipeline wiring.
    """

    def __init__(self, store: CourseStore, pipeline_factory: PipelineFactory) -> None:
        self._store = store
        self._factory = pipeline_factory

    async def create(self, topic: str, *, course_id: str, run_id: str) -> Course:
        pipeline = self._factory(self._store)
        return await pipeline.run(topic, course_id=course_id, run_id=run_id)

    async def stream(
        self, topic: str, *, course_id: str, run_id: str
    ) -> AsyncIterator[_StreamItem]:
        """Run the pipeline, yielding each progress event as it happens, then the course.

        The pipeline runs in a background task feeding a queue; we forward each
        ProgressEvent as it lands and, once the run completes, drain any tail and yield
        the finished course-object. The run task is always cancelled on early exit (a
        disconnected client) so a dropped SSE stream never leaks a running pipeline.

        A pipeline failure is logged here with ``run_id`` (so a truncated stream is still
        triangulatable across layers) and re-raised; the client-visible error frame is a
        later refinement.
        """
        queue: asyncio.Queue[ProgressEvent] = asyncio.Queue()
        run_task: asyncio.Task[Course] | None = None
        try:
            pipeline = self._factory(self._store)
            run_task = asyncio.create_task(
                pipeline.run(
                    topic, course_id=course_id, run_id=run_id, progress=QueueProgressSink(queue)
                )
            )
            while True:
                next_event_task = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait(
                    {next_event_task, run_task}, return_when=asyncio.FIRST_COMPLETED
                )
                if next_event_task in done:
                    yield ("progress", next_event_task.result())
                    continue
                # The run finished: cancel the pending get, flush any queued tail, stop.
                next_event_task.cancel()
                while not queue.empty():
                    yield ("progress", queue.get_nowait())
                break
            yield ("course", run_task.result())  # .result() propagates a pipeline failure here
        except Exception:
            logger.error("course_stream_failed", course_id=course_id, run_id=run_id, exc_info=True)
            raise
        finally:
            if run_task is not None and not run_task.done():
                run_task.cancel()

    def get(self, course_id: str) -> Course | None:
        try:
            return self._store.load(course_id)
        except FileNotFoundError:
            return None

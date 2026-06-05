import asyncio
from typing import Any


class RunRegistry:
    """Tracks in-flight course-build tasks by ``run_id`` so a separate request can cancel one.

    A build registers its pipeline task (with its ``course_id``) at start and discards it at end.
    ``cancel`` marks the run as explicitly cancelled (so its own teardown records CANCELLED, not
    FAILED), cancels the task, and returns the ``course_id`` so the cancel handler can record the
    terminal status itself — robust to the client dropping the stream before its teardown can write.
    Process-wide singleton at the composition root — every request shares it, so the cancel request
    and the build request see the same in-flight set.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._course_ids: dict[str, str] = {}
        self._cancelled: set[str] = set()

    def register(self, run_id: str, task: asyncio.Task[Any], course_id: str) -> None:
        self._tasks[run_id] = task
        self._course_ids[run_id] = course_id

    def discard(self, run_id: str) -> None:
        """Forget a finished run (called from the build's teardown). Idempotent."""
        self._tasks.pop(run_id, None)
        self._course_ids.pop(run_id, None)
        self._cancelled.discard(run_id)

    def cancel(self, run_id: str) -> str | None:
        """Request cancellation: mark the run + cancel its task. Returns the run's ``course_id``
        when something was in-flight (so the caller records CANCELLED), or ``None`` when nothing is
        in-flight (unknown or already finished) so the caller can surface a 404.

        Benign race: if the pipeline wins (completes in the same loop turn before CancelledError is
        delivered), the build records its real terminal status; the caller's CANCELLED write lands
        on a terminal row. The cancel still returned 202.
        """
        task = self._tasks.get(run_id)
        if task is None or task.done():
            return None
        self._cancelled.add(run_id)
        task.cancel()
        return self._course_ids.get(run_id)

    def was_cancelled(self, run_id: str) -> bool:
        """Whether this run was explicitly cancelled (vs a client disconnect or a pipeline error).
        The build's teardown reads this to record CANCELLED rather than FAILED."""
        return run_id in self._cancelled

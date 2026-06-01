import asyncio
from typing import Any


class RunRegistry:
    """Tracks in-flight course-build tasks by ``run_id`` so a separate request can cancel one.

    A build registers its pipeline task at start and discards it at end. ``cancel`` marks the run as
    explicitly cancelled (so its own teardown records CANCELLED, not FAILED) and cancels the task.
    Process-wide singleton at the composition root — every request shares it, so the cancel request
    and the build request see the same in-flight set.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._cancelled: set[str] = set()

    def register(self, run_id: str, task: asyncio.Task[Any]) -> None:
        self._tasks[run_id] = task

    def discard(self, run_id: str) -> None:
        """Forget a finished run (called from the build's teardown). Idempotent."""
        self._tasks.pop(run_id, None)
        self._cancelled.discard(run_id)

    def cancel(self, run_id: str) -> bool:
        """Request cancellation: mark the run + cancel its task. Returns False when nothing is
        in-flight for ``run_id`` (unknown or already finished) so the caller can surface a 404.

        Benign race: if the pipeline wins (completes in the same loop turn before CancelledError is
        delivered), the build records its real terminal status and CANCELLED is never written — the
        cancel still returned 202, but the run lands COMPLETED/FAILED. Correct, just not CANCELLED.
        """
        task = self._tasks.get(run_id)
        if task is None or task.done():
            return False
        self._cancelled.add(run_id)
        task.cancel()
        return True

    def was_cancelled(self, run_id: str) -> bool:
        """Whether this run was explicitly cancelled (vs a client disconnect or a pipeline error).
        The build's teardown reads this to record CANCELLED rather than FAILED."""
        return run_id in self._cancelled

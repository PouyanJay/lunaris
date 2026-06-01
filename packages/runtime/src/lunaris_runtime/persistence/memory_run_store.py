from datetime import UTC, datetime

from lunaris_runtime.schema import CourseRun, RunStatus


class InMemoryRunStore:
    """In-process run-history index — the no-key/CI fallback and the test stub.

    History lives only for the process lifetime (lost on restart); durable, cross-machine history
    requires the Supabase-backed store. Wired as a process-wide singleton at the composition root
    so every request shares one history; tests construct their own instance. Runs are returned
    newest-first by insertion order (not wall clock), so ordering is stable under same-instant runs.
    """

    def __init__(self) -> None:
        self._runs: dict[str, CourseRun] = {}
        self._order: list[str] = []

    async def start(self, *, run_id: str, course_id: str, topic: str) -> None:
        now = datetime.now(UTC)
        self._runs[course_id] = CourseRun(
            id=course_id,
            run_id=run_id,
            topic=topic,
            status=RunStatus.RUNNING,
            created_at=now,
            updated_at=now,
        )
        if course_id not in self._order:
            self._order.append(course_id)

    async def finish(
        self, *, course_id: str, status: RunStatus, kc_count: int, module_count: int
    ) -> None:
        existing = self._runs.get(course_id)
        if existing is None:
            return  # start was never recorded (best-effort) — nothing to finish
        self._runs[course_id] = existing.model_copy(
            update={
                "status": status,
                "kc_count": kc_count,
                "module_count": module_count,
                "updated_at": datetime.now(UTC),
            }
        )

    async def list_recent(self, *, limit: int = 50) -> list[CourseRun]:
        newest_first = list(reversed(self._order))[:limit]
        return [self._runs[course_id] for course_id in newest_first]

    async def get(self, *, course_id: str) -> CourseRun | None:
        return self._runs.get(course_id)

    async def delete(self, *, course_id: str) -> bool:
        """Drop a run's history row. Idempotent: returns False if it wasn't recorded."""
        if course_id not in self._runs:
            return False
        del self._runs[course_id]
        self._order = [cid for cid in self._order if cid != course_id]
        return True

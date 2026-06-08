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
        # The owner per course_id (Phase 2). Parallel to ``_runs`` rather than a CourseRun field, so
        # the wire contract stays unchanged and owner_id never leaks to the web. None = unscoped.
        self._owners: dict[str, str | None] = {}

    def _owns(self, course_id: str, owner_id: str | None) -> bool:
        """Whether a scoped caller may touch this row. None (unscoped) always may."""
        return owner_id is None or self._owners.get(course_id) == owner_id

    async def start(
        self, *, run_id: str, course_id: str, topic: str, owner_id: str | None = None
    ) -> None:
        now = datetime.now(UTC)
        self._runs[course_id] = CourseRun(
            id=course_id,
            run_id=run_id,
            topic=topic,
            status=RunStatus.RUNNING,
            created_at=now,
            updated_at=now,
        )
        self._owners[course_id] = owner_id
        if course_id not in self._order:
            self._order.append(course_id)

    async def finish(
        self,
        *,
        course_id: str,
        status: RunStatus,
        kc_count: int,
        module_count: int,
        owner_id: str | None = None,
    ) -> None:
        existing = self._runs.get(course_id)
        if existing is None or not self._owns(course_id, owner_id):
            return  # start was never recorded, or not the caller's row — nothing to finish
        self._runs[course_id] = existing.model_copy(
            update={
                "status": status,
                "kc_count": kc_count,
                "module_count": module_count,
                "updated_at": datetime.now(UTC),
            }
        )

    async def list_recent(self, *, limit: int = 50, owner_id: str | None = None) -> list[CourseRun]:
        newest_first = (
            course_id for course_id in reversed(self._order) if self._owns(course_id, owner_id)
        )
        return [self._runs[course_id] for course_id in list(newest_first)[:limit]]

    async def get(self, *, course_id: str, owner_id: str | None = None) -> CourseRun | None:
        if not self._owns(course_id, owner_id):
            return None
        return self._runs.get(course_id)

    async def delete(self, *, course_id: str, owner_id: str | None = None) -> bool:
        """Drop a run's history row. Idempotent: returns False if it wasn't recorded or isn't the
        caller's row."""
        if course_id not in self._runs or not self._owns(course_id, owner_id):
            return False
        del self._runs[course_id]
        del self._owners[course_id]
        self._order = [cid for cid in self._order if cid != course_id]
        return True

from lunaris_runtime.schema import CourseCost


class InMemoryCourseCostStore:
    """In-process course-cost rollup store — the no-key/CI fallback and the test stub.

    Rollups live only for the process lifetime; durable, cross-machine reads require the
    Supabase-backed store. Wired as a process-wide singleton so a build's upsert and a later
    ``GET .../cost`` read share one map. Keyed by ``course_id``; an upsert replaces the prior rollup
    (idempotent recompute).
    """

    def __init__(self) -> None:
        self._costs: dict[str, CourseCost] = {}
        # The owner per course_id (per-user scoping); kept parallel so CourseCost's wire shape stays
        # clean and another user's rollup reads as absent.
        self._owners: dict[str, str | None] = {}

    async def upsert(self, *, cost: CourseCost, owner_id: str | None = None) -> None:
        self._costs[cost.course_id] = cost
        self._owners[cost.course_id] = owner_id

    async def get(self, *, course_id: str, owner_id: str | None = None) -> CourseCost | None:
        if owner_id is not None and self._owners.get(course_id) != owner_id:
            return None  # another user's rollup is invisible
        return self._costs.get(course_id)

    async def delete_for_course(self, *, course_id: str, owner_id: str | None = None) -> int:
        if owner_id is not None and self._owners.get(course_id) != owner_id:
            return 0
        removed = 1 if self._costs.pop(course_id, None) is not None else 0
        self._owners.pop(course_id, None)
        return removed

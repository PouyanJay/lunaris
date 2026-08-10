from lunaris_runtime.schema import CostSubjectType, SubjectCost


class InMemorySubjectCostStore:
    """In-process cost rollup store — the no-key/CI fallback and the test stub.

    Rollups live only for the process lifetime; durable, cross-machine reads require the
    Supabase-backed store. Wired as a process-wide singleton so a build's upsert and a later
    ``GET .../cost`` read share one map. Keyed by ``(subject_type, subject_id)``; an upsert replaces
    the prior rollup (idempotent recompute).
    """

    def __init__(self) -> None:
        self._costs: dict[tuple[CostSubjectType, str], SubjectCost] = {}
        # The owner per subject (per-user scoping); kept parallel so SubjectCost's wire shape stays
        # clean and another user's rollup reads as absent.
        self._owners: dict[tuple[CostSubjectType, str], str | None] = {}

    async def upsert(self, *, cost: SubjectCost, owner_id: str | None = None) -> None:
        subject = (cost.subject_type, cost.subject_id)
        self._costs[subject] = cost
        self._owners[subject] = owner_id

    async def get(
        self, *, subject_type: CostSubjectType, subject_id: str, owner_id: str | None = None
    ) -> SubjectCost | None:
        subject = (subject_type, subject_id)
        if owner_id is not None and self._owners.get(subject) != owner_id:
            return None  # another user's rollup is invisible
        return self._costs.get(subject)

    async def delete_for_subject(
        self, *, subject_type: CostSubjectType, subject_id: str, owner_id: str | None = None
    ) -> int:
        subject = (subject_type, subject_id)
        if owner_id is not None and self._owners.get(subject) != owner_id:
            return 0
        removed = 1 if self._costs.pop(subject, None) is not None else 0
        self._owners.pop(subject, None)
        return removed

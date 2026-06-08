from lunaris_runtime.schema import Course

from .course_store_protocol import ICourseStore


class OwnerScopedCourseStore:
    """An ``ICourseStore`` decorator that binds one owner to every call (Phase 2 per-user scoping).

    The course SAVE happens deep inside the agent harness (the ``finalize_course`` tool calls
    ``store.save(course)``) and inside the legacy ``Orchestrator`` — neither knows the authenticated
    user, nor should. Rather than thread ``owner_id`` through the whole pipeline, the API wraps
    the shared store in this decorator (bound to the current user) and hands the wrapper to the
    pipeline factory: a plain ``save(course)`` from the harness then arrives at the underlying store
    as ``save(course, owner_id=<user>)``, stamping ownership at the one place it is known.

    Reads/deletes are forwarded with the bound owner too, so a pipeline that re-reads its own course
    (the regenerate path) stays scoped. The ``owner_id`` keyword exists only to satisfy
    ``ICourseStore``; the harness always calls these methods without it. Passing one that conflicts
    with the bound owner is a programming error (a second source of truth) and raises — so a misuse
    is loud, never a silent override.
    """

    def __init__(self, inner: ICourseStore, owner_id: str) -> None:
        self._inner = inner
        self._owner_id = owner_id

    def _resolved(self, owner_id: str | None) -> str:
        """The owner to forward: always the bound one. A caller-supplied owner that disagrees is a
        bug (two sources of truth), so reject it rather than silently override."""
        if owner_id is not None and owner_id != self._owner_id:
            raise ValueError(
                "OwnerScopedCourseStore is bound to one owner; do not pass a different owner_id"
            )
        return self._owner_id

    def save(self, course: Course, *, owner_id: str | None = None) -> None:
        self._inner.save(course, owner_id=self._resolved(owner_id))

    def load(self, course_id: str, *, owner_id: str | None = None) -> Course:
        return self._inner.load(course_id, owner_id=self._resolved(owner_id))

    def delete(self, course_id: str, *, owner_id: str | None = None) -> bool:
        return self._inner.delete(course_id, owner_id=self._resolved(owner_id))

from typing import Protocol

from lunaris_runtime.schema import Course


class ICourseStore(Protocol):
    """A destination for the finished course object — where a built Course is persisted and re-read.

    The API's ``CourseService`` and the agent pipelines depend on this abstraction (DIP), not on a
    concrete store, so the persistence target is swappable: the file-backed ``CourseStore`` (offline
    dev) and the Supabase-backed ``SupabaseCourseStore`` (durable, production). Methods
    are synchronous — the supabase-py client is sync, and async callers off-load the blocking write
    via ``asyncio.to_thread`` (see the harness ``finalize_course`` tool), so both stores present the
    same sync surface.

    Contract: ``load`` raises ``FileNotFoundError`` when no course has that id — the store-agnostic
    not-found signal the caller catches to answer 404. ``delete`` is idempotent — ``True`` if a
    row/file was removed, ``False`` if it was already absent (so the caller can choose 204 vs 404).

    ``owner_id`` (Phase 2 per-user scoping) is the authenticated caller's id: ``save`` stamps it on
    the row, ``load``/``delete`` constrain to it (a course owned by another user is not-found).
    ``None`` means unscoped — the auth-off / single-user path, byte-for-byte today's behavior. The
    file store is single-user and ignores it; the Supabase store enforces it.
    """

    def save(self, course: Course, *, owner_id: str | None = None) -> None: ...

    def load(self, course_id: str, *, owner_id: str | None = None) -> Course: ...

    def delete(self, course_id: str, *, owner_id: str | None = None) -> bool: ...

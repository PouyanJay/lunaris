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
    """

    def save(self, course: Course) -> None: ...

    def load(self, course_id: str) -> Course: ...

    def delete(self, course_id: str) -> bool: ...

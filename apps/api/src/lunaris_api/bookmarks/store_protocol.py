from typing import Protocol

from .bookmark import Bookmark, BookmarkKind


class IBookmarkStore(Protocol):
    """Per-user storage for saved lessons/concepts/sources.

    Every method is scoped to a ``user_id``; ``None`` is the unscoped single-user posture used
    when auth is unconfigured (offline dev — the in-memory backend). With auth on, the API always
    passes a real user id and the Supabase backend's rows are additionally owner-scoped by RLS.

    Contract: ``save`` upserts on the natural key (user, kind, course_id, target_id) — re-saving
    refreshes the display fields, never duplicates; ``remove`` deletes by the same key,
    idempotently (the client never knows row ids); ``list`` returns the user's saves newest-first.
    """

    async def list(self, *, user_id: str | None) -> list[Bookmark]: ...

    async def save(self, *, user_id: str | None, bookmark: Bookmark) -> None: ...

    async def remove(
        self, *, user_id: str | None, kind: BookmarkKind, course_id: str, target_id: str
    ) -> None: ...

    async def delete_for_course(self, *, user_id: str | None, course_id: str) -> int:
        """Remove every save the user made in a course — the bookmarks arm of a full course
        delete. Returns the number of rows removed."""
        ...

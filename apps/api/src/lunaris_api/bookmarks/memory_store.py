from .bookmark import Bookmark, BookmarkKind


class InMemoryBookmarkStore:
    """The no-DB bookmark store (offline dev / hermetic tests): plain dicts keyed by user.

    ``None`` user_id is the single-user posture — all unauthenticated saves share one bucket,
    mirroring the progress store when auth is off. Process-lifetime only.
    """

    def __init__(self) -> None:
        self._bookmarks: dict[tuple[str | None, BookmarkKind, str, str], Bookmark] = {}

    async def list(self, *, user_id: str | None) -> list[Bookmark]:
        # Newest-first, with insertion order breaking timestamp ties (the activity-store lesson:
        # wall-clock alone can tie at coarse resolution).
        owned = [
            (index, bookmark)
            for index, ((owner, *_), bookmark) in enumerate(self._bookmarks.items())
            if owner == user_id
        ]
        owned.sort(key=lambda pair: (pair[1].saved_at, pair[0]), reverse=True)
        return [bookmark for _, bookmark in owned]

    async def save(self, *, user_id: str | None, bookmark: Bookmark) -> None:
        key = (user_id, bookmark.kind, bookmark.course_id, bookmark.target_id)
        # Pop first so a re-save moves to the END of insertion order — dict assignment alone
        # keeps the ORIGINAL slot, and list()'s tie-break would then misorder a refreshed save.
        self._bookmarks.pop(key, None)
        self._bookmarks[key] = bookmark

    async def remove(
        self, *, user_id: str | None, kind: BookmarkKind, course_id: str, target_id: str
    ) -> None:
        self._bookmarks.pop((user_id, kind, course_id, target_id), None)

    async def delete_for_course(self, *, user_id: str | None, course_id: str) -> int:
        doomed = [key for key in self._bookmarks if key[0] == user_id and key[2] == course_id]
        for key in doomed:
            del self._bookmarks[key]
        return len(doomed)

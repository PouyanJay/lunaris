import asyncio
import os
from datetime import datetime

from .bookmark import Bookmark, BookmarkKind
from .store_unavailable_error import BookmarkStoreUnavailableError

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
_TABLE = "bookmarks"
_COLUMNS = (
    "kind, course_id, target_id, course_title, title, lesson_id, snippet, concept_tier,"
    " trust_tier, credibility, note, saved_at"
)


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _bookmark_from_row(row: dict) -> Bookmark:
    return Bookmark(
        kind=row["kind"],
        course_id=row["course_id"],
        target_id=row["target_id"],
        course_title=row.get("course_title"),
        title=row.get("title"),
        lesson_id=row.get("lesson_id"),
        snippet=row.get("snippet"),
        concept_tier=row.get("concept_tier"),
        trust_tier=row.get("trust_tier"),
        credibility=row.get("credibility"),
        note=row.get("note"),
        saved_at=_parse_timestamp(row["saved_at"]),
    )


class SupabaseBookmarkStore:
    """The production bookmark store: Supabase Postgres, lazy service-role client.

    Mirrors SupabaseProgressStore: the service-role client bypasses RLS (this API-layer store
    scopes every query by the authenticated ``user_id``), built lazily on first use so
    construction needs no creds. The table is additionally owner-scoped by RLS, so a user-JWT
    client could only ever reach its own rows even if it queried directly. The synchronous
    supabase-py calls run off the event loop via ``asyncio.to_thread``.
    """

    def __init__(
        self,
        *,
        url_env: str = _URL_ENV,
        service_key_env: str = _SERVICE_KEY_ENV,
        client: object | None = None,
    ) -> None:
        self._url_env = url_env
        self._service_key_env = service_key_env
        # An injected client (tests) skips lazy construction; production leaves it None so the
        # service-role client is built from the environment on first use.
        self._client = client

    def _ensure_client(self) -> object:
        if self._client is None:
            from supabase import create_client

            url = os.environ.get(self._url_env)
            key = os.environ.get(self._service_key_env)
            if not url or not key:
                raise RuntimeError(
                    f"{self._url_env} / {self._service_key_env} not set; cannot store bookmarks"
                )
            self._client = create_client(url, key)
        return self._client

    @staticmethod
    def _require_user(user_id: str | None) -> str:
        # With Supabase configured, auth is configured — the API always resolves a real user.
        if user_id is None:
            raise RuntimeError("bookmarks require an authenticated user when Supabase is active")
        return user_id

    async def list(self, *, user_id: str | None) -> list[Bookmark]:
        owner = self._require_user(user_id)
        client = self._ensure_client()

        def _select() -> object:
            return (
                client.table(_TABLE)  # type: ignore[attr-defined]
                .select(_COLUMNS)
                .eq("user_id", owner)
                .order("saved_at", desc=True)
                .execute()
            )

        try:
            response = await asyncio.to_thread(_select)
        except Exception as exc:
            raise BookmarkStoreUnavailableError("bookmarks backend unavailable") from exc
        return [_bookmark_from_row(row) for row in response.data or []]  # type: ignore[attr-defined]

    async def save(self, *, user_id: str | None, bookmark: Bookmark) -> None:
        owner = self._require_user(user_id)
        client = self._ensure_client()
        row = {
            "user_id": owner,
            "kind": bookmark.kind,
            "course_id": bookmark.course_id,
            "target_id": bookmark.target_id,
            "course_title": bookmark.course_title,
            "title": bookmark.title,
            "lesson_id": bookmark.lesson_id,
            "snippet": bookmark.snippet,
            "concept_tier": bookmark.concept_tier,
            "trust_tier": bookmark.trust_tier,
            "credibility": bookmark.credibility,
            "note": bookmark.note,
            "saved_at": bookmark.saved_at.isoformat(),
        }

        def _upsert() -> object:
            return (
                client.table(_TABLE)  # type: ignore[attr-defined]
                .upsert(row, on_conflict="user_id,kind,course_id,target_id")
                .execute()
            )

        try:
            await asyncio.to_thread(_upsert)
        except Exception as exc:
            raise BookmarkStoreUnavailableError("bookmarks backend unavailable") from exc

    async def remove(
        self, *, user_id: str | None, kind: BookmarkKind, course_id: str, target_id: str
    ) -> None:
        owner = self._require_user(user_id)
        client = self._ensure_client()

        def _delete() -> object:
            return (
                client.table(_TABLE)  # type: ignore[attr-defined]
                .delete()
                .eq("user_id", owner)
                .eq("kind", kind)
                .eq("course_id", course_id)
                .eq("target_id", target_id)
                .execute()
            )

        try:
            await asyncio.to_thread(_delete)
        except Exception as exc:
            raise BookmarkStoreUnavailableError("bookmarks backend unavailable") from exc

    async def delete_for_course(self, *, user_id: str | None, course_id: str) -> int:
        """Remove every save the user made in a course (the bookmarks arm of a full course delete).
        Owner-scoped in the query (belt-and-braces with RLS); returns the rows removed."""
        owner = self._require_user(user_id)
        client = self._ensure_client()

        def _delete() -> object:
            return (
                client.table(_TABLE)  # type: ignore[attr-defined]
                .delete(count="exact")
                .eq("user_id", owner)
                .eq("course_id", course_id)
                .execute()
            )

        try:
            response = await asyncio.to_thread(_delete)
        except Exception as exc:
            raise BookmarkStoreUnavailableError("bookmarks backend unavailable") from exc
        return response.count or 0  # type: ignore[attr-defined]

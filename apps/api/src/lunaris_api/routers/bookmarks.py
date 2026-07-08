from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Response, status
from lunaris_runtime.logging import bind_request_id

from ..bookmarks import Bookmark, BookmarkKind, BookmarkStoreUnavailableError
from ..dependencies import BookmarkStoreDep, OptionalUserIdDep
from ..schemas import BookmarkRequest, BookmarkView

router = APIRouter(prefix="/api/bookmarks", tags=["bookmarks"])


def _bind() -> str:
    """Bind a fresh correlation id for the request and return it (for the X-Request-Id header)."""
    request_id = uuid4().hex
    bind_request_id(request_id)
    return request_id


def _view(bookmark: Bookmark) -> BookmarkView:
    return BookmarkView(
        kind=bookmark.kind,
        course_id=bookmark.course_id,
        target_id=bookmark.target_id,
        course_title=bookmark.course_title,
        title=bookmark.title,
        lesson_id=bookmark.lesson_id,
        snippet=bookmark.snippet,
        concept_tier=bookmark.concept_tier,
        trust_tier=bookmark.trust_tier,
        credibility=bookmark.credibility,
        note=bookmark.note,
        saved_at=bookmark.saved_at,
    )


_UNAVAILABLE = "Bookmarks are temporarily unavailable"


def _unavailable(request_id: str) -> HTTPException:
    """The recoverable-outage 503. Correlation must ride the exception explicitly — headers set
    on the injected Response are dropped when a handler raises."""
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=_UNAVAILABLE,
        headers={"X-Request-Id": request_id},
    )


@router.get("", response_model=list[BookmarkView])
async def list_bookmarks(
    store: BookmarkStoreDep,
    owner_id: OptionalUserIdDep,
    response: Response,
) -> list[BookmarkView]:
    """The caller's saved lessons/concepts/sources, newest-first. A bookmarks-backend outage is
    a recoverable 503 (kept inside the CORS middleware), never a raw 500."""
    request_id = _bind()
    response.headers["X-Request-Id"] = request_id
    try:
        bookmarks = await store.list(user_id=owner_id)
    except BookmarkStoreUnavailableError as exc:
        raise _unavailable(request_id) from exc
    return [_view(bookmark) for bookmark in bookmarks]


@router.put("", status_code=status.HTTP_204_NO_CONTENT)
async def put_bookmark(
    payload: BookmarkRequest,
    store: BookmarkStoreDep,
    owner_id: OptionalUserIdDep,
    response: Response,
) -> None:
    """Save a bookmark — an idempotent upsert on (kind, course, target): re-saving refreshes the
    display fields, never duplicates."""
    request_id = _bind()
    response.headers["X-Request-Id"] = request_id
    bookmark = Bookmark(
        kind=payload.kind,
        course_id=payload.course_id,
        target_id=payload.target_id,
        course_title=payload.course_title,
        title=payload.title,
        lesson_id=payload.lesson_id,
        snippet=payload.snippet,
        concept_tier=payload.concept_tier,
        trust_tier=payload.trust_tier,
        credibility=payload.credibility,
        note=payload.note,
        saved_at=datetime.now(UTC),
    )
    try:
        await store.save(user_id=owner_id, bookmark=bookmark)
    except BookmarkStoreUnavailableError as exc:
        raise _unavailable(request_id) from exc


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bookmark(
    store: BookmarkStoreDep,
    owner_id: OptionalUserIdDep,
    response: Response,
    kind: BookmarkKind,
    course_id: Annotated[str, Query(alias="courseId", min_length=1, max_length=100)],
    target_id: Annotated[str, Query(alias="targetId", min_length=1, max_length=300)],
) -> None:
    """Remove a bookmark by its natural key (idempotent — removing twice is fine). The client
    toggles from the affordance it saved at, so it knows the key, never the row id."""
    request_id = _bind()
    response.headers["X-Request-Id"] = request_id
    try:
        await store.remove(user_id=owner_id, kind=kind, course_id=course_id, target_id=target_id)
    except BookmarkStoreUnavailableError as exc:
        raise _unavailable(request_id) from exc

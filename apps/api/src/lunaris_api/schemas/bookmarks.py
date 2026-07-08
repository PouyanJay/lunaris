from datetime import datetime

from pydantic import Field

from ..bookmarks import BookmarkKind
from .base import CamelModel


class BookmarkView(CamelModel):
    """One saved lesson/concept/source, with the display fields captured at save time."""

    kind: BookmarkKind
    course_id: str
    target_id: str
    course_title: str | None = None
    title: str | None = None
    lesson_id: str | None = None
    snippet: str | None = None
    concept_tier: int | None = None
    trust_tier: str | None = None
    credibility: float | None = None
    note: str | None = None
    saved_at: datetime


class BookmarkRequest(CamelModel):
    """Save (idempotent upsert on the natural key). Bounds mirror the DB checks; display fields
    are captured client-side at save time (the screen must render without re-fetching courses)."""

    kind: BookmarkKind
    course_id: str = Field(min_length=1, max_length=100)
    target_id: str = Field(min_length=1, max_length=300)
    course_title: str | None = Field(default=None, min_length=1, max_length=300)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    lesson_id: str | None = Field(default=None, min_length=1, max_length=200)
    snippet: str | None = Field(default=None, min_length=1, max_length=2000)
    concept_tier: int | None = Field(default=None, ge=1, le=5)
    trust_tier: str | None = Field(default=None, min_length=1, max_length=40)
    credibility: float | None = Field(default=None, ge=0, le=1)
    note: str | None = Field(default=None, min_length=1, max_length=2000)

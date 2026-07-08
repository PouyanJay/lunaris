from dataclasses import dataclass
from datetime import datetime
from typing import Literal

# The kind vocabulary (kept in lockstep with the DB check): what a save points at.
BookmarkKind = Literal["lesson", "concept", "source"]


@dataclass(frozen=True)
class Bookmark:
    """One user save. Identity is the natural key (kind, course_id, target_id) per user —
    target_id is a lesson id, a KC id, or a citation id for sources (claims carry no server id;
    the claim text rides along as ``snippet``).

    Display fields are denormalized at save time so the bookmarks screen renders without
    re-fetching courses and survives a course rebuild; ``lesson_id`` lets a source bookmark
    deep-link back to its owning lesson.
    """

    kind: BookmarkKind
    course_id: str
    target_id: str
    course_title: str | None
    title: str | None
    lesson_id: str | None
    snippet: str | None
    concept_tier: int | None
    trust_tier: str | None
    credibility: float | None
    note: str | None
    saved_at: datetime

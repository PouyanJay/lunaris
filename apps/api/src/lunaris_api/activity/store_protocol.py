from datetime import datetime
from typing import Protocol

from .learning_event import LearningEvent


class IActivityStore(Protocol):
    """Per-user storage for learning telemetry (events + coarse study minutes).

    Every method is scoped to a ``user_id``; ``None`` is the unscoped single-user posture used
    when auth is unconfigured (offline dev — the in-memory backend). With auth on, the API always
    passes a real user id and the Supabase backend's rows are additionally owner-scoped by RLS.

    Contract: ``record_event`` appends one immutable telemetry fact; ``record_minute`` upserts one
    minute-aligned study bucket (idempotent — repeated heartbeats within the same minute are one
    row); ``events`` returns the user's history newest-first; ``minutes`` returns the user's
    bucket timestamps. Reads return full history — streak math needs every active day, and the
    single-tenant row volume stays small (events are click-frequency, minutes are one row per
    studied minute).
    """

    async def record_event(self, *, user_id: str | None, event: LearningEvent) -> None: ...

    async def record_minute(self, *, user_id: str | None, bucket_start: datetime) -> None: ...

    async def events(self, *, user_id: str | None) -> list[LearningEvent]: ...

    async def minutes(self, *, user_id: str | None) -> list[datetime]: ...

    async def delete_for_course(self, *, user_id: str | None, course_id: str) -> int:
        """Remove the user's per-course feed events for a course — the activity arm of a full
        course delete. ``study_minutes`` has no course dimension (coarse global buckets), so study
        time is intentionally left untouched. Returns the number of events removed."""
        ...

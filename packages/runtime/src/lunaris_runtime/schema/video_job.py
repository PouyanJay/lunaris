from datetime import datetime

from pydantic import Field

from .base import CourseModel
from .enums import VideoJobStatus, VideoKind


class VideoJob(CourseModel):
    """One explainer-video generation job — a row in the ``video_jobs`` queue.

    The job is both the queue entry the worker claims and the status record the reader polls
    (the hero slot renders straight off ``status``). ``id`` is the job_id (uuid4().hex) and the
    run-scope correlation id across queue → worker → storage → API logs. ``input_hash``
    fingerprints the generation inputs (staleness detection); ``contract_hash`` arrives once the
    pipeline has planned scene contracts (the regeneration cache key). ``config`` snapshots the
    user's video settings (length, voice) at enqueue time so a later settings change never
    silently rewrites an in-flight job. The lease fields (``claimed_at``/``claimed_by``/
    ``attempts``) belong to the claim protocol; ``created_at``/``updated_at`` are DB-owned.
    """

    id: str
    user_id: str
    course_id: str
    lesson_id: str | None = None  # required for kind=lesson, absent for course-level kinds
    kind: VideoKind
    status: VideoJobStatus = VideoJobStatus.QUEUED
    input_hash: str
    contract_hash: str | None = None
    config: dict[str, object] = Field(default_factory=dict)
    attempts: int = 0
    claimed_at: datetime | None = None
    claimed_by: str | None = None
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

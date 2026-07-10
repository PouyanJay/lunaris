from datetime import datetime

from pydantic import Field

from .base import CourseModel
from .enums import CoverJobStatus, CoverStylePreset


class CoverJob(CourseModel):
    """One course cover-image generation job — a row in the ``cover_jobs`` queue.

    The job is both the queue entry the worker claims and the status record the reader polls (the
    cover slot renders straight off ``status``). ``id`` is the job_id (uuid4().hex) and the
    run-scope correlation id across queue → worker → storage → API logs. There is exactly one cover
    per course, so — unlike ``VideoJob`` — there is no kind / lesson_id / contract_hash.
    ``input_hash`` fingerprints the generation inputs (staleness detection); ``style_preset`` and
    ``config`` snapshot the art-direction preset and model/quality at enqueue time so a later
    settings change never silently rewrites an in-flight job. The lease fields (``claimed_at`` /
    ``claimed_by`` / ``attempts``) belong to the claim protocol; ``created_at`` / ``updated_at`` are
    DB-owned.
    """

    id: str
    user_id: str
    course_id: str
    status: CoverJobStatus = CoverJobStatus.QUEUED
    style_preset: CoverStylePreset = CoverStylePreset.NOCTURNE
    input_hash: str
    config: dict[str, object] = Field(default_factory=dict)
    attempts: int = 0
    claimed_at: datetime | None = None
    claimed_by: str | None = None
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

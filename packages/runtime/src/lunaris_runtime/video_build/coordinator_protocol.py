from collections.abc import Mapping, Sequence
from typing import Protocol

from ..schema import CourseBrief, Module, VideoArtifact, VideoKind


class IVideoBuildCoordinator(Protocol):
    """The build's video lifecycle as the harness sees it — a thin port over the job queue.

    The author→verify→revise loop calls :meth:`enqueue_lesson` the moment a module clears
    verification (its lessons are final), and :meth:`enqueue_summary` / :meth:`enqueue_overview`
    fire once the curriculum is designed — so videos render while the rest of the build runs,
    blocking-but-overlapped (plan §0). Finalize then calls :meth:`collect` (lessons) and
    :meth:`collect_course_videos` (course-level) to await those jobs and fold each finished artifact
    into its lesson / the course's Overview section, degrading on failure. The implementation owns
    the owner, the queue, the storage, and the per-job config snapshot; the harness only knows what
    is ready, and tracks the returned job ids on the run draft. Absent (no coordinator in run scope)
    ⇒ no video jobs: the gate (operator flag ∧ keyed ∧ owner) is decided once by the composition
    root, never re-derived here.
    """

    async def enqueue_lesson(self, *, course_id: str, lesson_id: str) -> str | None:
        """Enqueue a lesson-video job; return its job id, or ``None`` if it could not be enqueued
        (enqueue is best-effort — a queue hiccup must never break the build). Idempotent within a
        build: the same lesson returns the same job id rather than a duplicate."""
        ...

    async def enqueue_summary(
        self, *, course_id: str, topic: str, modules: Sequence[Module]
    ) -> str | None:
        """Enqueue the course's SUMMARY trailer, grounded in the designed curriculum (V5). Same
        best-effort + per-build idempotence contract as :meth:`enqueue_lesson`. The grounding (topic
        + modules) is snapshotted onto the job so the worker grounds it without the unpersisted
        course (the course saves only at finalize)."""
        ...

    async def enqueue_overview(self, *, course_id: str, brief: CourseBrief) -> str | None:
        """Enqueue the course's OVERVIEW intro, grounded in the brief + researched standard (V5).
        Same best-effort + per-build idempotence contract; the brief is snapshotted onto the job."""
        ...

    async def collect(self, jobs_by_lesson: Mapping[str, str]) -> dict[str, VideoArtifact]:
        """Await every enqueued lesson job to a terminal state (bounded), returning ``{lesson_id:
        VideoArtifact}``. A READY job yields its finished artifact (provenance populated); a FAILED
        job, an unreadable artifact, or one still running past the timeout yields a FAILED
        retry-state artifact — degrade-on-failure, so a video never blocks the course (plan §0)."""
        ...

    async def collect_course_videos(
        self, jobs_by_kind: Mapping[VideoKind, str]
    ) -> dict[VideoKind, VideoArtifact]:
        """Await the course-level (summary/overview) jobs, returning ``{kind: VideoArtifact}`` with
        the same degrade-on-failure posture as :meth:`collect` — a degraded course video carries its
        own kind so the reader's Overview section shows the right retry state."""
        ...

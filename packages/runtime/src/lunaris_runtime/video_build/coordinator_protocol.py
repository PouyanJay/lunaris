from collections.abc import Mapping
from typing import Protocol

from ..schema import VideoArtifact


class IVideoBuildCoordinator(Protocol):
    """The build's video lifecycle as the harness sees it — a thin port over the job queue.

    The author→verify→revise loop calls :meth:`enqueue_lesson` the moment a module clears
    verification (its lessons are final), so a lesson's video renders while the rest of the build
    runs — blocking-but-overlapped (plan §0). Finalize then calls :meth:`collect` to await those
    jobs and fold each finished artifact into its lesson, degrading on failure. The implementation
    owns the owner, the queue, the storage, and the per-job config snapshot; the harness only knows
    *which* lesson is ready, and tracks the returned job id on the run draft. Absent (no coordinator
    in run scope) ⇒ no video jobs: the gate (operator flag ∧ keyed ∧ owner) is decided once by the
    composition root, never re-derived here.
    """

    async def enqueue_lesson(self, *, course_id: str, lesson_id: str) -> str | None:
        """Enqueue a lesson-video job; return its job id, or ``None`` if it could not be enqueued
        (enqueue is best-effort — a queue hiccup must never break the build). Idempotent within a
        build: the same lesson returns the same job id rather than a duplicate."""
        ...

    async def collect(self, jobs_by_lesson: Mapping[str, str]) -> dict[str, VideoArtifact]:
        """Await every enqueued job to a terminal state (bounded), returning ``{lesson_id:
        VideoArtifact}``. A READY job yields its finished artifact (provenance populated); a FAILED
        job, an unreadable artifact, or one still running past the timeout yields a FAILED
        retry-state artifact — degrade-on-failure, so a video never blocks the course (plan §0)."""
        ...

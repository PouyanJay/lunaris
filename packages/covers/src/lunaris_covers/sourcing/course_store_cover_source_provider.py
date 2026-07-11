import asyncio

import structlog
from lunaris_runtime.persistence import ICourseStore
from lunaris_runtime.schema import Course, CoverJob

from lunaris_covers.errors import CoverPipelineError
from lunaris_covers.models.cover_brief import CoverBrief

_logger = structlog.get_logger(__name__)

# How many concept labels the art director is handed. Enough to make the subject specific to the
# course; few enough that the brief stays a focal subject, not a cluttered checklist (the #1 slop
# tell the house style guards against).
_MAX_CONCEPT_LABELS = 6


class CourseStoreCoverSourceProvider:
    """Loads a cover job's ``Course`` from the store and distils it into a ``CoverBrief``.

    ``owner_id`` scopes the load to the job's owner — the Supabase store enforces it, the file store
    (single-user dev) ignores it. The brief is the topic, a handful of concept-graph labels (in
    topo order, so the most foundational concepts lead), and an audience note. A course that has
    been deleted between enqueue and render surfaces as a ``CoverPipelineError`` so the worker
    settles the job cleanly rather than crashing.
    """

    def __init__(self, store: ICourseStore) -> None:
        self._store = store

    async def load(self, job: CoverJob) -> CoverBrief:
        course = await asyncio.to_thread(self._load_course, job)
        labels = _concept_labels(course)
        _logger.info(
            "cover_source_provider.loaded",
            course_id=course.id,
            concept_count=len(labels),
            style=job.style_preset.value,
        )
        return CoverBrief(
            topic=course.topic,
            concept_labels=labels,
            audience=course.scope_note.strip() or f"learners studying {course.topic}",
            style_preset=job.style_preset,
        )

    def _load_course(self, job: CoverJob) -> Course:
        try:
            return self._store.load(job.course_id, owner_id=job.user_id)
        except FileNotFoundError as exc:
            raise CoverPipelineError(f"course {job.course_id} not found for cover job") from exc


def _concept_labels(course: Course) -> tuple[str, ...]:
    """The leading concept labels for the brief, in topo order (foundational concepts first).

    Falls back to node declaration order when the graph has no topo order (a pre-assembly course),
    and to an empty tuple when the course has no graph at all — the art director then designs from
    the topic alone. Blank labels are dropped so a stray empty KC never dilutes the brief.
    """
    by_id = {node.id: node.label for node in course.graph.nodes}
    ordered_ids = course.graph.topo_order or list(by_id)
    labels = [by_id[kc_id].strip() for kc_id in ordered_ids if by_id.get(kc_id, "").strip()]
    return tuple(labels[:_MAX_CONCEPT_LABELS])

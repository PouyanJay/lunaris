import asyncio

import structlog
from lunaris_live.graph import ConceptGraph
from lunaris_runtime.persistence import ICourseStore
from lunaris_runtime.schema.enums import CourseStatus

from .changed import CorpusChangedError
from .mapping_is_ready import mapping_is_ready
from .models.access_policy import CorpusAccessPolicy
from .normalize_course import normalize_course
from .not_ready import GraphNotReadyError
from .unavailable import CorpusUnavailableError


class StudioCorpusAccessGuard:
    """Fresh owner/source checks never mutate snapshots, graphs or learner state."""

    def __init__(self, courses: ICourseStore) -> None:
        self._courses = courses

    async def check(
        self,
        graph: ConceptGraph,
        *,
        owner_id: str | None,
        run_id: str,
        policy: CorpusAccessPolicy = CorpusAccessPolicy.TEACH,
    ) -> None:
        source = graph.corpus
        if source is None:
            return
        if not owner_id:
            raise CorpusUnavailableError
        try:
            course = await asyncio.to_thread(
                self._courses.load, source.course_id, owner_id=owner_id
            )
        except FileNotFoundError as exc:
            raise CorpusUnavailableError from exc
        if course.id != source.course_id or course.status != CourseStatus.PUBLISHED:
            raise CorpusUnavailableError
        try:
            current = await asyncio.to_thread(normalize_course, course, run_id=run_id)
        except ValueError as exc:
            raise CorpusChangedError from exc
        if (
            current.source.digest != source.digest
            or current.source.adapter_version != source.adapter_version
        ):
            raise CorpusChangedError
        if policy is not CorpusAccessPolicy.INSPECT:
            original = current.model_copy(update={"source": source})
            if source.status != "verified" or not mapping_is_ready(graph, original):
                raise GraphNotReadyError
        structlog.get_logger().info(
            "live.corpus.access_checked", run_id=run_id, graph_id=graph.graph_id
        )

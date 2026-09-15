import asyncio

import structlog
from lunaris_live.corpus.protocols.snapshot_store import ICorpusSnapshotStore
from lunaris_live.corpus.schemas.reference import CorpusReference
from lunaris_live.corpus.schemas.snapshot import CorpusSnapshot
from lunaris_runtime.persistence import ICourseStore
from lunaris_runtime.schema.enums import CourseStatus

from .invalid import CorpusInvalidError
from .normalize_course import normalize_course
from .unavailable import CorpusUnavailableError

logger = structlog.get_logger()


class StudioCorpusResolver:
    """Recheck source access on every resolve; immutable cached content never grants access."""

    def __init__(self, courses: ICourseStore, snapshots: ICorpusSnapshotStore) -> None:
        self._courses = courses
        self._snapshots = snapshots

    async def resolve(
        self, reference: CorpusReference, *, owner_id: str, run_id: str
    ) -> CorpusSnapshot:
        if not owner_id:
            raise CorpusUnavailableError
        try:
            course = await asyncio.to_thread(
                self._courses.load, reference.course_id, owner_id=owner_id
            )
        except FileNotFoundError as exc:
            raise CorpusUnavailableError from exc
        if course.id != reference.course_id or course.status != CourseStatus.PUBLISHED:
            raise CorpusUnavailableError
        try:
            snapshot = normalize_course(course, run_id=run_id)
        except ValueError as exc:
            raise CorpusInvalidError from exc
        persisted = await asyncio.to_thread(self._snapshots.save, snapshot, owner_id=owner_id)
        logger.info(
            "live.corpus.resolved",
            run_id=run_id,
            course_id=reference.course_id,
            digest=persisted.source.digest,
            sections=len(persisted.sections),
        )
        return persisted.model_copy(
            update={"source": persisted.source.model_copy(update={"run_id": run_id})}
        )

import structlog
from lunaris_graph import PrerequisiteGraphBuilder
from lunaris_runtime.logging import bind_run_id
from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.schema import Course, CourseStatus

from .subagents.concept_extractor import IConceptExtractor

logger = structlog.get_logger()


class Orchestrator:
    """Owns the plan and the course-object; delegates the work.

    Stage 2 pathway: topic → concept extraction (KCs) → deterministic prerequisite
    graph (the Failure-A moat) written onto the course-object. Objectives, authoring,
    verification, and visuals attach in later stages.
    """

    def __init__(
        self,
        store: CourseStore,
        extractor: IConceptExtractor,
        builder: PrerequisiteGraphBuilder,
    ) -> None:
        self._store = store
        self._extractor = extractor
        self._builder = builder

    async def run(self, topic: str, *, course_id: str, run_id: str) -> Course:
        bind_run_id(run_id)
        logger.info("course_run_started", topic=topic, course_id=course_id)

        course = Course(id=course_id, topic=topic)

        course.status = CourseStatus.MAPPING
        extraction = await self._extractor.extract(topic)
        course.goal_concept = extraction.goal_id

        course.status = CourseStatus.SEQUENCING
        course.graph = await self._builder.build(
            extraction.kcs,
            frontier=course.learner.frontier,  # MVP: empty (assume novice)
            goal=extraction.goal_id,
        )

        self._store.save(course)
        logger.info(
            "course_run_completed",
            course_id=course_id,
            status=course.status.value,
            kc_count=len(course.graph.nodes),
            edge_count=len(course.graph.edges),
        )
        return course

import structlog
from lunaris_graph import PrerequisiteGraphBuilder
from lunaris_grounding import Verifier
from lunaris_runtime.logging import bind_run_id
from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.schema import Course, CourseStatus

from .critic import ICritic, MinimalCritic
from .lesson_claims import iter_claims
from .subagents.concept_extractor import IConceptExtractor
from .subagents.curriculum_architect import CurriculumAssembler, ICurriculumArchitect
from .subagents.module_author import IModuleAuthor, LessonAssembler
from .subagents.visual_agent import VisualEngine

logger = structlog.get_logger()


class Orchestrator:
    """Owns the plan and the course-object; delegates the work.

    Pathway: topic → concept extraction (KCs) → deterministic prerequisite graph
    (Failure-A moat) → curriculum architect (backward design) → module authoring
    (Merrill lessons) → visual engine (validated diagrams, optional) → verifier
    (Failure-B moat, claim-level publish gate) → pedagogy critic → publish.
    """

    def __init__(
        self,
        store: CourseStore,
        extractor: IConceptExtractor,
        builder: PrerequisiteGraphBuilder,
        architect: ICurriculumArchitect,
        author: IModuleAuthor,
        verifier: Verifier,
        critic: ICritic | None = None,
        visual_engine: VisualEngine | None = None,
        curriculum_assembler: CurriculumAssembler | None = None,
        lesson_assembler: LessonAssembler | None = None,
    ) -> None:
        self._store = store
        self._extractor = extractor
        self._builder = builder
        self._architect = architect
        self._author = author
        self._verifier = verifier
        self._critic = critic or MinimalCritic()
        self._visual_engine = visual_engine
        self._curriculum_assembler = curriculum_assembler or CurriculumAssembler()
        self._lesson_assembler = lesson_assembler or LessonAssembler()

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

        plan = await self._architect.design(course.graph)
        course.modules = self._curriculum_assembler.assemble(plan, course.graph)

        course.status = CourseStatus.AUTHORING
        for module in course.modules:
            draft = await self._author.author(module)
            module.lessons = [self._lesson_assembler.assemble(draft, lesson_id=f"{module.id}-l0")]

        if self._visual_engine is not None:
            await self._visual_engine.illustrate(course)

        course.status = CourseStatus.VERIFYING
        all_lessons = [lesson for module in course.modules for lesson in module.lessons]
        claims = list(iter_claims(all_lessons))
        citations = await self._verifier.verify(claims, risk_tier=course.risk.tier)
        course.provenance = citations

        course.status = CourseStatus.REVIEW
        issues = self._critic.review(course)
        if issues:
            logger.warning(
                "critic_flagged", course_id=course_id, issue_count=len(issues), issues=issues
            )
        else:
            course.status = CourseStatus.PUBLISHED

        self._store.save(course)
        logger.info(
            "course_run_completed",
            course_id=course_id,
            status=course.status.value,
            kc_count=len(course.graph.nodes),
            module_count=len(course.modules),
            claim_count=len(claims),
            citation_count=len(citations),
            critic_issues=len(issues),
        )
        return course

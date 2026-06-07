import asyncio

import structlog
from lunaris_graph import PrerequisiteGraphBuilder
from lunaris_grounding import Verifier
from lunaris_runtime.logging import bind_run_id
from lunaris_runtime.persistence import ICourseStore
from lunaris_runtime.schema import (
    Citation,
    Clarification,
    Course,
    CourseStatus,
    DiscoveryDepth,
    Lesson,
    Module,
    ProgressEvent,
    ProgressStage,
    VerifierStatus,
)

from .critic import ICritic, MinimalCritic
from .lesson_claims import iter_claims
from .progress import IAgentSink, IProgressSink, NoOpProgressSink
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
        store: ICourseStore,
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

    async def run(
        self,
        topic: str,
        *,
        course_id: str,
        run_id: str,
        progress: IProgressSink | None = None,
        agent: IAgentSink | None = None,
        clarification: Clarification | None = None,
        discovery_depth: DiscoveryDepth = DiscoveryDepth.STANDARD,
    ) -> Course:
        # All three are part of the CoursePipeline contract but unused here: the legacy single-shot
        # orchestrator emits only coarse stages, has no brief to calibrate, and does no discovery.
        _ = agent, clarification, discovery_depth
        bind_run_id(run_id)
        logger.info("course_run_started", topic=topic, course_id=course_id)

        # Progress events mirror the structlog stage trail but are streamable. The sink
        # defaults to a no-op, so batch callers need no wiring. The run-local `emit`
        # closure stamps each event with a monotonic ordinal so the client can order
        # them without a clock; keeping the counter local keeps runs independent.
        sink = progress or NoOpProgressSink()
        sequence = 0

        async def emit(stage: ProgressStage, label: str, **counts: object) -> None:
            nonlocal sequence
            await sink.emit(
                ProgressEvent(stage=stage, label=label, run_id=run_id, sequence=sequence, **counts)
            )
            sequence += 1

        course = Course(id=course_id, topic=topic)
        await emit(ProgressStage.RUN_STARTED, f"Building a course for “{topic}”")

        course.status = CourseStatus.MAPPING
        extraction = await self._extractor.extract(topic)
        course.goal_concept = extraction.goal_id
        await emit(
            ProgressStage.CONCEPTS_EXTRACTED,
            f"Extracted {len(extraction.kcs)} concepts",
            kc_count=len(extraction.kcs),
        )

        course.status = CourseStatus.SEQUENCING
        course.graph = await self._builder.build(
            extraction.kcs,
            frontier=course.learner.frontier,  # MVP: empty (assume novice)
            goal=extraction.goal_id,
        )
        await emit(
            ProgressStage.GRAPH_BUILT,
            f"Built prerequisite graph: {len(course.graph.nodes)} concepts, "
            f"{len(course.graph.edges)} edges",
            kc_count=len(course.graph.nodes),
            edge_count=len(course.graph.edges),
        )

        plan = await self._architect.design(course.graph)
        course.modules = self._curriculum_assembler.assemble(plan, course.graph)
        await emit(
            ProgressStage.CURRICULUM_DESIGNED,
            f"Designed curriculum: {len(course.modules)} modules",
            module_count=len(course.modules),
        )

        course.status = CourseStatus.AUTHORING
        for module in course.modules:
            draft = await self._author.author(module)
            module.lessons = [self._lesson_assembler.assemble(draft, lesson_id=f"{module.id}-l0")]
            await emit(
                ProgressStage.MODULE_AUTHORED,
                f"Authored lesson: {module.title}",
                module_id=module.id,
            )

        if self._visual_engine is not None:
            await self._visual_engine.illustrate(course)

        course.status = CourseStatus.VERIFYING
        all_lessons = [lesson for module in course.modules for lesson in module.lessons]
        claims = list(iter_claims(all_lessons))
        citations = await self._verifier.verify(claims, risk_tier=course.risk.tier)
        course.provenance = citations
        supported = sum(1 for c in claims if c.verifier_status is VerifierStatus.SUPPORTED)
        await emit(
            ProgressStage.CLAIMS_VERIFIED,
            f"Verified {len(claims)} claims: {supported} supported, {len(claims) - supported} cut",
            claims_total=len(claims),
            claims_supported=supported,
            claims_cut=len(claims) - supported,
        )

        course.status = CourseStatus.REVIEW
        issues = self._critic.review(course)
        if issues:
            logger.warning(
                "critic_flagged", course_id=course_id, issue_count=len(issues), issues=issues
            )
        else:
            course.status = CourseStatus.PUBLISHED

        # Off-load the (possibly network-backed) save so the event loop isn't blocked during the
        # write — parity with the harness finalize_course tool.
        await asyncio.to_thread(self._store.save, course)
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
        await emit(
            ProgressStage.RUN_COMPLETED,
            "Published" if course.status is CourseStatus.PUBLISHED else "Needs review",
            status=course.status,
        )
        return course

    async def regenerate_lesson(
        self, course_id: str, lesson_id: str, *, run_id: str
    ) -> Course | None:
        """Re-author a single lesson of an existing course in place: re-run its module's author,
        re-illustrate it, re-verify its claims, recompute the publish status, persist, and return
        the updated course. Returns ``None`` if the course or lesson is unknown.
        """
        bind_run_id(run_id)
        try:
            # Off-load the (possibly network-backed) load so the event loop isn't blocked.
            course = await asyncio.to_thread(self._store.load, course_id)
        except FileNotFoundError:
            return None

        located = self._locate_lesson(course, lesson_id)
        if located is None:
            logger.warning("regenerate_lesson_not_found", course_id=course_id, lesson_id=lesson_id)
            return None
        module, _ = located

        draft = await self._author.author(module)
        lesson = self._lesson_assembler.assemble(draft, lesson_id=lesson_id)
        module.lessons = [
            lesson if existing.id == lesson_id else existing for existing in module.lessons
        ]

        if self._visual_engine is not None:
            await self._visual_engine.illustrate_lesson(module.title, lesson)

        claims = list(iter_claims([lesson]))
        citations = await self._verifier.verify(claims, risk_tier=course.risk.tier)
        course.provenance = self._merge_provenance(course.provenance, citations)

        course.status = CourseStatus.REVIEW
        issues = self._critic.review(course)
        if issues:
            logger.warning(
                "critic_flagged_on_regenerate",
                course_id=course_id,
                lesson_id=lesson_id,
                issue_count=len(issues),
            )
        else:
            course.status = CourseStatus.PUBLISHED

        # Off-load the (possibly network-backed) save so the event loop isn't blocked during the
        # write — parity with the harness finalize_course tool.
        await asyncio.to_thread(self._store.save, course)
        logger.info(
            "lesson_regenerated",
            course_id=course_id,
            lesson_id=lesson_id,
            status=course.status.value,
        )
        return course

    @staticmethod
    def _locate_lesson(course: Course, lesson_id: str) -> tuple[Module, Lesson] | None:
        for module in course.modules:
            for lesson in module.lessons:
                if lesson.id == lesson_id:
                    return module, lesson
        return None

    @staticmethod
    def _merge_provenance(existing: list[Citation], regenerated: list[Citation]) -> list[Citation]:
        """Merge re-verified citations into the course provenance, keyed by id (newest wins)."""
        by_id = {citation.id: citation for citation in existing}
        for citation in regenerated:
            by_id[citation.id] = citation
        return list(by_id.values())

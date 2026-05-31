"""``AgentCourseBuilder`` — the agent-pipeline replacement for ``Orchestrator``.

Exposes the SAME contract the API's ``CourseService`` already calls
(``run(topic, *, course_id, run_id, progress=None) -> Course``), so the new ``agent`` pipeline
drops in beside ``live``/``stub`` with no HTTP-layer changes. Each run builds a fresh
:class:`CourseDraft`, a fresh set of draft-bound tools, and a fresh module-author subagent (the
author→verify→revise loop), then drives the REAL deep-agent harness: the model plans, calls the
deterministic moat tools, and DELEGATES lesson authoring to the subagent via the ``task`` tool. The
moats + ``finalize_course`` guarantee the result; the model is injected — a real Claude id (live) or
a scripted fake (the no-key CI path).
"""

import structlog
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from lunaris_graph import PrerequisiteGraphBuilder
from lunaris_grounding import Verifier
from lunaris_runtime.logging import bind_run_id, clear_correlation
from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.schema import Course, ProgressStage, RiskTier

from ..critic import ICritic, MinimalCritic
from ..progress import IProgressSink
from ..subagents.concept_extractor import IConceptExtractor
from ..subagents.curriculum_architect import ICurriculumArchitect
from .agent import build_course_agent
from .authoring import ILessonReviser, build_authoring_subgraph
from .draft import CourseDraft
from .progress_reporter import ProgressReporter
from .tools import (
    make_design_curriculum_tool,
    make_extract_concepts_tool,
    make_finalize_course_tool,
    make_prerequisite_graph_tool,
)

logger = structlog.get_logger()

_AUTHOR_SUBAGENT = "module-author"
_AUTHOR_SUBAGENT_DESCRIPTION = (
    "Authors and verifies the Merrill lessons for every designed module: writes each lesson, "
    "grounds every factual claim against the evidence corpus, and revises until claims are "
    "supported — cutting any that cannot be grounded. Call once, after design_curriculum and "
    "before finalize_course."
)

_BUILD_INSTRUCTION = (
    "Build a complete, verified course on the topic: {topic}. Extract the concepts, order them "
    "with the prerequisite-graph tool, design the curriculum, then delegate lesson authoring to "
    "the module-author subagent (it authors, verifies, and revises the lessons). Finally, finalize "
    "the course."
)


class AgentCourseBuilder:
    """Composes a deep agent over the course-build tools + the authoring subagent, and runs it."""

    def __init__(
        self,
        model: str | BaseChatModel,
        store: CourseStore,
        *,
        extractor: IConceptExtractor,
        builder: PrerequisiteGraphBuilder,
        architect: ICurriculumArchitect,
        reviser: ILessonReviser,
        verifier: Verifier,
        critic: ICritic | None = None,
        risk_tier: RiskTier = RiskTier.LOW,
    ) -> None:
        self._model = model
        self._store = store
        self._extractor = extractor
        self._builder = builder
        self._architect = architect
        self._reviser = reviser
        self._verifier = verifier
        self._critic = critic or MinimalCritic()
        self._risk_tier = risk_tier

    async def run(
        self,
        topic: str,
        *,
        course_id: str,
        run_id: str,
        progress: IProgressSink | None = None,
    ) -> Course:
        # ``run_id`` is bound for the whole run and cleared in ``finally`` so it never leaks
        # into a later run sharing the event loop (the API reuses it across requests).
        bind_run_id(run_id)
        try:
            logger.info("agent_course_run_started", topic=topic, course_id=course_id)
            draft = CourseDraft(
                topic=topic, course_id=course_id, run_id=run_id, risk_tier=self._risk_tier
            )
            # Stream stage-boundary progress through the injected sink (no-op for batch callers);
            # the draft-bound tools + authoring loop emit onto draft.progress as they run.
            if progress is not None:
                draft.progress = ProgressReporter(run_id, progress)
            await draft.progress.emit(ProgressStage.RUN_STARTED, f"Building a course for “{topic}”")
            agent = build_course_agent(
                self._model,
                self._make_tools(draft),
                subagents=[self._make_author_subagent(draft)],
            )
            await agent.ainvoke(
                {"messages": [HumanMessage(content=_BUILD_INSTRUCTION.format(topic=topic))]}
            )
            return self._finished_course(draft, course_id)
        finally:
            clear_correlation()

    def _make_tools(self, draft: CourseDraft) -> list[BaseTool]:
        """The draft-bound capability tools the agent plans over (one fresh set per run).

        Lesson authoring + verification are NOT here — they are delegated to the module-author
        subagent (the author→verify→revise loop), so the agent reasons about *when* to author and
        the loop owns *how*.
        """
        return [
            make_extract_concepts_tool(self._extractor, draft),
            make_prerequisite_graph_tool(self._builder, draft),
            make_design_curriculum_tool(self._architect, draft),
            make_finalize_course_tool(self._critic, self._store, draft),
        ]

    def _make_author_subagent(self, draft: CourseDraft) -> dict[str, object]:
        """The module-author subagent: the author→verify→revise loop, closed over this run's draft.

        Registered as a Deep Agents ``CompiledSubAgent`` (a ``runnable`` graph). The main agent
        delegates with a narrative briefing via the ``task`` tool; the loop keys off the shared
        draft (the curriculum it must author) and writes the typed lessons + provenance back onto
        it, then returns a one-message report to the main agent.
        """
        return {
            "name": _AUTHOR_SUBAGENT,
            "description": _AUTHOR_SUBAGENT_DESCRIPTION,
            "runnable": build_authoring_subgraph(self._reviser, self._verifier, draft),
        }

    def _finished_course(self, draft: CourseDraft, course_id: str) -> Course:
        """Return the finalized course, or fail loudly if the agent never finalized one."""
        if draft.course is None:
            logger.error("agent_course_run_unfinalized", course_id=course_id)
            raise RuntimeError("agent finished without finalizing a course")
        logger.info(
            "agent_course_run_completed",
            course_id=course_id,
            status=draft.course.status.value,
            module_count=len(draft.course.modules),
        )
        return draft.course

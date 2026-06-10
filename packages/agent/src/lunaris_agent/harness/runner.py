"""``AgentCourseBuilder`` — the agent-pipeline replacement for ``Orchestrator``.

Exposes the SAME contract the API's ``CourseService`` calls
(``run(topic, *, course_id, run_id, progress=None, agent=None) -> Course``), so the ``agent``
pipeline drops in beside ``live``/``stub`` with no HTTP-layer changes. Each run builds a fresh
:class:`CourseDraft`, a fresh set of draft-bound tools, and a fresh module-author subagent (the
author→verify→revise loop), then drives the REAL deep-agent harness: the model plans, calls the
deterministic moat tools, and DELEGATES lesson authoring to the subagent via the ``task`` tool. The
moats + ``finalize_course`` guarantee the result; the model is injected — a real Claude id (live) or
a scripted fake (the no-key CI path).

``progress`` carries coarse pipeline stages; ``agent`` carries the fine-grained transcript feed
(reasoning / tool calls / todos). Both default to a no-op sink, so batch callers need no wiring.
"""

import structlog
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from lunaris_graph import PrerequisiteGraphBuilder
from lunaris_grounding import Verifier
from lunaris_runtime.logging import bind_run_id, clear_correlation
from lunaris_runtime.persistence import ICourseStore
from lunaris_runtime.schema import Clarification, Course, DiscoveryDepth, ProgressStage, RiskTier

from ..coverage_critic import ICoverageCritic, StubCoverageCritic
from ..critic import ICritic, MinimalCritic
from ..progress import IAgentSink, IProgressSink
from ..subagents.concept_extractor import IConceptExtractor
from ..subagents.curriculum_architect import ICurriculumArchitect
from ..subagents.goal_interpreter import IGoalInterpreter
from ..subagents.learner_profiler import ILearnerProfiler
from ..subagents.resource_curator import IResourceCurator
from ..subagents.scope_polisher import IScopePolisher
from ..subagents.standard_researcher import IStandardResearcher
from ..subagents.visual_agent import VisualEngine
from .agent import build_course_agent
from .agent_reporter import AgentReporter
from .authoring import ILessonReviser, build_authoring_subgraph
from .discovery import IGroundingDiscoverer
from .draft import CourseDraft
from .event_tap import stream_course_build
from .progress_reporter import ProgressReporter
from .seeding import IGroundingSeeder
from .stage_cursor import StageCursor
from .tools import (
    make_curate_resources_tool,
    make_design_curriculum_tool,
    make_discover_grounding_tool,
    make_extract_concepts_tool,
    make_finalize_course_tool,
    make_interpret_request_tool,
    make_model_learner_tool,
    make_prerequisite_graph_tool,
    make_research_standard_tool,
    make_seed_grounding_tool,
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
    "Build a complete, verified course for the request: {topic}. First call interpret_request to "
    "interpret the request into a structured brief (a goal for a learner at a level). Then call "
    "research_standard to ground the brief's target standard in its real competencies. Then call "
    "model_learner to infer what the learner already knows (the frontier to skip). Then extract "
    "the concepts, order them with the prerequisite-graph tool, design the curriculum, then call "
    "seed_grounding to seed the evidence corpus from the sources research already fetched, then "
    "discover_grounding to find any further evidence the claims are verified against. Then "
    "delegate lesson authoring to the module-author subagent (it authors, verifies, and revises "
    "the lessons). Then call curate_resources to attach vetted external learning resources to each "
    "lesson. Finally, finalize the course."
)

# The briefing handed to the author→verify→revise subagent on the scripted (keyless) path — the
# narrative the ``task`` tool would otherwise carry. The subagent keys off the draft's curriculum.
_SCRIPTED_AUTHOR_BRIEFING = (
    "Author and verify the Merrill lesson for every designed module: write each lesson, ground "
    "every factual claim against the evidence corpus, and revise until claims are supported."
)

# The fixed tool order for the keyless (scripted) path — the spine ``_BUILD_INSTRUCTION`` asks the
# agent to follow, split around the authoring subagent (a subagent, not a tool, run in the middle).
# A test pins these against ``_make_tools`` so a tool added there but omitted here fails a test,
# rather than being silently skipped on a keyless build.
_SCRIPTED_PRE_AUTHOR_TOOLS: tuple[str, ...] = (
    "interpret_request",
    "research_standard",
    "model_learner",
    "extract_concepts",
    "build_prerequisite_graph",
    "design_curriculum",
    "seed_grounding",
    "discover_grounding",
)
_SCRIPTED_POST_AUTHOR_TOOLS: tuple[str, ...] = ("curate_resources", "finalize_course")
# Every build tool, in order — the union must equal the names ``_make_tools`` produces.
SCRIPTED_TOOL_SEQUENCE: tuple[str, ...] = _SCRIPTED_PRE_AUTHOR_TOOLS + _SCRIPTED_POST_AUTHOR_TOOLS


class AgentCourseBuilder:
    """Composes a deep agent over the course-build tools + the authoring subagent, and runs it."""

    def __init__(
        self,
        model: str | BaseChatModel,
        store: ICourseStore,
        *,
        interpreter: IGoalInterpreter,
        profiler: ILearnerProfiler,
        researcher: IStandardResearcher,
        extractor: IConceptExtractor,
        builder: PrerequisiteGraphBuilder,
        architect: ICurriculumArchitect,
        reviser: ILessonReviser,
        curator: IResourceCurator,
        seeder: IGroundingSeeder,
        discoverer: IGroundingDiscoverer,
        verifier: Verifier,
        critic: ICritic | None = None,
        coverage_critic: ICoverageCritic | None = None,
        visual_engine: VisualEngine | None = None,
        scope_polisher: IScopePolisher | None = None,
        risk_tier: RiskTier = RiskTier.LOW,
        stream_tokens: bool = False,
        scripted: bool = False,
    ) -> None:
        self._model = model
        self._store = store
        self._interpreter = interpreter
        self._profiler = profiler
        self._researcher = researcher
        self._extractor = extractor
        self._builder = builder
        self._architect = architect
        self._reviser = reviser
        self._curator = curator
        self._seeder = seeder
        self._discoverer = discoverer
        self._verifier = verifier
        self._critic = critic or MinimalCritic()
        # The coverage gate (CQ Phase 4.2) always runs — the deterministic fail-safe / LLM judge is
        # wired by the composition root; this default keeps the offline path clean (no gap) so a
        # test that isn't exercising coverage builds a course unchanged.
        self._coverage_critic = coverage_critic or StubCoverageCritic()
        self._visual_engine = visual_engine
        # The optional key-gated scope-band wording polish (CQ Phase 3.1); None → the deterministic
        # band ships unchanged (the no-key path), so the offline suite stays byte-for-byte stable.
        self._scope_polisher = scope_polisher
        self._risk_tier = risk_tier
        # Token-by-token reasoning streaming: enabled only for a real streaming model (the live
        # composition root sets it). The scripted no-key model keeps the deterministic ``updates``
        # path, so the offline suite stays stable.
        self._stream_tokens = stream_tokens
        # Scripted (keyless) mode: drive the build tools in a fixed, code-enforced order instead of
        # letting the model plan — a small local model can't reliably orchestrate the multi-tool
        # build (it called finalize first and crashed the run). Same tools/subagent/features; only
        # the autonomous planner is bypassed. Set by the composition root on the no-Anthropic-key
        # signal, so a keyed build keeps the full agent harness, untouched.
        self._scripted = scripted

    @property
    def stream_tokens(self) -> bool:
        """Whether this builder streams the agent's reasoning token-by-token (live path only)."""
        return self._stream_tokens

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
        # ``run_id`` is bound for the whole run and cleared in ``finally`` so it never leaks
        # into a later run sharing the event loop (the API reuses it across requests).
        bind_run_id(run_id)
        try:
            logger.info("agent_course_run_started", topic=topic, course_id=course_id)
            # The learner's opt-in confirm answers (P7.5) ride on the draft: the interpret_request
            # stage folds them onto the inferred brief. None (the default / skipped clarifier)
            # leaves the interpreter's inference untouched.
            draft = CourseDraft(
                topic=topic,
                course_id=course_id,
                run_id=run_id,
                risk_tier=self._risk_tier,
                clarification=clarification,
                discovery_depth=discovery_depth,
            )
            # One stage cursor per run, shared by both reporters: the ProgressReporter advances
            # it at each stage boundary, and the AgentReporter stamps every fine event's `stage`
            # from it, so the timeline buckets reasoning/tool beats under the active phase.
            cursor = StageCursor()
            # Stream stage-boundary progress through the injected sink (no-op for batch callers);
            # the draft-bound tools + authoring loop emit onto draft.progress as they run.
            if progress is not None:
                draft.progress = ProgressReporter(run_id, progress, cursor=cursor)
            # The fine-grained transcript feed (reasoning / tool calls / todos): tap the deep
            # agent's own LangGraph event stream and translate it onto the agent channel
            # (sink → SSE → web transcript). This drives the graph to completion exactly as
            # ``ainvoke`` would; the finalized course is read from the draft afterward.
            # The cursor is advanced only by draft.progress (above); a batch caller with
            # progress=None never advances it, so every agent event correctly emits stage=None.
            agent_reporter = AgentReporter(run_id, agent, cursor=cursor)
            # Share it with the draft so the authoring subagent emits its per-module beats on the
            # SAME channel (one sink + sequence) — the tap can't see inside the subagent.
            draft.agent = agent_reporter
            await draft.progress.emit(ProgressStage.RUN_STARTED, f"Building a course for “{topic}”")
            if self._scripted:
                # Keyless: the code drives the tool order; the local model only does each step's
                # generation (which it can), never the planning (which it can't).
                await self._run_scripted(draft, topic)
            else:
                deep_agent = build_course_agent(
                    self._model,
                    self._make_tools(draft),
                    subagents=[self._make_author_subagent(draft)],
                )
                await stream_course_build(
                    deep_agent,
                    {"messages": [HumanMessage(content=_BUILD_INSTRUCTION.format(topic=topic))]},
                    agent_reporter,
                    stream_tokens=self._stream_tokens,
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
            make_interpret_request_tool(self._interpreter, draft),
            make_research_standard_tool(self._researcher, draft),
            make_model_learner_tool(self._profiler, draft),
            make_extract_concepts_tool(self._extractor, draft),
            make_prerequisite_graph_tool(self._builder, draft),
            make_design_curriculum_tool(self._architect, draft),
            make_seed_grounding_tool(self._seeder, draft),
            make_discover_grounding_tool(self._discoverer, draft),
            make_curate_resources_tool(self._curator, draft),
            make_finalize_course_tool(
                self._critic,
                self._store,
                draft,
                visual_engine=self._visual_engine,
                scope_polisher=self._scope_polisher,
                coverage_critic=self._coverage_critic,
            ),
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

    async def _run_scripted(self, draft: CourseDraft, topic: str) -> None:
        """Drive the build tools in a fixed, code-enforced order — the keyless (Draft) path.

        This is the same spine ``_BUILD_INSTRUCTION`` asks the agent to follow, but the CODE owns
        the order so a weak local model never has to plan it (the failure that crashed the run).
        Each tool reads/writes the shared ``draft`` exactly as on the agent path, the author→verify→
        revise subagent is invoked directly instead of via the ``task`` tool, and every tool still
        emits its ``ProgressStage`` onto ``draft.progress`` — so the build timeline advances and all
        grounding/relevance/coverage features run, unchanged. Only the autonomous planner is gone.
        """
        tools = {tool.name: tool for tool in self._make_tools(draft)}
        # The two draft-bound tools that take the topic; the rest read the draft (called with {}).
        topic_args: dict[str, dict[str, object]] = {
            "interpret_request": {"request": topic},
            "extract_concepts": {"topic": topic},
        }

        async def step(name: str) -> None:
            await tools[name].ainvoke(topic_args.get(name, {}))

        for name in _SCRIPTED_PRE_AUTHOR_TOOLS:
            await step(name)
        # Author + verify + revise every module's lesson (the subagent loop, run directly). It keys
        # off the draft's designed curriculum and writes the typed lessons + provenance back to it.
        author = build_authoring_subgraph(self._reviser, self._verifier, draft)
        await author.ainvoke({"messages": [HumanMessage(content=_SCRIPTED_AUTHOR_BRIEFING)]})
        for name in _SCRIPTED_POST_AUTHOR_TOOLS:
            await step(name)

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

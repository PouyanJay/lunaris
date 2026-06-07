"""CQ Phase 2 — T0 walking skeleton: the query-translator seam + per-module modality threading.

Proves the new path is wired end-to-end with trivial behavior, BEFORE the LLM translator (T1):
- the curator plans its searches through an injected ``IQueryTranslator`` (not a hardcoded
  template),
- the ``curate_resources`` tool resolves each module's representative ``Modality`` from the graph
  and threads it into ``curate`` — the plumbing Phase 2's query SHAPE will ride on.
All offline (fake judge/search/curator), no model, no network.
"""

from langchain_core.messages import AIMessage
from lunaris_agent.harness.draft import CourseDraft
from lunaris_agent.harness.tools import make_curate_resources_tool
from lunaris_agent.subagents.resource_curator import (
    ClaudeResourceCurator,
    CuratedResources,
    DeterministicQueryTranslator,
    SearchQuery,
    representative_modality,
)
from lunaris_grounding import StubVideoSource
from lunaris_runtime.schema import (
    BloomLevel,
    CourseBrief,
    KnowledgeComponent,
    Lesson,
    Level,
    MerrillSegments,
    Modality,
    Module,
    PrerequisiteGraph,
    ResourceKind,
    Segment,
)


class _FakeJudge:
    async def ainvoke(self, prompt: str) -> AIMessage:
        return AIMessage(content="{}")


class _RecordingSearch:
    """An ISearchProvider that records the queries it receives and returns nothing."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, query: str, *, max_results: int = 5) -> list:
        self.queries.append(query)
        return []


class _RecordingTranslator:
    """An IQueryTranslator that records its inputs and replays fixed queries."""

    def __init__(self, queries: list[SearchQuery]) -> None:
        self._queries = queries
        self.calls: list[tuple[str | None, Modality | None, str | None]] = []

    async def translate(self, module, brief=None, *, modality=None, feedback=None):
        self.calls.append((module.competency, modality, feedback))
        return self._queries


class _RecordingCurator:
    """An IResourceCurator that records the modality it was asked to curate with."""

    def __init__(self) -> None:
        self.modalities: list[Modality | None] = []

    async def curate(self, module, brief=None, *, modality=None) -> CuratedResources:
        self.modalities.append(modality)
        return CuratedResources()


def _module() -> Module:
    return Module(
        id="m0",
        title="Listening for intent",
        kcs=["intent"],
        competency="hear implied intent in speech",
        difficulty_index=0.6,
    )


def _brief() -> CourseBrief:
    return CourseBrief(
        subject="English language proficiency", goal="reach CLB 10", target_level=Level.ADVANCED
    )


def _kc(kc_id: str, modality: Modality | None) -> KnowledgeComponent:
    return KnowledgeComponent(
        id=kc_id,
        label=kc_id,
        definition="x",
        difficulty=0.5,
        bloom_ceiling=BloomLevel.ANALYZE,
        modality=modality,
    )


async def test_curator_plans_searches_through_the_translator_seam() -> None:
    # Arrange — a translator returning ONE vernacular query (not the old "{competency} tutorial").
    search = _RecordingSearch()
    translator = _RecordingTranslator(
        [SearchQuery(kind=ResourceKind.ARTICLE, query="reading authorial stance C1")]
    )
    curator = ClaudeResourceCurator(_FakeJudge(), search, StubVideoSource(), translator=translator)

    # Act
    await curator.curate(_module(), _brief(), modality=Modality.RECEPTIVE)

    # Assert — the search ran the translator's query, and the translator saw the module + modality.
    assert search.queries == ["reading authorial stance C1"]
    assert translator.calls == [("hear implied intent in speech", Modality.RECEPTIVE, None)]


async def test_default_translator_preserves_todays_queries() -> None:
    # Arrange — no translator injected → the deterministic default (wraps build_resource_queries).
    search = _RecordingSearch()
    curator = ClaudeResourceCurator(_FakeJudge(), search, StubVideoSource())

    # Act
    await curator.curate(_module(), _brief())

    # Assert — the non-video kinds still search on the competency (today's behavior, via the seam).
    assert any("hear implied intent in speech" in q for q in search.queries)


def test_representative_modality_picks_the_dominant_kc_modality() -> None:
    # Arrange — a module spanning three KCs, receptive dominant (2 vs 1).
    graph = PrerequisiteGraph(
        nodes=[
            _kc("a", Modality.RECEPTIVE),
            _kc("b", Modality.PRODUCTIVE),
            _kc("c", Modality.RECEPTIVE),
        ]
    )
    module = Module(id="m", title="m", kcs=["a", "b", "c"])

    # Act / Assert — the dominant modality wins.
    assert representative_modality(module, graph) is Modality.RECEPTIVE


def test_representative_modality_is_none_when_unclassified_or_graphless() -> None:
    module = Module(id="m", title="m", kcs=["a"])
    assert representative_modality(module, None) is None
    graph = PrerequisiteGraph(nodes=[_kc("a", None)])
    assert representative_modality(module, graph) is None


async def test_curate_resources_tool_threads_representative_modality(progress_sink) -> None:
    # Arrange — a draft whose module KCs are productive; a recording curator captures the modality.
    draft = CourseDraft(topic="t", course_id="c", run_id="r")
    draft.graph = PrerequisiteGraph(nodes=[_kc("spk", Modality.PRODUCTIVE)])
    lesson = Lesson(
        id="m0-l0",
        segments=MerrillSegments(
            activate=Segment(prose="a"),
            demonstrate=Segment(prose="d"),
            apply=Segment(prose="ap"),
            integrate=Segment(prose="i"),
        ),
    )
    draft.modules = [
        Module(
            id="m0", title="Speaking", kcs=["spk"], competency="speak fluently", lessons=[lesson]
        )
    ]
    curator = _RecordingCurator()
    tool = make_curate_resources_tool(curator, draft)

    # Act
    await tool.ainvoke({})

    # Assert — the tool resolved the module's representative modality from the graph and passed it.
    assert curator.modalities == [Modality.PRODUCTIVE]


def test_deterministic_translator_is_the_default_fallback() -> None:
    # The default translator is the deterministic one (the T1 LLM translator's failure fallback).
    curator = ClaudeResourceCurator(_FakeJudge(), _RecordingSearch(), StubVideoSource())
    assert isinstance(curator._translator, DeterministicQueryTranslator)

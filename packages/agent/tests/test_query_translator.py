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
    ClaudeQueryTranslator,
    ClaudeResourceCurator,
    CuratedResources,
    SearchQuery,
    representative_modality,
)
from lunaris_grounding import StubVideoSource
from lunaris_runtime.schema import (
    BloomLevel,
    CourseBrief,
    GoalType,
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


def test_representative_modality_breaks_count_ties_by_enum_order() -> None:
    # Arrange — one receptive + one productive KC (a 1-1 tie); RECEPTIVE is the earlier enum member.
    graph = PrerequisiteGraph(nodes=[_kc("a", Modality.RECEPTIVE), _kc("b", Modality.PRODUCTIVE)])
    module = Module(id="m", title="m", kcs=["a", "b"])

    # Act / Assert — the tie resolves deterministically to the earlier-declared modality.
    assert representative_modality(module, graph) is Modality.RECEPTIVE


def test_representative_modality_is_none_when_there_is_no_graph() -> None:
    module = Module(id="m", title="m", kcs=["a"])
    assert representative_modality(module, None) is None


def test_representative_modality_is_none_when_no_kc_is_classified() -> None:
    module = Module(id="m", title="m", kcs=["a"])
    graph = PrerequisiteGraph(nodes=[_kc("a", None)])
    assert representative_modality(module, graph) is None


async def test_curate_resources_tool_threads_representative_modality() -> None:
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


# ── T1: the LLM query translator ───────────────────────────────────────────────────────────────


class _FakeModel:
    """A chat model stand-in: records prompts and replays a fixed text response."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.prompts: list[str] = []

    async def ainvoke(self, prompt: str) -> AIMessage:
        self.prompts.append(prompt)
        return AIMessage(content=self._response)


class _RaisingModel:
    async def ainvoke(self, prompt: str) -> AIMessage:
        raise RuntimeError("boom")


def _receptive_module() -> Module:
    return Module(
        id="m1",
        title="Comprehending dense input",
        kcs=["listen"],
        competency="Comprehend complex information from diverse sources",
        difficulty_index=0.7,
    )


def _credential_brief() -> CourseBrief:
    return CourseBrief(
        subject="English language proficiency",
        goal="reach CLB 10",
        goal_type=GoalType.CREDENTIAL,
        target_level=Level.ADVANCED,
    )


async def test_llm_translator_parses_queries_and_carries_the_judge_signal() -> None:
    # Arrange — the model returns two vernacular queries with a kind + the judge's content signal.
    model = _FakeModel(
        '[{"query": "C1 advanced English lecture full subtitles", "kind": "video", '
        '"media_role": "input_material", "level_hint": "C1/C2", '
        '"good_result_looks_like": "long native-level talk, accurate captions", '
        '"rationale": "comprehension grows from authentic input"},'
        '{"query": "how to infer implied meaning in difficult texts", "kind": "article", '
        '"media_role": "concept_explainer", "level_hint": "advanced", '
        '"good_result_looks_like": "teaches inference of subtext with examples", '
        '"rationale": "one strategy explainer"}]'
    )
    translator = ClaudeQueryTranslator(model)

    # Act
    queries = await translator.translate(
        _receptive_module(), _credential_brief(), modality=Modality.RECEPTIVE
    )

    # Assert — both parsed with their routing kind + the good_result_looks_like the judge scores on.
    assert [q.kind for q in queries] == [ResourceKind.VIDEO, ResourceKind.ARTICLE]
    assert queries[0].query == "C1 advanced English lecture full subtitles"
    assert queries[0].good_result_looks_like.startswith("long native-level talk")
    assert queries[0].media_role == "input_material"


async def test_llm_translator_drops_verbatim_competency_and_strips_hype() -> None:
    # Arrange — the model echoes the competency (must be dropped) + a hyped query (must be cleaned).
    model = _FakeModel(
        '[{"query": "Comprehend complex information from diverse sources", "kind": "article"},'
        '{"query": "best advanced English listening practice", "kind": "video"}]'
    )
    translator = ClaudeQueryTranslator(model)

    # Act
    queries = await translator.translate(_receptive_module(), _credential_brief())

    # Assert — the verbatim competency is gone; the surviving query has no hype word.
    assert len(queries) == 1
    assert "best" not in queries[0].query.lower()
    assert "advanced English listening practice" in queries[0].query


async def test_llm_translator_passes_goal_type_modality_and_feedback_into_the_prompt() -> None:
    # Arrange
    model = _FakeModel('[{"query": "x advanced", "kind": "article"}]')
    translator = ClaudeQueryTranslator(model)

    # Act
    await translator.translate(
        _receptive_module(),
        _credential_brief(),
        modality=Modality.RECEPTIVE,
        feedback="previous queries returned 0 results; broaden",
    )

    # Assert — the shaping inputs reach the model so it can derive query SHAPE + broaden on retry.
    prompt = model.prompts[0].lower()
    assert "credential" in prompt
    assert "receptive" in prompt
    assert "broaden" in prompt
    assert "comprehend complex information from diverse sources" in prompt


async def test_llm_translator_falls_back_to_deterministic_on_failure() -> None:
    # Arrange — the model raises; the translator must degrade to the deterministic queries.
    translator = ClaudeQueryTranslator(_RaisingModel())

    # Act
    queries = await translator.translate(_receptive_module(), _credential_brief())

    # Assert — non-empty, competency-anchored deterministic queries (today's behavior as the floor).
    assert queries
    assert any("Comprehend complex information from diverse sources" in q.query for q in queries)


async def test_llm_translator_falls_back_when_the_response_has_no_usable_queries() -> None:
    # Arrange — prose with no JSON array → parse yields nothing → fallback.
    translator = ClaudeQueryTranslator(_FakeModel("I could not produce queries."))

    # Act
    queries = await translator.translate(_receptive_module(), _credential_brief())

    # Assert — the deterministic floor still returns queries.
    assert queries


async def test_llm_translator_caps_queries_at_max() -> None:
    # Arrange — the model returns 4 distinct queries but the cap is 2 (over-retrieve, bounded).
    model = _FakeModel(
        '[{"query": "q one", "kind": "article"}, {"query": "q two", "kind": "video"},'
        '{"query": "q three", "kind": "docs"}, {"query": "q four", "kind": "practice"}]'
    )
    translator = ClaudeQueryTranslator(model, max_queries=2)

    # Act
    queries = await translator.translate(_receptive_module(), _credential_brief())

    # Assert — only the first two survive the cap.
    assert [q.query for q in queries] == ["q one", "q two"]

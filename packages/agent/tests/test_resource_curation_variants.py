"""CQ Phase 2 T6 — variant coverage (the Genericity Rule for resource curation).

The translator + curation must be goal-type/modality-blind, never wired to one domain (English): the
matrix below spans credential/skill/knowledge/behavior goals across receptive/procedural/conceptual/
productive modalities and AWS / CLB / ABRSM / Rust / habit domains. Plus the m1/m3 regression: an
abstract competency that used to return a silent zero now recovers via the broaden-retry. Offline
(fake model/search/judge), no network.
"""

import pytest
from langchain_core.messages import AIMessage
from lunaris_agent.subagents.resource_curator import (
    ClaudeQueryTranslator,
    ClaudeResourceCurator,
    SearchQuery,
)
from lunaris_grounding import SearchResult, StubVideoSource
from lunaris_runtime.schema import CourseBrief, GoalType, Level, Modality, Module, ResourceKind


class _EchoModel:
    """Records prompts; replays one valid (non-verbatim) query so parsing always succeeds."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def ainvoke(self, prompt: str) -> AIMessage:
        self.prompts.append(prompt)
        return AIMessage(content='[{"query": "domain vernacular query advanced", "kind": "video"}]')


class _FakeJudge:
    def __init__(self, response: str) -> None:
        self._response = response

    async def ainvoke(self, prompt: str) -> AIMessage:
        return AIMessage(content=self._response)


class _EmptyThenHit:
    """Empty on the first query, a hit once the broaden-retry runs (the m1/m3 zero → recovery)."""

    def __init__(self) -> None:
        self.calls = 0

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        self.calls += 1
        if self.calls == 1:
            return []
        return [SearchResult(url="https://found.example/x", title="Recovered", snippet="content")]


class _FeedbackTranslator:
    def __init__(self) -> None:
        self.feedbacks: list[str | None] = []

    async def translate(self, module, brief=None, *, modality=None, feedback=None):
        self.feedbacks.append(feedback)
        return [SearchQuery(kind=ResourceKind.ARTICLE, query="broadened query")]


# (goal_type, modality, domain, competency) rows: 3+ goal types over distinct domains (topic-blind).
_VARIANTS = [
    (GoalType.CREDENTIAL, Modality.RECEPTIVE, "English (CLB)", "Comprehend complex information"),
    (
        GoalType.CREDENTIAL,
        Modality.CONCEPTUAL,
        "AWS Solutions Architect",
        "Design multi-AZ resilience",
    ),
    (GoalType.SKILL, Modality.PROCEDURAL, "ABRSM Grade 8 piano", "Perform scales evenly at tempo"),
    (GoalType.KNOWLEDGE, Modality.CONCEPTUAL, "Rust ownership", "Explain the borrow checker rules"),
    (
        GoalType.BEHAVIOR,
        Modality.PRODUCTIVE,
        "Daily writing habit",
        "Sustain a daily writing practice",
    ),
]


@pytest.mark.parametrize(("goal_type", "modality", "domain", "competency"), _VARIANTS)
async def test_translator_shapes_queries_generically_across_goal_types_and_modalities(
    goal_type: GoalType, modality: Modality, domain: str, competency: str
) -> None:
    # Arrange — a brief + module for this domain/goal; the model echoes a parseable query.
    model = _EchoModel()
    translator = ClaudeQueryTranslator(model)
    module = Module(id="m", title=domain, kcs=["k"], competency=competency)
    brief = CourseBrief(
        subject=domain, goal=domain, goal_type=goal_type, target_level=Level.ADVANCED
    )

    # Act
    queries = await translator.translate(module, brief, modality=modality)

    # Assert — the shaping inputs reach the model for THIS goal/modality/domain (not hardcoded to
    # English), and the competency is rewritten, never emitted verbatim.
    prompt = model.prompts[0].lower()
    assert goal_type.value in prompt
    assert modality.value in prompt
    assert domain.lower() in prompt
    assert queries and all(q.query.lower() != competency.lower() for q in queries)


@pytest.mark.parametrize(("goal_type", "modality", "domain", "competency"), _VARIANTS)
async def test_abstract_competency_zero_recovers_via_broaden_retry(
    goal_type: GoalType, modality: Modality, domain: str, competency: str
) -> None:
    # Arrange — an abstract competency whose first search comes up empty (the m1/m3 failure), across
    # every goal type/domain; the broaden-retry must recover it rather than ship a silent zero.
    search = _EmptyThenHit()
    translator = _FeedbackTranslator()
    judge = _FakeJudge(
        '{"selected": [{"index": 0, "phase": "demonstrate", "why": "w", "credibility": 0.6}]}'
    )
    curator = ClaudeResourceCurator(judge, search, StubVideoSource(), translator=translator)
    module = Module(id="m", title=domain, kcs=["k"], competency=competency)
    brief = CourseBrief(subject=domain, goal=domain, goal_type=goal_type)

    # Act
    curated = await curator.curate(module, brief, modality=modality)

    # Assert — the broaden pass fired and a resource was recovered (no silent zero) per variant.
    assert translator.feedbacks[0] is None
    assert translator.feedbacks[1] is not None  # the broaden retry
    total = len(curated.activate + curated.demonstrate + curated.apply + curated.integrate)
    assert total == 1

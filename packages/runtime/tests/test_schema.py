import pytest
from lunaris_runtime.schema import (
    AgentEvent,
    AgentEventKind,
    BloomLevel,
    Citation,
    Course,
    CourseStatus,
    KnowledgeComponent,
    SourceType,
    TrustTier,
)
from pydantic import ValidationError


def test_course_minimal_construction_uses_defaults() -> None:
    # Arrange / Act
    course = Course(id="c1", topic="binary search")

    # Assert
    assert course.status is CourseStatus.DIAGNOSING
    assert course.graph.nodes == []
    assert course.settings.latency.value == "await_full"


def test_course_json_round_trip_is_camel_case() -> None:
    # Arrange
    course = Course(id="c1", topic="binary search", goal_concept="kc-goal")

    # Act
    payload = course.model_dump_json(by_alias=True)
    reloaded = Course.model_validate_json(payload)

    # Assert
    assert '"goalConcept":"kc-goal"' in payload.replace(" ", "")
    assert reloaded == course


def test_knowledge_component_difficulty_is_bounded() -> None:
    # Arrange / Act
    kc = KnowledgeComponent(
        id="kc1", label="Loops", definition="...", difficulty=0.4, bloom_ceiling=BloomLevel.APPLY
    )

    # Assert
    assert kc.difficulty == 0.4
    assert kc.bloom_ceiling is BloomLevel.APPLY


def test_citation_parses_without_trust_fields_for_backward_compat() -> None:
    # Arrange — a pre-P6.0 wire citation (no trust/provenance keys), as older courses carry.
    # Act
    citation = Citation.model_validate(
        {"id": "src-1", "title": "CLRS", "url": None, "snippet": "…"}
    )

    # Assert — it validates, with every trust field defaulting to None (the reader shows no badge).
    assert citation.id == "src-1"
    assert citation.trust_tier is None
    assert citation.credibility is None
    assert citation.source_type is None
    assert citation.fetched_at is None


def test_citation_carries_trust_provenance_camel_case() -> None:
    # Arrange
    citation = Citation(
        id="src-1",
        trust_tier=TrustTier.REPUTABLE,
        credibility=0.91,
        source_type=SourceType.REFERENCE,
        fetched_at="2026-06-03T00:00:00Z",
    )

    # Act — the wire shape the web reader consumes.
    payload = citation.model_dump_json(by_alias=True).replace(" ", "")
    reloaded = Citation.model_validate_json(payload)

    # Assert — camelCase keys, round-trips losslessly.
    assert '"trustTier":"reputable"' in payload
    assert '"sourceType":"reference"' in payload
    assert '"fetchedAt":"2026-06-03T00:00:00Z"' in payload
    assert reloaded == citation


def test_citation_credibility_is_bounded() -> None:
    # Arrange / Act / Assert — credibility is a 0..1 score; both bounds are rejected at the wire.
    assert Citation(id="x", credibility=0.0).credibility == 0.0
    assert Citation(id="x", credibility=1.0).credibility == 1.0
    with pytest.raises(ValidationError):
        Citation(id="x", credibility=1.5)
    with pytest.raises(ValidationError):
        Citation(id="x", credibility=-0.1)


def test_agent_event_rejects_both_text_and_delta() -> None:
    # Arrange / Act / Assert — a REASONING beat is a whole text OR a streaming delta, never both.
    with pytest.raises(ValidationError, match="mutually exclusive"):
        AgentEvent(kind=AgentEventKind.REASONING, run_id="r", text="whole", delta="chunk")


def test_agent_event_allows_text_or_delta_alone() -> None:
    # Arrange / Act — each form on its own is valid.
    whole = AgentEvent(kind=AgentEventKind.REASONING, run_id="r", text="whole beat")
    streamed = AgentEvent(kind=AgentEventKind.REASONING, run_id="r", delta="a chunk")

    # Assert
    assert whole.delta is None
    assert streamed.text is None

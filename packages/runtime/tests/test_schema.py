import pytest
from lunaris_runtime.schema import (
    AgentEvent,
    AgentEventKind,
    BloomLevel,
    Course,
    CourseStatus,
    KnowledgeComponent,
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

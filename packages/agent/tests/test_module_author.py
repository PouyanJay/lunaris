import pytest
from lunaris_agent.subagents.module_author import LessonAssembler, parse_lesson
from lunaris_agent.subagents.module_author.lesson_draft import LessonDraft, SegmentDraft


def _draft() -> LessonDraft:
    return LessonDraft(
        activate=SegmentDraft("recall arrays", ["arrays are indexed"]),
        demonstrate=SegmentDraft(
            "here is binary search", ["it runs in O(log n)", "needs sorted input"]
        ),
        apply=SegmentDraft("now trace it", []),
        integrate=SegmentDraft("use it in your code", []),
    )


def test_parse_lesson_reads_four_merrill_phases() -> None:
    # Arrange
    text = """{"activate": {"prose": "a", "claims": []},
               "demonstrate": {"prose": "b", "claims": ["x is true"]},
               "apply": {"prose": "c", "claims": []},
               "integrate": {"prose": "d", "claims": []}}"""

    # Act
    draft = parse_lesson(text)

    # Assert
    assert draft.demonstrate.claims == ["x is true"]
    assert draft.activate.prose == "a"


def test_parse_lesson_rejects_missing_phase() -> None:
    # Arrange — no "integrate" phase
    text = '{"activate": {"prose": "a"}, "demonstrate": {"prose": "b"}, "apply": {"prose": "c"}}'

    # Act / Assert — a lesson cannot exist without all four Merrill phases
    with pytest.raises(ValueError, match="missing Merrill phase"):
        parse_lesson(text)


def test_assemble_builds_lesson_with_claims_in_segments() -> None:
    # Act
    lesson = LessonAssembler().assemble(_draft(), lesson_id="m0-l0")

    # Assert — claims land in their segments as unverified Claim objects
    assert lesson.id == "m0-l0"
    assert [c.text for c in lesson.segments.demonstrate.claims] == [
        "it runs in O(log n)",
        "needs sorted input",
    ]
    assert lesson.segments.apply.claims == []
    # Gagné events the Merrill cycle structurally covers are flagged
    assert lesson.gagne.present_content is True
    assert lesson.gagne.enhance_transfer is True

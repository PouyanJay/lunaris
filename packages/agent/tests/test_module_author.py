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


def test_parse_lesson_reads_the_arc_bookends() -> None:
    # Arrange — an author response carrying the P7.3 arc compartments alongside the phases.
    text = """{"expects": ["You can form complex sentences."],
               "activate": {"prose": "a", "claims": []},
               "demonstrate": {"prose": "b", "claims": []},
               "apply": {"prose": "c", "claims": []},
               "integrate": {"prose": "d", "claims": []},
               "self_check": ["Can you hedge a disagreement?", "  "]}"""

    # Act
    draft = parse_lesson(text)

    # Assert — expects + self_check are read; blank self-check lines are dropped.
    assert draft.expects == ["You can form complex sentences."]
    assert draft.self_check == ["Can you hedge a disagreement?"]


def test_parse_lesson_defaults_the_arc_bookends_when_absent() -> None:
    # Arrange — a legacy / novice author that emits only the four Merrill phases (no arc bookends).
    text = """{"activate": {"prose": "a", "claims": []},
               "demonstrate": {"prose": "b", "claims": []},
               "apply": {"prose": "c", "claims": []},
               "integrate": {"prose": "d", "claims": []}}"""

    # Act
    draft = parse_lesson(text)

    # Assert — the lesson is still valid; the arc bookends simply default to empty.
    assert draft.expects == []
    assert draft.self_check == []


def test_parse_lesson_survives_a_malformed_json_response() -> None:
    # Arrange — a missing comma between two phases (the live delimiter failure). The author path
    # produces the actual lesson content, so it must survive a single slip, not lose the lesson.
    text = (
        '{"activate": {"prose": "a"} "demonstrate": {"prose": "b", "claims": []},'  # missing comma
        ' "apply": {"prose": "c"}, "integrate": {"prose": "d"}}'
    )

    # Act
    draft = parse_lesson(text)

    # Assert
    assert draft.activate.prose == "a"
    assert draft.demonstrate.prose == "b"


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

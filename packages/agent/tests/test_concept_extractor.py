import pytest
from lunaris_agent.subagents.concept_extractor import parse_extraction
from lunaris_runtime.schema import BloomLevel


def test_parse_extraction_reads_kcs_and_goal() -> None:
    # Arrange
    text = """Here you go:
    {"goal_id": "bsearch", "kcs": [
      {"id": "arrays", "label": "Arrays", "definition": "indexed lists",
       "difficulty": 0.2, "bloom_ceiling": "understand"},
      {"id": "bsearch", "label": "Binary search", "definition": "halving search",
       "difficulty": 0.8, "bloom_ceiling": "apply"}
    ]}"""

    # Act
    extraction = parse_extraction(text)

    # Assert
    assert extraction.goal_id == "bsearch"
    assert [kc.id for kc in extraction.kcs] == ["arrays", "bsearch"]
    assert extraction.kcs[0].bloom_ceiling is BloomLevel.UNDERSTAND


def test_parse_extraction_clamps_difficulty_and_defaults_bad_bloom() -> None:
    # Arrange — out-of-range difficulty + an invalid bloom level
    text = (
        '{"goal_id": "x", "kcs": [{"id": "x", "label": "X", "definition": "d",'
        ' "difficulty": 5, "bloom_ceiling": "wizardry"}]}'
    )

    # Act
    extraction = parse_extraction(text)

    # Assert
    assert extraction.kcs[0].difficulty == 1.0  # clamped
    assert extraction.kcs[0].bloom_ceiling is BloomLevel.APPLY  # safe default


def test_parse_extraction_defaults_goal_to_last_kc() -> None:
    # Arrange — no goal_id provided
    text = (
        '{"kcs": [{"id": "a", "label": "A", "definition": "d", "difficulty": 0.1},'
        ' {"id": "b", "label": "B", "definition": "d", "difficulty": 0.9}]}'
    )

    # Act
    extraction = parse_extraction(text)

    # Assert
    assert extraction.goal_id == "b"


def test_parse_extraction_rejects_goal_not_in_kcs() -> None:
    # Arrange
    text = (
        '{"goal_id": "ghost", "kcs": ['
        '{"id": "a", "label": "A", "definition": "d", "difficulty": 0.1}]}'
    )

    # Act / Assert
    with pytest.raises(ValueError, match="not among"):
        parse_extraction(text)


def test_parse_extraction_rejects_empty() -> None:
    with pytest.raises(ValueError, match="no JSON object"):
        parse_extraction("sorry, I cannot help with that")

import pytest
from lunaris_agent.subagents.curriculum_architect import (
    objective_has_valid_bloom_verb,
    parse_curriculum,
)
from lunaris_runtime.schema import BloomLevel

_KCS = {"arrays", "bsearch"}


def test_parse_curriculum_reads_modules_objectives_and_items() -> None:
    # Arrange
    text = """{"modules": [
      {"title": "Foundations", "kcs": ["arrays"], "objectives": [
        {"kc": "arrays", "statement": "Given a list, the learner can describe indexing",
         "bloom_level": "understand", "item_prompts": ["What is the first element's index?"]}]},
      {"title": "Search", "kcs": ["bsearch"], "objectives": [
        {"kc": "bsearch", "statement": "Given a sorted array, the learner can apply binary search",
         "bloom_level": "apply", "item_prompts": ["Trace binary search on [1,3,5,7]."]}]}
    ]}"""

    # Act
    plan = parse_curriculum(text, _KCS)

    # Assert
    assert [m.title for m in plan.modules] == ["Foundations", "Search"]
    assert plan.modules[1].objectives[0].bloom_level is BloomLevel.APPLY
    assert plan.modules[0].objectives[0].item_prompts


def test_parse_curriculum_rejects_objective_without_items() -> None:
    # Arrange
    text = (
        '{"modules": [{"title": "M", "kcs": ["arrays"], "objectives": ['
        '{"kc": "arrays", "statement": "s", "bloom_level": "understand", "item_prompts": []}]}]}'
    )

    # Act / Assert — backward design: no objective ships unassessed
    with pytest.raises(ValueError, match="no assessment items"):
        parse_curriculum(text, _KCS)


def test_parse_curriculum_rejects_unknown_kc() -> None:
    # Arrange
    text = (
        '{"modules": [{"title": "M", "kcs": ["ghost"], "objectives": ['
        '{"kc": "ghost", "statement": "s", "bloom_level": "apply", "item_prompts": ["q"]}]}]}'
    )

    # Act / Assert
    with pytest.raises(ValueError, match="unknown KC"):
        parse_curriculum(text, _KCS)


def test_parse_curriculum_survives_a_malformed_json_response() -> None:
    # Arrange — a missing comma between two object members (the live "Expecting ',' delimiter"
    # failure that crashed a real build). The tolerant loader repairs it instead of crashing.
    text = (
        '{"modules": [{"title": "M", "kcs": ["arrays"], "objectives": ['
        '{"kc": "arrays", "statement": "s" "bloom_level": "understand",'  # missing comma after "s"
        ' "item_prompts": ["q"]}]}]}'
    )

    # Act
    plan = parse_curriculum(text, _KCS)

    # Assert — the curriculum was recovered, not lost to a single delimiter slip.
    assert [m.title for m in plan.modules] == ["M"]
    assert plan.modules[0].objectives[0].item_prompts == ["q"]


def test_bloom_verb_helper_matches_level() -> None:
    assert objective_has_valid_bloom_verb("the learner can apply the rule", BloomLevel.APPLY)
    assert not objective_has_valid_bloom_verb("the learner can apply the rule", BloomLevel.CREATE)

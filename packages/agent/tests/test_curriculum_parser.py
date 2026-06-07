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
    assert plan.modules[0].objectives[0].items[0].prompt == "What is the first element's index?"


def test_parse_curriculum_reads_a_per_item_gradeable_pass_criterion() -> None:
    # Backward design (CQ Phase 4.1): each assessment item carries its summative-check prompt AND a
    # concrete, gradeable pass criterion (the structured `items` shape).
    # Arrange
    text = """{"modules": [
      {"title": "Search", "kcs": ["bsearch"], "objectives": [
        {"kc": "bsearch", "statement": "Given a sorted array, the learner can apply binary search",
         "bloom_level": "apply", "items": [
           {"prompt": "Trace binary search on [1,3,5,7].",
            "pass_criterion": "Halves the range each step; finds 5 in <=3 comparisons."}]}]}
    ]}"""

    # Act
    plan = parse_curriculum(text, _KCS)

    # Assert — the prompt and its gradeable criterion are both carried onto the plan.
    item = plan.modules[0].objectives[0].items[0]
    assert item.prompt.startswith("Trace binary search")
    assert "comparisons" in item.pass_criterion


def test_parse_curriculum_accepts_legacy_item_prompts_without_criteria() -> None:
    # Backward-compat: a pre-P4 response with `item_prompts` (bare strings, no criteria) still
    # parses — each becomes an item with an empty pass criterion.
    # Arrange
    text = (
        '{"modules": [{"title": "M", "kcs": ["arrays"], "objectives": ['
        '{"kc": "arrays", "statement": "s", "bloom_level": "apply", "item_prompts": ["q"]}]}]}'
    )

    # Act
    plan = parse_curriculum(text, _KCS)

    # Assert
    items = plan.modules[0].objectives[0].items
    assert [i.prompt for i in items] == ["q"]
    assert items[0].pass_criterion == ""


def test_parse_curriculum_tolerates_items_emitted_as_a_non_list() -> None:
    # A live-model slip: `items` emitted as a bare string instead of an array. The parser must NOT
    # character-iterate it — it ignores the malformed `items` and falls back to `item_prompts`.
    # Arrange
    text = (
        '{"modules": [{"title": "M", "kcs": ["arrays"], "objectives": ['
        '{"kc": "arrays", "statement": "s", "bloom_level": "apply",'
        ' "items": "Trace it.", "item_prompts": ["fallback"]}]}]}'
    )

    # Act
    plan = parse_curriculum(text, _KCS)

    # Assert — the bare-string items is discarded; the legacy prompts carry through intact.
    assert [i.prompt for i in plan.modules[0].objectives[0].items] == ["fallback"]


def test_parse_curriculum_reads_a_per_module_competency() -> None:
    # Arrange — the architect tagged the module with the researched competency it builds (P7.3).
    text = """{"modules": [
      {"title": "Search", "competency": "Locate an element in a sorted collection efficiently.",
       "kcs": ["bsearch"], "objectives": [
        {"kc": "bsearch", "statement": "Given a sorted array, the learner can apply binary search",
         "bloom_level": "apply", "item_prompts": ["Trace binary search on [1,3,5,7]."]}]}
    ]}"""

    # Act
    plan = parse_curriculum(text, _KCS)

    # Assert — the competency is carried onto the plan.
    assert plan.modules[0].competency == "Locate an element in a sorted collection efficiently."


def test_parse_curriculum_leaves_competency_none_when_absent() -> None:
    # Arrange — a module with no competency tag (no-research path).
    text = (
        '{"modules": [{"title": "M", "kcs": ["arrays"], "objectives": ['
        '{"kc": "arrays", "statement": "s", "bloom_level": "apply", "item_prompts": ["q"]}]}]}'
    )

    # Act
    plan = parse_curriculum(text, _KCS)

    # Assert
    assert plan.modules[0].competency is None


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
    assert [i.prompt for i in plan.modules[0].objectives[0].items] == ["q"]


def test_bloom_verb_helper_matches_level() -> None:
    assert objective_has_valid_bloom_verb("the learner can apply the rule", BloomLevel.APPLY)
    assert not objective_has_valid_bloom_verb("the learner can apply the rule", BloomLevel.CREATE)

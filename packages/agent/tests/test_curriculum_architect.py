"""ClaudeCurriculumArchitect parse-repair: a weak model's bad KC reference must not kill a build.

A live device (keyless) build died at curriculum design: the prompt enumerates the teaching
order as ``1. kc_id — label``, and the small on-device model answered with the list number
(``"kc": "1"``) instead of the kc id, so ``parse_curriculum`` raised with no retry. The
architect now gets bounded repair turns (the parse error folded into the prompt), and the
prompt itself tells the model to copy ids verbatim.
"""

import json

import pytest
from _scripted_chat import ScriptedRecordingChatModel
from langchain_core.language_models import BaseChatModel
from lunaris_agent.subagents.curriculum_architect import (
    ClaudeCurriculumArchitect,
    build_curriculum_prompt,
)
from lunaris_runtime.schema import BloomLevel, KnowledgeComponent, PrerequisiteGraph

_KC_ID = "binary-search-algorithm"


def _curriculum(kc: str) -> str:
    return json.dumps(
        {
            "modules": [
                {
                    "title": "Binary Search",
                    "kcs": [kc],
                    "objectives": [
                        {
                            "kc": kc,
                            "statement": "Given a sorted array, the learner can apply it",
                            "bloom_level": "apply",
                            "items": [
                                {"prompt": "Trace a search", "pass_criterion": "Correct midpoints"}
                            ],
                        }
                    ],
                }
            ]
        }
    )


# The prod device-build failure verbatim: the model echoed the teaching-order list number.
# Positional references now resolve deterministically (see the no-repair-turn test below), so
# the repair-path tests use a reference that genuinely can't be resolved.
_POSITIONAL_KC_CURRICULUM = _curriculum("kc_1")

_UNRESOLVABLE_KC_CURRICULUM = _curriculum("ghost-concept")

_VALID_CURRICULUM = _curriculum(_KC_ID)


def _architect(client: ScriptedRecordingChatModel, **kwargs: int) -> ClaudeCurriculumArchitect:
    def factory(model: str) -> BaseChatModel:
        return client  # type: ignore[return-value]  # duck-typed double: only ainvoke is used

    return ClaudeCurriculumArchitect("claude-test", client_factory=factory, **kwargs)


def _graph() -> PrerequisiteGraph:
    return PrerequisiteGraph(
        nodes=[
            KnowledgeComponent(
                id=_KC_ID,
                label="Binary search",
                definition="halving search on sorted data",
                difficulty=0.5,
                bloom_ceiling=BloomLevel.APPLY,
            )
        ],
        edges=[],
        is_acyclic=True,
        topo_order=[_KC_ID],
    )


async def test_design_repairs_an_unresolvable_kc_reference_instead_of_failing() -> None:
    # Arrange — first response targets a KC that exists nowhere, the second is valid.
    client = ScriptedRecordingChatModel([_UNRESOLVABLE_KC_CURRICULUM, _VALID_CURRICULUM])
    architect = _architect(client)

    # Act
    plan = await architect.design(_graph())

    # Assert — the repaired plan came back instead of a raised parse error.
    assert plan.modules[0].objectives[0].kc == _KC_ID
    assert len(client.prompts) == 2


async def test_design_sends_the_parse_error_with_the_original_prompt_on_repair() -> None:
    # Arrange
    client = ScriptedRecordingChatModel([_UNRESOLVABLE_KC_CURRICULUM, _VALID_CURRICULUM])
    architect = _architect(client)

    # Act
    await architect.design(_graph())

    # Assert — the repair turn restates the full original prompt plus the parse error.
    first_prompt, repair_prompt = client.prompts
    assert repair_prompt.startswith(first_prompt)
    assert "unknown KC 'ghost-concept'" in repair_prompt
    assert _KC_ID in repair_prompt


async def test_design_raises_after_exhausting_bounded_repair_attempts() -> None:
    # Arrange — every response carries the bad KC reference, so repair can never succeed.
    client = ScriptedRecordingChatModel([_UNRESOLVABLE_KC_CURRICULUM] * 3)
    architect = _architect(client, max_attempts=3)

    # Act / Assert — the parse error surfaces after exactly max_attempts calls.
    with pytest.raises(ValueError, match="unknown KC"):
        await architect.design(_graph())
    assert len(client.prompts) == 3

    # Assert — repair feedback never stacks: every repair turn rebuilds from the original
    # prompt, so identical errors produce identical repair prompts.
    original_prompt, first_repair, second_repair = client.prompts
    assert first_repair == second_repair
    assert first_repair.startswith(original_prompt)


async def test_design_resolves_a_positional_kc_reference_without_a_repair_turn() -> None:
    # Arrange — the persistent device-model habit: "kc_1" for the first listed KC. The
    # numbering is ours (the prompt enumerates the teaching order), so no repair turn is spent.
    client = ScriptedRecordingChatModel([_POSITIONAL_KC_CURRICULUM])
    architect = _architect(client)

    # Act
    plan = await architect.design(_graph())

    # Assert — resolved deterministically on the first attempt, in the kcs list too.
    assert plan.modules[0].objectives[0].kc == _KC_ID
    assert plan.modules[0].kcs == [_KC_ID]
    assert len(client.prompts) == 1


def test_prompt_tells_the_model_to_copy_kc_ids_verbatim() -> None:
    # Arrange — the head-off: weak models echo the enumeration number unless told not to.
    graph = _graph()

    # Act
    prompt = build_curriculum_prompt(graph)

    # Assert
    assert "never the list number" in prompt

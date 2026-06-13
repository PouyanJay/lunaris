"""ScenePlanner tests (stubbed model): the PLAN node turns a lesson into a validated
SceneContracts with the global_style INJECTED from the token map — the model never chooses
style — and malformed completions get bounded repair turns before failing clean."""

import json
from collections.abc import Callable

import pytest
from lunaris_runtime.resilience import DEFAULT_PARSE_REPAIR_ATTEMPTS
from lunaris_video.models import LessonSource
from lunaris_video.planning import ScenePlanner
from lunaris_video.schemas import SceneContracts
from lunaris_video.skill import read_skill_asset
from lunaris_video.style import video_global_style


def _lesson() -> LessonSource:
    return LessonSource(
        course_topic="Algorithms and data structures",
        lesson_title="How merge sort works",
        audience="first-year CS students who know arrays",
        prose="Merge sort splits the array in half, sorts each half, and merges the results.",
    )


def _draft_payload(contract_factory: Callable[..., SceneContracts]) -> dict[str, object]:
    contract = contract_factory().model_dump(mode="json")
    return {
        key: contract[key]
        for key in ("topic", "audience", "visual_archetypes_used", "asset_strategy", "scenes")
    }


class _StubModel:
    """Scripted completions, recording every prompt the planner sends."""

    def __init__(self, replies: list[str]) -> None:
        self.prompts: list[str] = []
        self._replies = replies

    async def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        call_index = len(self.prompts) - 1  # 0-based; repeats the last reply once exhausted
        return self._replies[min(call_index, len(self._replies) - 1)]


async def test_planner_builds_a_contract_with_injected_style(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange
    payload = _draft_payload(make_lesson_contract)
    stub = _StubModel([json.dumps(payload)])
    planner = ScenePlanner(invoke=stub)

    # Act
    contract = await planner.plan(_lesson())

    # Assert — the style is the token map's, the gates are the spec's, the scenes the model's.
    assert contract.global_style == video_global_style()
    assert contract.verifier_gates == [
        "render_success_per_scene",
        "frame_visual_qa",
        "narration_claim_check_vs_sources",
    ]
    assert len(contract.scenes) == len(payload["scenes"])  # type: ignore[arg-type]


async def test_model_cannot_choose_global_style(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange — first completion smuggles a global_style; the draft schema rejects it, the
    # repair turn carries the error, the second completion is clean.
    smuggled = dict(_draft_payload(make_lesson_contract))
    smuggled["global_style"] = {"background": "#FF00FF"}
    stub = _StubModel([json.dumps(smuggled), json.dumps(_draft_payload(make_lesson_contract))])
    planner = ScenePlanner(invoke=stub)

    # Act
    contract = await planner.plan(_lesson())

    # Assert
    assert len(stub.prompts) == 2
    assert "global_style" in stub.prompts[1]  # the repair turn names the rejected field
    assert contract.global_style == video_global_style()


async def test_planner_exhausts_repairs_and_raises() -> None:
    # Arrange
    stub = _StubModel(["not json at all"])
    planner = ScenePlanner(invoke=stub)

    # Act / Assert — bounded attempts, then the parse error propagates (the worker fails the job).
    with pytest.raises(ValueError):
        await planner.plan(_lesson())
    assert len(stub.prompts) == DEFAULT_PARSE_REPAIR_ATTEMPTS


async def test_prompt_carries_lesson_and_pinned_skill_context(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange
    stub = _StubModel([json.dumps(_draft_payload(make_lesson_contract))])
    planner = ScenePlanner(invoke=stub)

    # Act
    await planner.plan(_lesson(), target_seconds=80)

    # Assert — the prompt grounds the model in the lesson AND the pinned references (verbatim),
    # caps the envelope, and forbids invented figures (V1 has no grounding packet yet).
    prompt = stub.prompts[0]
    assert "How merge sort works" in prompt
    assert "Merge sort splits the array in half" in prompt
    assert "80" in prompt
    archetypes = read_skill_asset("references/archetypes.md")
    assert archetypes[:200] in prompt
    assert "framing only - no empirical claims" in prompt

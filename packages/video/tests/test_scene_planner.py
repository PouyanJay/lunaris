"""ScenePlanner tests (stubbed model): the PLAN node turns a lesson into a validated
SceneContracts with the global_style INJECTED from the token map — the model never chooses
style — and malformed completions get bounded repair turns before failing clean."""

import json
from collections.abc import Callable

import pytest
from _stubs import StubInvokeModel
from lunaris_runtime.resilience import DEFAULT_PARSE_REPAIR_ATTEMPTS
from lunaris_video.models import GroundedClaim, GroundingPacket, LessonSource, PacketKind
from lunaris_video.planning import ScenePlanner
from lunaris_video.schemas import FRAMING_ONLY_SENTINEL, SceneContracts
from lunaris_video.skill import read_skill_asset
from lunaris_video.style import video_global_style


def _lesson() -> LessonSource:
    return LessonSource(
        course_topic="Algorithms and data structures",
        lesson_title="How merge sort works",
        audience="first-year CS students who know arrays",
        prose="Merge sort splits the array in half, sorts each half, and merges the results.",
    )


def _packet(*claims: GroundedClaim) -> GroundingPacket:
    return GroundingPacket(kind=PacketKind.LESSON, claims=tuple(claims))


def _grounded_lesson(packet: GroundingPacket) -> LessonSource:
    return LessonSource(
        course_topic="Algorithms and data structures",
        lesson_title="How merge sort works",
        audience="first-year CS students who know arrays",
        prose="Merge sort splits the array in half, sorts each half, and merges the results.",
        packet=packet,
    )


def _set_scene_sources(scene: dict[str, object], sources: list[str]) -> None:
    """Point one draft scene's sources at the given claim ids (or the framing sentinel)."""
    scene["sources"] = sources


def _draft_payload(contract_factory: Callable[..., SceneContracts]) -> dict[str, object]:
    contract = contract_factory().model_dump(mode="json")
    return {
        key: contract[key]
        for key in ("topic", "audience", "visual_archetypes_used", "asset_strategy", "scenes")
    }


async def test_planner_builds_a_contract_with_injected_style(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange
    payload = _draft_payload(make_lesson_contract)
    stub = StubInvokeModel([json.dumps(payload)])
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
    stub = StubInvokeModel([json.dumps(smuggled), json.dumps(_draft_payload(make_lesson_contract))])
    planner = ScenePlanner(invoke=stub)

    # Act
    contract = await planner.plan(_lesson())

    # Assert
    assert len(stub.prompts) == 2
    assert "global_style" in stub.prompts[1]  # the repair turn names the rejected field
    assert contract.global_style == video_global_style()


async def test_planner_exhausts_repairs_and_raises() -> None:
    # Arrange
    stub = StubInvokeModel(["not json at all"])
    planner = ScenePlanner(invoke=stub)

    # Act / Assert — bounded attempts, then the parse error propagates (the worker fails the job).
    with pytest.raises(ValueError):
        await planner.plan(_lesson())
    assert len(stub.prompts) == DEFAULT_PARSE_REPAIR_ATTEMPTS


async def test_prompt_carries_lesson_and_pinned_skill_context(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange
    stub = StubInvokeModel([json.dumps(_draft_payload(make_lesson_contract))])
    planner = ScenePlanner(invoke=stub)

    # Act
    await planner.plan(_lesson(), target_seconds=80)

    # Assert — the prompt grounds the model in the lesson AND the pinned references (verbatim),
    # caps the envelope, and offers the framing-only sentinel for scenes that assert nothing.
    prompt = stub.prompts[0]
    assert "How merge sort works" in prompt
    assert "Merge sort splits the array in half" in prompt
    assert "80" in prompt
    archetypes = read_skill_asset("references/archetypes.md")
    assert archetypes[:200] in prompt
    assert "framing only - no empirical claims" in prompt


async def test_prompt_requires_one_reveal_per_beat(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange — sync is deterministic only if each beat's narrated element can sit on screen from
    # the START of its window. A beat that introduces TWO things desyncs at the midpoint, so planner
    # must split compound narration into one-reveal beats (pairs with the codegen front-load rule).
    stub = StubInvokeModel([json.dumps(_draft_payload(make_lesson_contract))])
    planner = ScenePlanner(invoke=stub)

    # Act
    await planner.plan(_lesson(), target_seconds=80)

    # Assert — the one-reveal-per-beat discipline (and the split instruction) is in the prompt.
    # Match the exact instructional phrase, not a bare "split" the lesson prose could supply.
    prompt = stub.prompts[0].lower()
    assert "one reveal per beat" in prompt
    assert "split it into two beats" in prompt


def _two_claim_packet() -> GroundingPacket:
    return _packet(
        GroundedClaim(
            id="c1",
            text="Merge sort runs in O(n log n) time.",
            citation_id="cite-clrs",
            source_label="CLRS",
        ),
        GroundedClaim(
            id="c2",
            text="Each merge pass touches all n elements.",
            citation_id="cite-clrs",
            source_label="CLRS",
        ),
    )


async def test_prompt_lists_the_packet_claims_for_citation(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange — a lesson with two verified claims: the planner must show BOTH with ids + sources.
    stub = StubInvokeModel([json.dumps(_draft_payload(make_lesson_contract))])
    planner = ScenePlanner(invoke=stub)

    # Act
    await planner.plan(_grounded_lesson(_two_claim_packet()))

    # Assert — the model can only cite what it can see: each claim's id, text and source label.
    prompt = stub.prompts[0]
    assert "[c1]" in prompt
    assert "Merge sort runs in O(n log n) time." in prompt
    assert "[c2]" in prompt
    assert "Each merge pass touches all n elements." in prompt
    assert "CLRS" in prompt


async def test_planner_accepts_a_scene_citing_multiple_known_claim_ids(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange — one scene draws on two verified claims at once.
    payload = _draft_payload(make_lesson_contract)
    _set_scene_sources(payload["scenes"][0], ["c1", "c2"])  # type: ignore[index]
    stub = StubInvokeModel([json.dumps(payload)])
    planner = ScenePlanner(invoke=stub)

    # Act
    contract = await planner.plan(_grounded_lesson(_two_claim_packet()))

    # Assert — both cited ids survive (Gate C will diff figures against both).
    assert contract.scenes[0].sources == ["c1", "c2"]


async def test_planner_accepts_a_contract_mixing_grounded_and_framing_only_scenes(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange — scene 1 grounds on a claim; the rest are pure framing (the standard arc's hook).
    payload = _draft_payload(make_lesson_contract)
    _set_scene_sources(payload["scenes"][0], ["c1"])  # type: ignore[index]
    stub = StubInvokeModel([json.dumps(payload)])
    planner = ScenePlanner(invoke=stub)

    # Act
    contract = await planner.plan(_grounded_lesson(_two_claim_packet()))

    # Assert — per-scene grounding is independent: one cites a claim, the others stay framing-only.
    assert contract.scenes[0].sources == ["c1"]
    assert all(scene.sources == [FRAMING_ONLY_SENTINEL] for scene in contract.scenes[1:])


async def test_planner_repairs_a_scene_that_cites_an_unknown_claim_id(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange — the first completion cites c9, which the packet never lists (an invented figure's
    # tell); the repair turn must name it; the second completion cites the real c1.
    payload_bad = _draft_payload(make_lesson_contract)
    _set_scene_sources(payload_bad["scenes"][0], ["c9"])  # type: ignore[index]
    payload_good = _draft_payload(make_lesson_contract)
    _set_scene_sources(payload_good["scenes"][0], ["c1"])  # type: ignore[index]
    stub = StubInvokeModel([json.dumps(payload_bad), json.dumps(payload_good)])
    planner = ScenePlanner(invoke=stub)

    # Act
    contract = await planner.plan(_grounded_lesson(_two_claim_packet()))

    # Assert — the repair turn is a distinct prompt that names the offending id.
    assert len(stub.prompts) == 2
    assert stub.prompts[0] != stub.prompts[1]
    assert "c9" in stub.prompts[1]
    assert contract.scenes[0].sources == ["c1"]


async def test_planner_repairs_a_scene_citing_a_mix_of_known_and_unknown_ids(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange — c1 is real but c9 is invented: one bad id in the list still fails the scene.
    payload_bad = _draft_payload(make_lesson_contract)
    _set_scene_sources(payload_bad["scenes"][0], ["c1", "c9"])  # type: ignore[index]
    payload_good = _draft_payload(make_lesson_contract)
    _set_scene_sources(payload_good["scenes"][0], ["c1"])  # type: ignore[index]
    stub = StubInvokeModel([json.dumps(payload_bad), json.dumps(payload_good)])
    planner = ScenePlanner(invoke=stub)

    # Act
    contract = await planner.plan(_grounded_lesson(_two_claim_packet()))

    # Assert — only the unknown id is named; the legitimate c1 is not flagged.
    assert len(stub.prompts) == 2
    assert "c9" in stub.prompts[1]
    assert contract.scenes[0].sources == ["c1"]


async def test_empty_packet_instructs_every_scene_to_be_framing_only(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange — no verified claims: a framing-only completion is accepted; we inspect the prompt.
    stub = StubInvokeModel([json.dumps(_draft_payload(make_lesson_contract))])
    planner = ScenePlanner(invoke=stub)

    # Act
    await planner.plan(_lesson())

    # Assert — the prompt steers the model to assert nothing and offers the sentinel.
    prompt = stub.prompts[0]
    assert "no verified claims" in prompt.lower()
    assert FRAMING_ONLY_SENTINEL in prompt


async def test_empty_packet_rejects_a_scene_that_cites_a_claim(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange — with no claims available, ANY claim-id citation is an invented figure: repair, then
    # the model falls back to framing-only (the fixture's default).
    cites_a_claim = _draft_payload(make_lesson_contract)
    _set_scene_sources(cites_a_claim["scenes"][0], ["c1"])  # type: ignore[index]
    framing_only = _draft_payload(make_lesson_contract)
    stub = StubInvokeModel([json.dumps(cites_a_claim), json.dumps(framing_only)])
    planner = ScenePlanner(invoke=stub)

    # Act
    contract = await planner.plan(_lesson())

    # Assert — the repair turn names the offending id; the retried contract asserts nothing.
    assert len(stub.prompts) == 2
    assert "c1" in stub.prompts[1]
    assert all(scene.sources == [FRAMING_ONLY_SENTINEL] for scene in contract.scenes)

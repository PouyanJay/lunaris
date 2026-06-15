"""ScenePlanner.plan_chaptered (video V5-T1): the OVERVIEW kind's PLAN node — a ~3-minute topic
intro that exceeds the skill's 3-5-scene envelope is planned as a CHAPTERED contract (chapters of
3-4 scenes → one MP4). Like the flat path: the model emits everything creative, the system injects
``global_style`` (never the model's choice) and the verifier gates, and a scene citing an unknown
claim id earns a repair turn. The chapter count scales with the configured target length."""

import json
from collections.abc import Callable

import pytest
from _stubs import StubInvokeModel
from lunaris_runtime.resilience import DEFAULT_PARSE_REPAIR_ATTEMPTS
from lunaris_video.models import GroundedClaim, GroundingPacket, LessonSource, PacketKind
from lunaris_video.planning import ScenePlanner
from lunaris_video.schemas import FRAMING_ONLY_SENTINEL, ChapteredSceneContracts
from lunaris_video.style import video_global_style

_OVERVIEW_SECONDS = 180


def _overview_source(packet: GroundingPacket | None = None) -> LessonSource:
    return LessonSource(
        course_topic="Information theory",
        lesson_title="Course overview: what information theory is and why it matters",
        audience="curious newcomers",
        prose="A tour of the whole course: the question, the key insight, and where it leads.",
        packet=packet or GroundingPacket(kind=PacketKind.OVERVIEW),
    )


def _chaptered_draft_payload(
    contract_factory: Callable[..., ChapteredSceneContracts],
) -> dict[str, object]:
    contract = contract_factory().model_dump(mode="json")
    return {
        key: contract[key]
        for key in ("topic", "audience", "visual_archetypes_used", "asset_strategy", "chapters")
    }


async def test_chaptered_prompt_requires_one_reveal_per_beat(
    make_chaptered_contract: Callable[..., ChapteredSceneContracts],
) -> None:
    # Arrange — the overview path needs the same sync discipline: one reveal per beat so each beat's
    # element can be front-loaded to its window start (present at the midpoint Gate D samples).
    stub = StubInvokeModel([json.dumps(_chaptered_draft_payload(make_chaptered_contract))])
    planner = ScenePlanner(invoke=stub)

    # Act
    await planner.plan_chaptered(_overview_source(), target_seconds=_OVERVIEW_SECONDS)

    # Assert
    prompt = stub.prompts[0].lower()
    assert "one reveal per beat" in prompt
    assert "split" in prompt


async def test_chaptered_planner_builds_a_contract_with_injected_style(
    make_chaptered_contract: Callable[..., ChapteredSceneContracts],
) -> None:
    # Arrange
    payload = _chaptered_draft_payload(make_chaptered_contract)
    stub = StubInvokeModel([json.dumps(payload)])
    planner = ScenePlanner(invoke=stub)

    # Act
    contract = await planner.plan_chaptered(_overview_source(), target_seconds=_OVERVIEW_SECONDS)

    # Assert — a chaptered contract; style + gates injected by the system, chapters from the model,
    # and scenes flatten across chapters into one render order (one MP4).
    assert isinstance(contract, ChapteredSceneContracts)
    assert contract.global_style == video_global_style()
    assert contract.verifier_gates == [
        "render_success_per_scene",
        "frame_visual_qa",
        "narration_claim_check_vs_sources",
    ]
    assert len(contract.chapters) == 2
    assert [scene.id for scene in contract.scenes] == [
        "S1_hook",
        "S2_framing",
        "S3_bits",
        "S4_entropy",
    ]


async def test_chaptered_prompt_scales_with_the_target_length(
    make_chaptered_contract: Callable[..., ChapteredSceneContracts],
) -> None:
    # Arrange — capture the prompt the stub receives for a 3-minute overview.
    payload = _chaptered_draft_payload(make_chaptered_contract)
    stub = StubInvokeModel([json.dumps(payload)])
    planner = ScenePlanner(invoke=stub)

    # Act
    await planner.plan_chaptered(_overview_source(), target_seconds=_OVERVIEW_SECONDS)

    # Assert — the PLAN prompt carries the configured length AND a chapter count derived FROM that
    # length (180s → 3 chapters), so the chaptered structure scales with the target, not a constant.
    prompt = stub.prompts[0]
    assert "about 180 seconds" in prompt
    assert "about 3 chapters" in prompt


async def test_chaptered_planner_model_cannot_choose_global_style(
    make_chaptered_contract: Callable[..., ChapteredSceneContracts],
) -> None:
    # Arrange — the first completion smuggles a global_style into the draft; the draft schema
    # rejects it (extra=forbid), the repair turn carries the error, the second completion is clean.
    smuggled = dict(_chaptered_draft_payload(make_chaptered_contract))
    smuggled["global_style"] = {"palette": "rainbow"}
    clean = json.dumps(_chaptered_draft_payload(make_chaptered_contract))
    stub = StubInvokeModel([json.dumps(smuggled), clean])
    planner = ScenePlanner(invoke=stub)

    # Act
    contract = await planner.plan_chaptered(_overview_source(), target_seconds=_OVERVIEW_SECONDS)

    # Assert — two model calls (smuggle → repair), and the injected style wins.
    assert len(stub.prompts) == 2
    assert contract.global_style == video_global_style()


async def test_chaptered_planner_rejects_a_scene_citing_an_unknown_claim_id(
    make_chaptered_contract: Callable[..., ChapteredSceneContracts],
) -> None:
    # Arrange — the only grounded claim is c1; a chapter scene cites c9 (not in the packet). The
    # planner must reject it with a repair turn rather than let an ungrounded figure through.
    packet = GroundingPacket(
        kind=PacketKind.OVERVIEW,
        claims=(
            GroundedClaim(id="c1", text="A grounded fact.", citation_id="u", source_label="S"),
        ),
    )
    bad = _chaptered_draft_payload(make_chaptered_contract)
    bad["chapters"][0]["scenes"][0]["sources"] = ["c9"]  # type: ignore[index]
    good = _chaptered_draft_payload(make_chaptered_contract)
    good["chapters"][0]["scenes"][0]["sources"] = ["c1"]  # type: ignore[index]
    stub = StubInvokeModel([json.dumps(bad), json.dumps(good)])
    planner = ScenePlanner(invoke=stub)

    # Act
    contract = await planner.plan_chaptered(
        _overview_source(packet), target_seconds=_OVERVIEW_SECONDS
    )

    # Assert — the repair turn is a distinct prompt that names the offending id (so the model can
    # self-correct), and the repaired contract cites only known ids.
    assert len(stub.prompts) == 2
    assert stub.prompts[0] != stub.prompts[1]
    assert "c9" in stub.prompts[1]
    assert contract.chapters[0].scenes[0].sources == ["c1"]


async def test_chaptered_planner_allows_framing_only_scenes(
    make_chaptered_contract: Callable[..., ChapteredSceneContracts],
) -> None:
    # Arrange — an empty packet (no grounded facts): every scene must be framing-only, which the
    # fixture's scenes already are. This proves the moat doesn't block an ungrounded overview.
    payload = _chaptered_draft_payload(make_chaptered_contract)
    stub = StubInvokeModel([json.dumps(payload)])
    planner = ScenePlanner(invoke=stub)

    # Act
    contract = await planner.plan_chaptered(_overview_source(), target_seconds=_OVERVIEW_SECONDS)

    # Assert — the happy path took exactly one model call (no repairs), all scenes framing-only.
    assert len(stub.prompts) == 1
    assert all(scene.sources == [FRAMING_ONLY_SENTINEL] for scene in contract.scenes)


async def test_chaptered_planner_fails_clean_after_exhausting_repairs() -> None:
    # Arrange — every completion is unparseable JSON (the stub repeats its last reply); the planner
    # exhausts its bounded repair budget and raises rather than hanging or half-building a contract.
    stub = StubInvokeModel(["not json"])
    planner = ScenePlanner(invoke=stub)

    # Act / Assert — the parse error propagates once the budget is spent (the worker fails the job).
    with pytest.raises(ValueError):
        await planner.plan_chaptered(_overview_source(), target_seconds=_OVERVIEW_SECONDS)
    assert len(stub.prompts) == DEFAULT_PARSE_REPAIR_ATTEMPTS

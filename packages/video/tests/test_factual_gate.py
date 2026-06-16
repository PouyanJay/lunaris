"""Gate C — the factual gate (V2-T2, severity-tiered in quality Phase 1). Every numeric figure a
scene's narration states must be supported by a claim the scene cites; a framing-only scene may
assert no figure and no comparison.

Severity-tiered disposition (the Phase-1 quality hardening): a **minor** violation — a *grounded*
scene narrating a figure no cited claim supports — no longer fails the whole video; the gate records
it and the scene ships flagged (`degraded_scenes`). A **major** violation — a framing-only scene
smuggling a figure or a comparison, or a scene citing a claim absent from the packet — still fails
the job clean (the moat bites where it matters). The gate diffs the CONTRACT against the packet
(content is static once planned), so it runs before any render compute is spent."""

import pytest
from lunaris_video.errors import FactualGateError
from lunaris_video.gates import FactualGate
from lunaris_video.models import GroundedClaim, GroundingPacket, PacketKind
from lunaris_video.schemas import FRAMING_ONLY_SENTINEL, Beat, SceneContract, SceneContracts
from lunaris_video.style import video_global_style


def _packet(*claims: GroundedClaim) -> GroundingPacket:
    return GroundingPacket(kind=PacketKind.LESSON, claims=tuple(claims))


def _claim(claim_id: str, text: str) -> GroundedClaim:
    return GroundedClaim(id=claim_id, text=text, citation_id="cite", source_label="src")


def _scene(*, sources: list[str], narration: str, scene_id: str = "S1_scene") -> SceneContract:
    return SceneContract(
        id=scene_id,
        archetype="process/flow",
        narration=narration,
        objects=["a diagram"],
        beats=[Beat(id="b1", action="something happens", narration=narration)],
        sources=sources,
        duration_s=12,
    )


def _contract(*scenes: SceneContract) -> SceneContracts:
    return SceneContracts(
        topic="Sorting",
        audience="learners",
        visual_archetypes_used=["process/flow"],
        asset_strategy="tier-a procedural",
        global_style=video_global_style(),
        scenes=list(scenes),
    )


def test_a_grounded_figure_present_in_a_cited_claim_passes() -> None:
    # Arrange — the narration's only figure (O(n log n) has none; 8 is the count) is in claim c1.
    packet = _packet(_claim("c1", "Merge sort sorts 8 elements in 24 comparisons."))
    contract = _contract(
        _scene(sources=["c1"], narration="Watch it sort 8 elements in 24 comparisons.")
    )

    # Act / Assert — no smuggling: every narrated figure is in the cited claim, no violations.
    assert FactualGate().check(contract, packet) == {}


def test_a_figure_supported_by_the_second_of_two_cited_claims_passes() -> None:
    # Arrange — the supporting claim is c2, not the first one cited: support is the UNION of all
    # cited claims, so the gate must not stop at c1.
    packet = _packet(
        _claim("c1", "Merge sort is a divide-and-conquer algorithm."),
        _claim("c2", "It was tested on 1,000 data sets."),
    )
    contract = _contract(
        _scene(sources=["c1", "c2"], narration="We tested merge sort on 1000 data sets.")
    )

    # Act / Assert — 1000 == 1,000 after comma-normalization, found in c2.
    assert FactualGate().check(contract, packet) == {}


def test_a_grounded_figure_off_from_its_claim_degrades_not_fails() -> None:
    # Arrange — the claim says 8; the narration says 80. Set membership is exact: "8" != "80". The
    # scene IS grounded (cites c1), so the extra figure is a MINOR violation — degrade, never raise.
    packet = _packet(_claim("c1", "Merge sort sorts 8 elements."))
    contract = _contract(_scene(sources=["c1"], narration="Merge sort sorts 80 elements."))

    # Act — the gate records the violation against the scene instead of raising.
    violations = FactualGate().check(contract, packet)

    # Assert — S1_scene is flagged; the unsupported figure (80, not 8) is named in its message.
    assert list(violations) == ["S1_scene"]
    message = " ".join(violations["S1_scene"])
    assert "80" in message
    assert "8 " not in message  # the supported figure is not flagged


def test_a_grounded_scene_smuggling_a_figure_degrades_not_fails() -> None:
    # Arrange — the scene cites c1 (which says nothing about 99%) but narrates "99% faster". A
    # grounded scene's extra figure is a MINOR violation under the severity-tiered policy.
    packet = _packet(_claim("c1", "Merge sort runs in O(n log n) time."))
    contract = _contract(
        _scene(sources=["c1"], narration="Merge sort is 99% faster than bubble sort.")
    )

    # Act
    violations = FactualGate().check(contract, packet)

    # Assert — the scene is flagged with the unsupported figure, and the video is NOT failed.
    assert "99" in " ".join(violations["S1_scene"])


def test_a_framing_only_scene_stating_a_figure_still_fails() -> None:
    # Arrange — a framing scene asserts NOTHING, so a number in it smuggles an empirical claim into
    # framing: a MAJOR violation that still hard-fails the job.
    contract = _contract(
        _scene(sources=[FRAMING_ONLY_SENTINEL], narration="Sorting touches 42 industries.")
    )

    # Act / Assert
    with pytest.raises(FactualGateError) as caught:
        FactualGate().check(contract, _packet())
    assert caught.value.scene_id == "S1_scene"
    assert "42" in caught.value.unsupported


def test_a_framing_only_scene_making_a_comparison_still_fails() -> None:
    # Arrange — a comparison ("faster than") is an empirical claim, forbidden in a framing scene: a
    # MAJOR violation.
    contract = _contract(
        _scene(sources=[FRAMING_ONLY_SENTINEL], narration="Merge sort is faster than bubble sort.")
    )

    # Act / Assert — a comparison fires the same error type with a distinct empty `unsupported`.
    with pytest.raises(FactualGateError) as caught:
        FactualGate().check(contract, _packet())
    assert caught.value.scene_id == "S1_scene"
    assert caught.value.unsupported == []


def test_a_clean_framing_only_scene_passes() -> None:
    # Arrange — pure framing: a hook with no numbers and no comparison.
    contract = _contract(
        _scene(
            sources=[FRAMING_ONLY_SENTINEL],
            narration="Sorting is everywhere, and it splits the work in half.",
        )
    )

    # Act / Assert — "half" is a process description, not a comparison; nothing to ground.
    assert FactualGate().check(contract, _packet()) == {}


def test_a_scene_citing_an_id_absent_from_the_packet_still_fails() -> None:
    # Arrange — a contract whose scene cites c7, which the packet never lists. A scene with no claim
    # to diff against is structurally ungrounded: a MAJOR violation (the planner rejects this, but
    # the gate must not trust a figure against a non-existent claim).
    packet = _packet(_claim("c1", "Merge sort runs in O(n log n) time."))
    contract = _contract(_scene(sources=["c7"], narration="It takes 5 steps."))

    # Act / Assert — an unknown claim is a structural defect: fail the scene, empty `unsupported`.
    with pytest.raises(FactualGateError) as caught:
        FactualGate().check(contract, packet)
    assert caught.value.scene_id == "S1_scene"
    assert caught.value.unsupported == []


def test_a_figure_in_a_beat_narration_is_also_recorded() -> None:
    # Arrange — the smuggled figure hides in a beat's narration, not the scene-level script; the
    # scene is grounded, so it's a MINOR violation the gate records.
    packet = _packet(_claim("c1", "Merge sort runs in O(n log n) time."))
    scene = SceneContract(
        id="S1_scene",
        archetype="process/flow",
        narration="Merge sort is efficient.",
        objects=["a diagram"],
        beats=[
            Beat(id="b1", action="intro", narration="Merge sort is efficient."),
            Beat(id="b2", action="reveal", narration="It beats bubble sort by 73%."),
        ],
        sources=["c1"],
        duration_s=12,
    )

    # Act / Assert — the gate reads beat narration too, so the hidden 73% is recorded (not raised).
    violations = FactualGate().check(_contract(scene), packet)
    assert "73" in " ".join(violations["S1_scene"])


def test_a_major_violation_anywhere_fails_the_whole_contract() -> None:
    # Arrange — two scenes: one grounded scene with a MINOR smuggled figure, and one framing-only
    # scene with a MAJOR smuggled figure. A major anywhere fails the job clean (the moat wins).
    packet = _packet(_claim("c1", "Merge sort runs in O(n log n) time."))
    grounded = _scene(sources=["c1"], narration="It is 99% faster.", scene_id="S1_grounded")
    framing = _scene(
        sources=[FRAMING_ONLY_SENTINEL], narration="Sorting saves 5 hours.", scene_id="S2_framing"
    )

    # Act / Assert — the framing scene's major violation raises despite the grounded scene's minor.
    with pytest.raises(FactualGateError) as caught:
        FactualGate().check(_contract(grounded, framing), packet)
    assert caught.value.scene_id == "S2_framing"

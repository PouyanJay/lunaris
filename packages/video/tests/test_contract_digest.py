"""digest_of: compact an upstream video's scene contract into the SiblingContractDigest the planner
gets — the topic it covers, its visual archetypes (for consistency), and the notable on-screen terms
it introduced (so a downstream lesson reuses them). Works for flat and chaptered contracts."""

from collections.abc import Callable

from lunaris_video.planning import digest_of
from lunaris_video.schemas import ChapteredSceneContracts, SceneContracts


def test_digest_pulls_topic_archetypes_and_key_terms(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange — the default lesson contract: topic "How merge sort works", archetypes with a dup,
    # scenes whose objects include "title card" and "indexed array of 8 cells".
    contract = make_lesson_contract(
        visual_archetypes_used=["process/flow", "process/flow", "data/array"]
    )

    # Act
    digest = digest_of("Sorting basics", contract)

    # Assert — the provider-supplied title, the contract topic as "covers", deduped archetypes, and
    # the on-screen objects as reusable key terms.
    assert digest.lesson_title == "Sorting basics"
    assert digest.covers == "How merge sort works"
    assert digest.archetypes == ("process/flow", "data/array")  # order-preserving dedup
    assert "title card" in digest.key_terms
    assert "indexed array of 8 cells" in digest.key_terms


def test_digest_caps_key_terms_and_dedupes_across_scenes(
    make_lesson_contract: Callable[..., SceneContracts],
    make_scene: Callable[..., object],
) -> None:
    # Arrange — many objects across scenes, with a repeat, exceeding the cap.
    busy = make_lesson_contract(
        scenes=[
            make_scene(1, "a", objects=[f"obj{i}" for i in range(7)] + ["shared"]),
            make_scene(2, "b", objects=["shared"] + [f"obj{i}" for i in range(7, 12)]),
        ]
    )

    # Act
    digest = digest_of("Busy lesson", busy)

    # Assert — deduped ("shared" once) and capped to a compact list.
    assert digest.key_terms.count("shared") == 1
    assert len(digest.key_terms) <= 8


def test_digest_handles_a_chaptered_overview_contract(
    make_chaptered_contract: Callable[..., ChapteredSceneContracts],
) -> None:
    # Arrange — a chaptered (overview) contract flattens its chapters' scenes; the digest reads the
    # same fields without caring about the chaptered shape.
    contract = make_chaptered_contract()

    # Act
    digest = digest_of("Course overview", contract)

    # Assert — the on-screen objects flatten across the chapters' scenes into key_terms.
    assert digest.covers == contract.topic
    assert "title card" in digest.key_terms

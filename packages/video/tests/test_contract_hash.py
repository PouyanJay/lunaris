"""Contract-hash tests: the hash is the regeneration cache key (plan principle 5), so it must be
stable for equal contracts, insensitive to construction order, and sensitive to semantic change."""

import re
from collections.abc import Callable

from lunaris_video.hashing import contract_hash
from lunaris_video.schemas import ChapteredSceneContracts, SceneContracts


def test_equal_contracts_hash_identically(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange — two independently constructed, equal contracts.
    first, second = make_lesson_contract(), make_lesson_contract()

    # Act / Assert — a re-enqueued unchanged contract must hit the artifact cache.
    assert contract_hash(first) == contract_hash(second)
    assert re.fullmatch(r"[0-9a-f]{64}", contract_hash(first))


def test_hash_survives_a_json_round_trip(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange
    contract = make_lesson_contract()

    # Act
    restored = SceneContracts.model_validate_json(contract.model_dump_json())

    # Assert — the hash of a contract loaded back from storage equals the original's.
    assert contract_hash(restored) == contract_hash(contract)


def test_hash_ignores_field_construction_order(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange — reverse the outer key order to prove canonicalization makes the digest
    # independent of how the payload was assembled.
    payload = make_lesson_contract().model_dump(mode="json")
    reordered = dict(reversed(list(payload.items())))

    # Act
    from_reordered = SceneContracts.model_validate(reordered)

    # Assert
    assert contract_hash(from_reordered) == contract_hash(make_lesson_contract())


def test_semantic_change_changes_the_hash(
    make_lesson_contract: Callable[..., SceneContracts],
) -> None:
    # Arrange
    original = make_lesson_contract()
    retopiced = make_lesson_contract(topic="How quicksort works")

    # Act / Assert — a changed contract must NOT reuse stale artifacts.
    assert contract_hash(original) != contract_hash(retopiced)


def test_equal_chaptered_contracts_hash_identically(
    make_chaptered_contract: Callable[..., ChapteredSceneContracts],
) -> None:
    # Arrange — two independently constructed, equal chaptered contracts.
    first, second = make_chaptered_contract(), make_chaptered_contract()

    # Act / Assert — the chaptered shape dispatches through the same cache-key space.
    assert contract_hash(first) == contract_hash(second)

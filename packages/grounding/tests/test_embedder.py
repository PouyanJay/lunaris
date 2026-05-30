import math

import pytest
from lunaris_grounding import StubEmbedder


async def test_embedding_is_deterministic_for_same_text() -> None:
    # Arrange
    embedder = StubEmbedder()

    # Act
    first = await embedder.embed(["binary search halves the array each step"])
    second = await embedder.embed(["binary search halves the array each step"])

    # Assert
    assert first == second


async def test_embedding_has_requested_dimension_and_is_unit_length() -> None:
    # Arrange
    embedder = StubEmbedder(dim=128)

    # Act
    [vector] = await embedder.embed(["a non-empty sentence with several tokens"])

    # Assert
    assert len(vector) == 128
    assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0, rel_tol=1e-9)


async def test_shared_vocabulary_scores_higher_than_unrelated_text() -> None:
    # Arrange — a claim and a paraphrase share tokens; an unrelated text does not
    embedder = StubEmbedder(dim=256)
    claim, paraphrase, unrelated = await embedder.embed(
        [
            "merge sort divides the list and merges sorted halves",
            "merge sort splits the list then merges the sorted halves back",
            "photosynthesis converts sunlight into chemical energy in plants",
        ]
    )

    # Act
    related_score = _dot(claim, paraphrase)
    unrelated_score = _dot(claim, unrelated)

    # Assert — cosine (unit vectors → dot) is meaningfully higher for the paraphrase
    assert related_score > unrelated_score
    assert related_score > 0.3


async def test_empty_input_returns_no_vectors() -> None:
    assert await StubEmbedder().embed([]) == []


def test_non_positive_dimension_is_rejected() -> None:
    with pytest.raises(ValueError):
        StubEmbedder(dim=0)


def _dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))

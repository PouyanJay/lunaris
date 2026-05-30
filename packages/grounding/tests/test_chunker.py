import pytest
from lunaris_grounding import chunk_text


def test_short_text_is_a_single_normalised_chunk() -> None:
    # Arrange / Act
    chunks = chunk_text("  binary   search\nis logarithmic  ")

    # Assert — whitespace collapsed, one chunk
    assert chunks == ["binary search is logarithmic"]


def test_long_text_splits_into_multiple_chunks_within_the_limit() -> None:
    # Arrange — 50 words, well over a small char budget
    text = " ".join(f"word{i}" for i in range(50))

    # Act
    chunks = chunk_text(text, max_chars=60, overlap=10)

    # Assert
    assert len(chunks) > 1
    assert all(len(chunk) <= 60 for chunk in chunks)


def test_chunks_overlap_to_preserve_context() -> None:
    # Arrange
    text = " ".join(f"token{i}" for i in range(40))

    # Act
    chunks = chunk_text(text, max_chars=80, overlap=20)

    # Assert — a token from the tail of one chunk reappears at the head of the next
    first_tail = chunks[0].split()[-1]
    assert first_tail in chunks[1].split()


def test_words_are_not_split_mid_token() -> None:
    # Arrange
    text = "alpha bravo charlie delta echo foxtrot golf hotel india juliet"

    # Act
    chunks = chunk_text(text, max_chars=20, overlap=5)

    # Assert — every emitted token is one of the originals (no fragments)
    originals = set(text.split())
    assert all(token in originals for chunk in chunks for token in chunk.split())


def test_blank_text_yields_no_chunks() -> None:
    assert chunk_text("   \n  ") == []


def test_invalid_overlap_is_rejected() -> None:
    with pytest.raises(ValueError):
        chunk_text("some text", max_chars=50, overlap=50)

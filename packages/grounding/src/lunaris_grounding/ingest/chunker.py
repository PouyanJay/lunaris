_DEFAULT_MAX_CHARS = 800
_DEFAULT_OVERLAP = 100


def chunk_text(
    text: str, *, max_chars: int = _DEFAULT_MAX_CHARS, overlap: int = _DEFAULT_OVERLAP
) -> list[str]:
    """Split source text into overlapping, word-aligned chunks.

    Deterministic and dependency-free: packs whole words up to ``max_chars`` (so tokens are
    never split mid-word), then carries roughly ``overlap`` characters of trailing words
    into the next chunk to preserve cross-boundary context. A single word longer than
    ``max_chars`` becomes its own chunk. Returns ``[]`` for blank input.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if not 0 <= overlap < max_chars:
        raise ValueError("overlap must be in [0, max_chars)")

    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(words):
        cursor, length = start, 0
        while cursor < len(words):
            word_cost = len(words[cursor]) + (1 if cursor > start else 0)
            if length + word_cost > max_chars and cursor > start:
                break
            length += word_cost
            cursor += 1
        chunks.append(" ".join(words[start:cursor]))
        if cursor >= len(words):
            break
        start = _overlap_start(words, start, cursor, overlap)
    return chunks


def _overlap_start(words: list[str], start: int, end: int, overlap: int) -> int:
    """Step back whole words from ``end`` until ~``overlap`` chars repeat.

    Always returns a value in ``(start, end]`` so the outer loop makes progress — even for a
    lone oversized word (``end == start + 1``), where it returns ``end`` (no overlap).
    """
    carried, index = 0, end - 1
    while index > start + 1 and carried < overlap:
        carried += len(words[index]) + 1
        index -= 1
    return max(index, start + 1)

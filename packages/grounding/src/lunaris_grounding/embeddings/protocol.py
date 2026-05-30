from typing import Protocol


class IEmbedder(Protocol):
    """Turns text into dense vectors for similarity search (D2).

    The MVP provider is Voyage AI (``voyage-3.5``, 1024 dims) — Anthropic's recommended
    embeddings pairing — but any provider is substitutable behind this Protocol. Returns
    one vector per input text, in order. Implementations should be deterministic for a
    fixed input so the corpus and the query embed into the same space.
    """

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

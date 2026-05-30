import hashlib
import math
import re

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class StubEmbedder:
    """Deterministic feature-hashing embedder — no API key, no network.

    Each token is hashed into a dimension (with a hashed sign) and accumulated, then the
    vector is L2-normalised. Texts that share tokens land on overlapping dimensions, so
    cosine similarity is meaningful: a claim and the source it paraphrases score high, an
    unrelated source scores low. That lets the whole retrieve → assess → verify pathway be
    exercised offline, while the real space comes from a hosted model in production.
    """

    def __init__(self, dim: int = 64) -> None:
        if dim <= 0:
            raise ValueError("embedding dimension must be positive")
        self._dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self._dim
        for token in _TOKEN_RE.findall(text.lower()):
            digest = int(hashlib.sha256(token.encode()).hexdigest(), 16)
            index = digest % self._dim
            sign = 1.0 if (digest >> 8) & 1 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]

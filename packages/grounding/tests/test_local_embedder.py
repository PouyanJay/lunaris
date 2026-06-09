"""The keyless embeddings fallback: when no Voyage key is set, embed over a local OpenAI-compatible
endpoint (bge-large-en-v1.5, natively 1024-d to match the corpus), with no API key."""

from typing import ClassVar

import langchain_openai
from lunaris_grounding import LocalEmbedder


class _SpyOpenAIEmbeddings:
    """Captures the kwargs the embeddings client is built with (no network)."""

    last_kwargs: ClassVar[dict[str, object]] = {}

    def __init__(self, **kwargs: object) -> None:
        type(self).last_kwargs = kwargs

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 1024 for _ in texts]


async def test_local_embedder_uses_a_keyless_openai_compatible_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(langchain_openai, "OpenAIEmbeddings", _SpyOpenAIEmbeddings)
    monkeypatch.delenv("LUNARIS_FALLBACK_EMBEDDINGS_BASE_URL", raising=False)
    monkeypatch.delenv("LUNARIS_FALLBACK_EMBEDDINGS_MODEL", raising=False)

    vectors = await LocalEmbedder().embed(["binary search halves the array"])

    kwargs = _SpyOpenAIEmbeddings.last_kwargs
    assert kwargs["base_url"] == "http://localhost:8080/v1"
    assert kwargs["model"] == "bge-large-en-v1.5"
    assert kwargs["dimensions"] == 1024  # matches the vector(1024) corpus column
    assert kwargs["api_key"] == "no-key-required"  # a placeholder, not a secret
    assert len(vectors[0]) == 1024


async def test_local_embedder_returns_no_vectors_for_empty_input() -> None:
    # No client is constructed and no call made for an empty batch.
    assert await LocalEmbedder().embed([]) == []


async def test_local_embedder_honours_env_overrides(monkeypatch) -> None:
    monkeypatch.setattr(langchain_openai, "OpenAIEmbeddings", _SpyOpenAIEmbeddings)
    monkeypatch.setenv("LUNARIS_FALLBACK_EMBEDDINGS_BASE_URL", "http://gpu-host:9999/v1")
    monkeypatch.setenv("LUNARIS_FALLBACK_EMBEDDINGS_MODEL", "gte-large")

    await LocalEmbedder().embed(["x"])

    assert _SpyOpenAIEmbeddings.last_kwargs["base_url"] == "http://gpu-host:9999/v1"
    assert _SpyOpenAIEmbeddings.last_kwargs["model"] == "gte-large"

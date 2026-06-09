"""T2 — embeddings are no longer key-gated: the composition root picks Voyage when its key is set,
else the keyless local nano fallback, and the cuts-everything retriever stub no longer fires just
because the embeddings key is missing (a corpus present → real grounding on the local embedder)."""

import pytest
from lunaris_agent.composition import _embedder_from_env, _retriever_from_env
from lunaris_grounding import LocalEmbedder, PgVectorRetriever, VoyageEmbedder


def test_embedder_is_voyage_when_the_key_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBEDDINGS_API_KEY", "pa-embed-key")

    assert isinstance(_embedder_from_env(), VoyageEmbedder)


def test_embedder_falls_back_to_local_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EMBEDDINGS_API_KEY", raising=False)

    assert isinstance(_embedder_from_env(), LocalEmbedder)


def test_retriever_is_real_with_a_corpus_even_without_an_embeddings_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The corpus (Supabase) is present but no Voyage key — grounding runs on the keyless local
    # embedder rather than collapsing to the conservative cut-everything stub.
    monkeypatch.setenv("SUPABASE_URL", "http://supabase.test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role")
    monkeypatch.delenv("EMBEDDINGS_API_KEY", raising=False)

    retriever = _retriever_from_env()

    assert isinstance(retriever, PgVectorRetriever)
    assert isinstance(retriever._embedder, LocalEmbedder)


def test_retriever_is_none_without_a_corpus(monkeypatch: pytest.MonkeyPatch) -> None:
    # No corpus store at all → None (the verifier then uses the cut-everything stub upstream).
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    assert _retriever_from_env() is None

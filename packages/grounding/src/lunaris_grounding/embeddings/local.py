import os

from lunaris_runtime.resilience import retry_on_rate_limit

_DEFAULT_MODEL = "bge-large-en-v1.5"
_DEFAULT_BASE_URL = "http://localhost:8080/v1"
# The grounding_documents pgvector column is fixed at vector(1024). bge-large-en-v1.5 is natively
# 1024-d, so we pin 1024 to assert that contract (the keyless embedder MUST be a 1024-d model);
# llama.cpp returns the model's native dimension and ignores an extra request field, so this stays a
# belt-and-suspenders guard, not a truncation. A corpus must embed + query in one model/space.
_CORPUS_DIMS = 1024
# The local endpoint ignores the key, but the OpenAI client requires a non-empty value. A
# placeholder, NOT a secret — the keyless embeddings fallback needs no API key.
_PLACEHOLDER_KEY = "no-key-required"


class LocalEmbedder:
    """Keyless self-hosted embedder over an OpenAI-compatible endpoint (bge-large-en-v1.5 default).

    The fallback when no Voyage key is set: a local llama.cpp server serves the model, reached at
    ``/v1/embeddings`` with no API key. bge-large-en-v1.5 is a real, GGUF-available, natively 1024-d
    open model (MIT), matching the corpus's ``vector(1024)`` column. Base URL + model are read from
    env so the runtime/model is a one-line swap. Like ``VoyageEmbedder``, constructing it touches no
    network — the client materialises on the first embed call.

    Note: the keyless embedder and Voyage are different vector spaces, so a corpus must be ingested
    AND queried with the same embedder; switching providers means re-grounding the course.
    """

    def __init__(self, model_name: str | None = None, *, base_url: str | None = None) -> None:
        self._model_name = model_name or os.getenv(
            "LUNARIS_FALLBACK_EMBEDDINGS_MODEL", _DEFAULT_MODEL
        )
        self._base_url = base_url or os.getenv(
            "LUNARIS_FALLBACK_EMBEDDINGS_BASE_URL", _DEFAULT_BASE_URL
        )
        self._client: object | None = None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._client is None:
            from langchain_openai import OpenAIEmbeddings

            self._client = OpenAIEmbeddings(
                model=self._model_name,
                base_url=self._base_url,
                api_key=_PLACEHOLDER_KEY,
                dimensions=_CORPUS_DIMS,
            )
        return await retry_on_rate_limit(lambda: self._client.aembed_documents(texts))  # type: ignore[attr-defined]

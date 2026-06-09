import os

from lunaris_runtime.resilience import retry_on_rate_limit

_DEFAULT_MODEL = "voyage-4-nano"
_DEFAULT_BASE_URL = "http://localhost:8080/v1"
# The grounding_documents pgvector column is fixed at vector(1024); voyage-4-nano is Matryoshka, so
# request 1024 dims to match it (a corpus must embed + query in one model/space — see the class).
_CORPUS_DIMS = 1024
# The local endpoint ignores the key, but the OpenAI client requires a non-empty value. A
# placeholder, NOT a secret — the keyless embeddings fallback needs no API key.
_PLACEHOLDER_KEY = "no-key-required"


class LocalEmbedder:
    """Keyless self-hosted embedder over an OpenAI-compatible endpoint (voyage-4-nano by default).

    The fallback when no Voyage key is set: a local llama.cpp / ``bonsai`` server serves the model,
    reached at ``/v1/embeddings`` with no API key. Output is pinned to 1024 dims to match the
    corpus's ``vector(1024)`` column. Base URL + model are read from env so the runtime/model is a
    one-line swap. Like ``VoyageEmbedder``, constructing it touches no network — the client
    materialises on the first embed call.

    Note: nano and Voyage are different vector spaces, so a corpus must be ingested AND queried with
    the same embedder; switching providers means re-grounding the course.
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

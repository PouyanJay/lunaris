from lunaris_runtime.credentials import resolve_secret
from lunaris_runtime.metering import record_cost
from lunaris_runtime.resilience import retry_on_rate_limit
from lunaris_runtime.schema import CostProvider, CostUnit

_DEFAULT_MODEL = "voyage-3.5"
_API_KEY_ENV = "EMBEDDINGS_API_KEY"
# Voyage bills per input token; the client doesn't return a token count, so approximate from
# characters (~4 chars/token). Voyage is a negligible slice of build cost, so an approximation here
# is proportionate — and honest about being one.
_CHARS_PER_TOKEN = 4


class VoyageEmbedder:
    """Voyage AI embedder (D2 default) with a lazily-constructed client.

    Constructing it touches no network and needs no key, so it can be wired in a
    composition root unconditionally; the client (and the key requirement) only
    materialise on the first ``embed`` call. Rate-limit responses are absorbed by the
    shared backoff helper.
    """

    def __init__(
        self, model_name: str = _DEFAULT_MODEL, *, api_key_env: str = _API_KEY_ENV
    ) -> None:
        self._model_name = model_name
        self._api_key_env = api_key_env
        self._client: object | None = None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._client is None:
            from langchain_voyageai import VoyageAIEmbeddings

            api_key = resolve_secret(self._api_key_env)
            if not api_key:
                raise RuntimeError(f"{self._api_key_env} is not set; cannot embed with Voyage AI")
            self._client = VoyageAIEmbeddings(model=self._model_name, api_key=api_key)
        vectors = await retry_on_rate_limit(lambda: self._client.aembed_documents(texts))  # type: ignore[attr-defined]
        approx_tokens = sum(len(text) for text in texts) / _CHARS_PER_TOKEN
        record_cost(
            component="embeddings",
            provider=CostProvider.VOYAGE,
            model=self._model_name,
            usage={CostUnit.INPUT_TOKENS: approx_tokens},
        )
        return vectors

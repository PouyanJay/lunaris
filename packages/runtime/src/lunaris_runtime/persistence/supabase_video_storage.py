import asyncio
import os

from .guard import guard
from .persistence_error import PersistenceError

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
_BUCKET = "course-videos"


class SupabaseVideoStorage:
    """The production video-artifact store: the private ``course-videos`` Supabase bucket.

    Same lazy service-role client pattern as the other Supabase stores. Uploads are upserts so a
    regenerate overwrites the same artifact path instead of 409-ing; playback URLs are short-lived
    signed URLs (the bucket is private — the signed URL, not a storage policy, is what the
    reader's player presents).
    """

    def __init__(
        self,
        *,
        url_env: str = _URL_ENV,
        service_key_env: str = _SERVICE_KEY_ENV,
        client: object | None = None,
    ) -> None:
        self._url_env = url_env
        self._service_key_env = service_key_env
        # An injected client (tests) skips lazy construction; production builds from env on
        # first use so the composition root can construct this unconditionally.
        self._client = client

    def _ensure_client(self) -> object:
        if self._client is None:
            from supabase import create_client

            url = os.environ.get(self._url_env)
            key = os.environ.get(self._service_key_env)
            if not url or not key:
                raise RuntimeError(
                    f"{self._url_env} / {self._service_key_env} not set; cannot reach storage"
                )
            self._client = create_client(url, key)
        return self._client

    @guard("course-videos upload")
    async def upload(self, *, path: str, data: bytes, content_type: str) -> None:
        client = self._ensure_client()

        def _run() -> object:
            bucket = client.storage.from_(_BUCKET)  # type: ignore[attr-defined]
            return bucket.upload(path, data, {"content-type": content_type, "upsert": "true"})

        await asyncio.to_thread(_run)

    @guard("course-videos signed url")
    async def signed_url(self, *, path: str, expires_in_seconds: int = 3600) -> str:
        client = self._ensure_client()

        def _run() -> object:
            bucket = client.storage.from_(_BUCKET)  # type: ignore[attr-defined]
            return bucket.create_signed_url(path, expires_in_seconds)

        response = await asyncio.to_thread(_run)
        # supabase-py has shipped both key spellings across versions; accept either.
        url = response.get("signedURL") or response.get("signedUrl")  # type: ignore[union-attr]
        if not url:
            raise PersistenceError(f"no signed URL returned for {path!r}")
        return str(url)

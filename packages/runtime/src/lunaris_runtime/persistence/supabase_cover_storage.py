import asyncio
import os

from .cover_image_transform import CoverImageTransform
from .guard import guard
from .persistence_error import PersistenceError

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
_BUCKET = "course-covers"


class SupabaseCoverStorage:
    """The production cover-image store: the private ``course-covers`` Supabase bucket.

    Same lazy service-role client pattern as the other Supabase stores. Uploads are upserts so a
    regenerate overwrites the same artifact path instead of 409-ing; display URLs are short-lived
    signed URLs (the bucket is private — the signed URL, not a storage policy, is what the reader
    presents).
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

    @guard("course-covers upload")
    async def upload(self, *, path: str, data: bytes, content_type: str) -> None:
        client = self._ensure_client()

        def _run() -> object:
            bucket = client.storage.from_(_BUCKET)  # type: ignore[attr-defined]
            # A cover object is immutable: it lives under a per-job-id path, and a regenerate writes
            # a NEW path, so its bytes never change in place. Stamp a long immutable Cache-Control
            # so a client holding a valid signed URL serves it from cache (the service worker caches
            # by path regardless, but this also helps plain browsers and any CDN in front).
            return bucket.upload(
                path,
                data,
                {
                    "content-type": content_type,
                    "cache-control": "public, max-age=31536000, immutable",
                    "upsert": "true",
                },
            )

        await asyncio.to_thread(_run)

    @guard("course-covers signed url")
    async def signed_url(
        self,
        *,
        path: str,
        expires_in_seconds: int = 3600,
        transform: CoverImageTransform | None = None,
    ) -> str:
        client = self._ensure_client()
        # supabase-py signs the transform INTO the token (storage-api ignores query params on a
        # signed URL), so a resized derivative is a distinct mint — not the master URL with params.
        options = None if transform is None else {"transform": transform.as_options()}

        def _run() -> object:
            bucket = client.storage.from_(_BUCKET)  # type: ignore[attr-defined]
            return bucket.create_signed_url(path, expires_in_seconds, options)

        response = await asyncio.to_thread(_run)
        # supabase-py has shipped both key spellings across versions; accept either.
        url = response.get("signedURL") or response.get("signedUrl")  # type: ignore[union-attr]
        if not url:
            raise PersistenceError(f"no signed URL returned for {path!r}")
        return str(url)

    @guard("course-covers download")
    async def download(self, *, path: str) -> bytes:
        client = self._ensure_client()

        def _run() -> object:
            bucket = client.storage.from_(_BUCKET)  # type: ignore[attr-defined]
            return bucket.download(path)

        data = await asyncio.to_thread(_run)
        if not isinstance(data, bytes | bytearray):
            raise PersistenceError(
                f"download for {path!r} returned {type(data).__name__}, not bytes"
            )
        return bytes(data)

    @guard("course-covers delete")
    async def delete(self, *, paths: list[str]) -> None:
        if not paths:
            return  # nothing to remove — don't round-trip an empty batch

        client = self._ensure_client()

        def _run() -> object:
            bucket = client.storage.from_(_BUCKET)  # type: ignore[attr-defined]
            return bucket.remove(paths)

        await asyncio.to_thread(_run)

import asyncio
import hashlib
from urllib.parse import urlsplit

import httpx
from lunaris_live.corpus.video.models.measured_media import MeasuredMedia
from lunaris_live.corpus.video.mp4_duration import mp4_duration
from lunaris_runtime.persistence.video_storage_protocol import IVideoStorage


class SignedVideoMedia:
    """Inspect only storage-issued media; no redirects, bounded transfer and movie metadata."""

    def __init__(self, storage: IVideoStorage, *, client: httpx.AsyncClient | None = None) -> None:
        self._storage = storage
        self._client = client

    async def inspect(self, *, path: str, max_bytes: int) -> MeasuredMedia:
        async with asyncio.timeout(30):
            url = await self._storage.signed_url(path=path, expires_in_seconds=60)
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("unsupported storage URL")
            if self._client is not None:
                return await self._read(self._client, url, max_bytes)
            async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
                return await self._read(client, url, max_bytes)

    async def _read(self, client: httpx.AsyncClient, url: str, max_bytes: int) -> MeasuredMedia:
        data = bytearray()
        async with client.stream(
            "GET", url, follow_redirects=False, headers={"Accept-Encoding": "identity"}
        ) as response:
            if response.status_code != 200:
                raise ValueError("media unavailable")
            if response.headers.get("content-encoding", "identity") != "identity":
                raise ValueError("encoded media unsupported")
            length = response.headers.get("content-length")
            if length is not None and int(length) > max_bytes:
                raise ValueError("media exceeds byte budget")
            async for chunk in response.aiter_bytes(chunk_size=65536):
                if len(data) + len(chunk) > max_bytes:
                    raise ValueError("media exceeds byte budget")
                data.extend(chunk)
        return MeasuredMedia(mp4_duration(data), hashlib.sha256(data).hexdigest(), len(data))

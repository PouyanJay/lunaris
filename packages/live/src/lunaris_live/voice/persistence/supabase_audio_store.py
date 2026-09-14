import os
from asyncio import timeout

import httpx

from ..error import VoiceError
from .validate_pcm import validate_pcm


class SupabaseVoiceAudioStore:
    """Private Storage REST, with cancellable total deadlines (no background upload threads)."""

    def __init__(
        self,
        *,
        url: str | None = None,
        key: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._url, self._key, self._client = url, key, client

    def _url_for(self, path: str) -> str:
        url = self._url or os.environ.get("SUPABASE_URL")
        if not url:
            raise VoiceError("Voice storage is unavailable.", status_code=503)
        return f"{url.rstrip('/')}/storage/v1/{path}"

    async def _request(self, request: httpx.Request) -> bytes:
        key = self._key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not key:
            raise VoiceError("Voice storage is unavailable.", status_code=503)
        request.headers.update({"Authorization": f"Bearer {key}", "apikey": key})
        client = self._client or httpx.AsyncClient(timeout=60)
        try:
            async with timeout(60):
                response = await client.send(request)
                response.raise_for_status()
                return response.content
        except (httpx.HTTPError, TimeoutError):
            raise VoiceError("Voice storage is unavailable.", status_code=503) from None
        finally:
            if self._client is None:
                await client.aclose()

    async def put(self, key: str, pcm: bytes) -> None:
        validate_pcm(key, pcm)
        request = httpx.Request(
            "POST",
            self._url_for(f"object/live-voice/{key}"),
            content=pcm,
            headers={"Content-Type": "audio/pcm", "x-upsert": "false"},
        )
        await self._request(request)

    async def get(self, key: str) -> bytes:
        validate_pcm(key)
        request = httpx.Request("GET", self._url_for(f"object/authenticated/live-voice/{key}"))
        pcm = await self._request(request)
        validate_pcm(key, pcm)
        return pcm

    async def delete(self, key: str) -> None:
        validate_pcm(key)
        request = httpx.Request(
            "DELETE", self._url_for("object/live-voice"), json={"prefixes": [key]}
        )
        await self._request(request)

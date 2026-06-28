import asyncio
import time
from typing import Any

import httpx

_TOKEN_RESOURCE = "https://management.azure.com/"
# Refresh the cached token this many seconds before it actually expires.
_TOKEN_SKEW_SECONDS = 300.0


class ArmClient:
    """A thin Azure Resource Manager client authed by the container app's managed identity.

    Azure Container Apps injects ``IDENTITY_ENDPOINT`` + ``IDENTITY_HEADER``; we exchange them for
    an ARM bearer token (cached until shortly before expiry) and call ARM REST over httpx — no
    ``azure-*`` SDK. The IMDS metadata IP is deliberately not used (it is SSRF-blocked elsewhere);
    the env-injected MSI endpoint is the supported path on ACA.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        identity_endpoint: str,
        identity_header: str,
        client_id: str,
    ) -> None:
        self._client = client
        self._identity_endpoint = identity_endpoint
        self._identity_header = identity_header
        self._client_id = client_id
        self._token: str | None = None
        self._expires_at = 0.0
        # Serialize refreshes so concurrent ARM calls (e.g. the parallel per-app metric reads) don't
        # each stampede the MSI endpoint for a token.
        self._token_lock = asyncio.Lock()

    async def _token_value(self) -> str:
        async with self._token_lock:
            return await self._refresh_token_if_needed()

    async def _refresh_token_if_needed(self) -> str:
        now = time.time()
        if self._token is not None and now < self._expires_at - _TOKEN_SKEW_SECONDS:
            return self._token
        response = await self._client.get(
            self._identity_endpoint,
            params={
                "resource": _TOKEN_RESOURCE,
                "api-version": "2019-08-01",
                "client_id": self._client_id,
            },
            headers={"X-IDENTITY-HEADER": self._identity_header},
        )
        response.raise_for_status()
        payload = response.json()
        self._token = payload["access_token"]
        self._expires_at = now + float(payload.get("expires_in", 3600))
        return self._token

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call ARM with the managed-identity bearer token. Raises on a non-2xx response; returns
        the parsed JSON body (or ``{}`` for an empty body, e.g. a start/stop action)."""
        token = await self._token_value()
        response = await self._client.request(
            method,
            url,
            params=params,
            json=json,
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        return response.json() if response.content else {}

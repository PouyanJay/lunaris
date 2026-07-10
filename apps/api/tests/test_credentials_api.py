"""Integration tests for the BYOK credentials API (Phase 2, T5) — per-user, authed provider keys.

Hermetic (mirrors test_me_api / test_user_isolation_api): each user mints an HS256 token signed with
the configured secret; BYOK is turned on via a base64 master key in Settings; the store is an
injected in-memory one and the validator accepts (no network). Proves the real router → vault →
cipher → store path, per-user isolation, the masked surface, and the auth/BYOK gates.
"""

import base64
import time
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import jwt
import pytest
from _doubles import RejectingValidator
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import get_credential_store, get_secret_validator
from lunaris_api.secrets import (
    AcceptingValidator,
    CompositeSecretValidator,
    ElevenLabsProbeValidator,
    InMemoryCredentialStore,
    ISecretValidator,
)
from lunaris_runtime.logging import clear_correlation

_JWT_SECRET = "test-jwt-secret-at-least-32-bytes-long-xxxx"
_MASTER_KEY_B64 = base64.b64encode(bytes(32)).decode()
_USER_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_USER_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _auth(sub: str) -> dict[str, str]:
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": sub,
            "aud": "authenticated",
            "role": "authenticated",
            "iat": now,
            "exp": now + 3600,
        },
        _JWT_SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def _build_client(
    tmp_path: Path,
    *,
    jwt_secret: str | None = _JWT_SECRET,
    master_key: str | None = _MASTER_KEY_B64,
    validator: ISecretValidator | None = None,
) -> httpx.AsyncClient:
    clear_correlation()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        supabase_jwt_secret=jwt_secret,
        key_enc_master=master_key,
    )
    # One shared in-memory store across requests (per-user keying gives the isolation).
    store = InMemoryCredentialStore()
    app.dependency_overrides[get_credential_store] = lambda: store
    app.dependency_overrides[get_secret_validator] = lambda: validator or AcceptingValidator()
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    async with _build_client(tmp_path) as http_client:
        yield http_client


async def test_set_then_list_shows_the_key_masked(client: httpx.AsyncClient) -> None:
    # Act — set a key, then list.
    put = await client.put(
        "/api/credentials/anthropic", json={"value": "sk-ant-secret"}, headers=_auth(_USER_A)
    )
    listed = await client.get("/api/credentials", headers=_auth(_USER_A))

    # Assert — set returns the masked status; list shows it set with last4, never the value.
    assert put.status_code == 200
    assert put.json() == {"provider": "anthropic", "isSet": True, "last4": "cret"}
    by_provider = {row["provider"]: row for row in listed.json()}
    assert by_provider["anthropic"] == {"provider": "anthropic", "isSet": True, "last4": "cret"}
    assert by_provider["search"]["isSet"] is False
    # The V3 voice key rides the same router; the list always surfaces it (set or unset).
    assert by_provider["elevenlabs"]["isSet"] is False


async def test_elevenlabs_voice_key_sets_and_lists_through_the_same_route(
    client: httpx.AsyncClient,
) -> None:
    # Act — set the ElevenLabs voice key, then list.
    put = await client.put(
        "/api/credentials/elevenlabs", json={"value": "sk_eleven_secret"}, headers=_auth(_USER_A)
    )
    listed = await client.get("/api/credentials", headers=_auth(_USER_A))

    # Assert — same masked surface as every other provider.
    assert put.status_code == 200
    assert put.json() == {"provider": "elevenlabs", "isSet": True, "last4": "cret"}
    by_provider = {row["provider"]: row for row in listed.json()}
    assert by_provider["elevenlabs"] == {"provider": "elevenlabs", "isSet": True, "last4": "cret"}


async def test_keys_are_isolated_per_user(client: httpx.AsyncClient) -> None:
    # Arrange — A sets a key.
    await client.put(
        "/api/credentials/anthropic", json={"value": "a-key-1234"}, headers=_auth(_USER_A)
    )

    # Act — both users list.
    a_listed = await client.get("/api/credentials", headers=_auth(_USER_A))
    b_listed = await client.get("/api/credentials", headers=_auth(_USER_B))

    # Assert — A keeps their key; B sees nothing set (A's key is invisible to B).
    a_anthropic = next(r for r in a_listed.json() if r["provider"] == "anthropic")
    assert a_anthropic["isSet"] is True
    assert all(row["isSet"] is False for row in b_listed.json())


async def test_set_rotates_an_existing_key(client: httpx.AsyncClient) -> None:
    # Arrange — an initial key.
    await client.put(
        "/api/credentials/anthropic", json={"value": "old-0000"}, headers=_auth(_USER_A)
    )

    # Act — set again with a new value (rotation = upsert).
    await client.put(
        "/api/credentials/anthropic", json={"value": "new-1111"}, headers=_auth(_USER_A)
    )

    # Assert — one entry, the new last4 wins (no duplicate row).
    listed = [
        r
        for r in (await client.get("/api/credentials", headers=_auth(_USER_A))).json()
        if r["provider"] == "anthropic"
    ]
    assert len(listed) == 1
    assert listed[0]["last4"] == "1111"


async def test_delete_removes_only_the_callers_key(client: httpx.AsyncClient) -> None:
    # Arrange — both users set the same provider.
    await client.put("/api/credentials/search", json={"value": "a-1234"}, headers=_auth(_USER_A))
    await client.put("/api/credentials/search", json={"value": "b-5678"}, headers=_auth(_USER_B))

    # Act — A deletes theirs.
    deleted = await client.delete("/api/credentials/search", headers=_auth(_USER_A))

    # Assert — A's is gone; B's survives.
    assert deleted.status_code == 200
    assert deleted.json()["isSet"] is False
    a_listed = (await client.get("/api/credentials", headers=_auth(_USER_A))).json()
    b_listed = (await client.get("/api/credentials", headers=_auth(_USER_B))).json()
    a_search = next(r for r in a_listed if r["provider"] == "search")
    b_search = next(r for r in b_listed if r["provider"] == "search")
    assert a_search["isSet"] is False
    assert b_search["isSet"] is True


async def test_set_unknown_provider_is_404(client: httpx.AsyncClient) -> None:
    response = await client.put(
        "/api/credentials/cohere", json={"value": "k"}, headers=_auth(_USER_A)
    )
    assert response.status_code == 404


async def test_set_empty_value_is_400(client: httpx.AsyncClient) -> None:
    response = await client.put(
        "/api/credentials/anthropic", json={"value": ""}, headers=_auth(_USER_A)
    )
    assert response.status_code == 400


async def test_test_probe_reports_ok_for_a_good_key(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/credentials/anthropic/test", json={"value": "good-key"}, headers=_auth(_USER_A)
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True, "detail": None}


async def test_test_probe_reports_not_ok_for_a_bad_key(tmp_path: Path) -> None:
    # Arrange — a validator that rejects the key.
    async with _build_client(tmp_path, validator=RejectingValidator()) as client:
        # Act
        response = await client.post(
            "/api/credentials/anthropic/test", json={"value": "bad"}, headers=_auth(_USER_A)
        )

    # Assert — a probe is a query: 200 with ok=False + a safe detail, not an error.
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["detail"]


async def test_elevenlabs_probe_reports_not_ok_for_a_rejected_key(tmp_path: Path) -> None:
    # Arrange — the REAL ElevenLabs validator with an injected probe that 401s, so the Settings
    # "Test" button's whole path (router → composite → elevenlabs probe) is exercised end to end.
    async def reject(value: str) -> tuple[int, str]:
        return 401, "invalid_api_key"

    validator = CompositeSecretValidator([ElevenLabsProbeValidator(probe=reject)])
    async with _build_client(tmp_path, validator=validator) as client:
        # Act
        response = await client.post(
            "/api/credentials/elevenlabs/test", json={"value": "sk_bad"}, headers=_auth(_USER_A)
        )

    # Assert — a probe is a query: 200 with ok=False + a safe, value-free detail.
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "rejected" in body["detail"].lower()


async def test_anonymous_request_is_401(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/credentials")).status_code == 401


async def test_byok_disabled_returns_503(tmp_path: Path) -> None:
    # Arrange — auth on, but no master key ⇒ BYOK is off.
    async with _build_client(tmp_path, master_key=None) as client:
        # Act
        response = await client.get("/api/credentials", headers=_auth(_USER_A))

    # Assert — the feature is unavailable (503), not a silent empty list.
    assert response.status_code == 503

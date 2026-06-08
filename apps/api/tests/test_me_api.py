"""Integration tests for authenticated identity — ``GET /api/me`` verifies a Supabase Auth JWT and
returns the caller's user id, the foundation every per-user feature builds on.

Hermetic by design: the test mints its own HS256 token signed with the secret the API is configured
with — exactly what Supabase Auth does — so it exercises the real verification path (router →
dependency → verifier) with no live Supabase. The live end-to-end (real signup → token) is covered
separately and self-skips when the local stack is down.
"""

import time
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import jwt
import pytest
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_runtime.logging import clear_correlation

_JWT_SECRET = "test-jwt-secret-at-least-32-bytes-long-xxxx"
_TEST_USER_ID = "11111111-1111-1111-1111-111111111111"


def _mint_token(
    *,
    sub: str = _TEST_USER_ID,
    secret: str = _JWT_SECRET,
    exp_offset: int = 3600,
    aud: str = "authenticated",
) -> str:
    now = int(time.time())
    payload = {
        "sub": sub,
        "aud": aud,
        "role": "authenticated",
        "iat": now,
        "exp": now + exp_offset,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _build_client(jwt_secret: str | None, tmp_path: Path) -> httpx.AsyncClient:
    clear_correlation()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        supabase_jwt_secret=jwt_secret,
    )
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    async with _build_client(_JWT_SECRET, tmp_path) as http_client:
        yield http_client


async def test_get_me_valid_token_returns_user_id(client: httpx.AsyncClient) -> None:
    # Act
    response = await client.get("/api/me", headers={"Authorization": f"Bearer {_mint_token()}"})

    # Assert
    assert response.status_code == 200
    assert response.json() == {"userId": _TEST_USER_ID}


async def test_get_me_missing_token_returns_401(client: httpx.AsyncClient) -> None:
    # Act
    response = await client.get("/api/me")

    # Assert
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_get_me_malformed_authorization_header_returns_401(
    client: httpx.AsyncClient,
) -> None:
    # Arrange — a bare token with no "Bearer " scheme prefix
    headers = {"Authorization": _mint_token()}

    # Act
    response = await client.get("/api/me", headers=headers)

    # Assert
    assert response.status_code == 401


async def test_get_me_wrong_signature_returns_401(client: httpx.AsyncClient) -> None:
    # Arrange — signed with a secret the API is not configured with
    token = _mint_token(secret="a-different-secret-also-32-bytes-long-yyyy")

    # Act
    response = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

    # Assert
    assert response.status_code == 401


async def test_get_me_expired_token_returns_401(client: httpx.AsyncClient) -> None:
    # Arrange — expired ten seconds ago
    token = _mint_token(exp_offset=-10)

    # Act
    response = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

    # Assert
    assert response.status_code == 401


async def test_get_me_wrong_audience_returns_401(client: httpx.AsyncClient) -> None:
    # Arrange — a non-end-user token (Supabase also issues anon/service_role audiences)
    token = _mint_token(aud="anon")

    # Act
    response = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

    # Assert
    assert response.status_code == 401


async def test_get_me_unconfigured_secret_returns_503(tmp_path: Path) -> None:
    # Arrange — the server has no JWT secret, so authentication is unavailable
    async with _build_client(None, tmp_path) as client:
        # Act
        response = await client.get("/api/me", headers={"Authorization": f"Bearer {_mint_token()}"})

    # Assert
    assert response.status_code == 503

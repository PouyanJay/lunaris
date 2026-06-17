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
from _auth import JWT_SECRET as _JWT_SECRET
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_runtime.logging import clear_correlation

# The local _mint_token keeps test-specific knobs (secret/exp/aud overrides for the negative-auth
# cases) the shared _auth.mint_token doesn't carry; the secret literal itself comes from _auth.
_TEST_USER_ID = "11111111-1111-1111-1111-111111111111"


def _mint_token(
    *,
    sub: str = _TEST_USER_ID,
    secret: str = _JWT_SECRET,
    exp_offset: int = 3600,
    aud: str = "authenticated",
    email: str | None = None,
) -> str:
    now = int(time.time())
    payload: dict[str, object] = {
        "sub": sub,
        "aud": aud,
        "role": "authenticated",
        "iat": now,
        "exp": now + exp_offset,
    }
    if email is not None:
        payload["email"] = email
    return jwt.encode(payload, secret, algorithm="HS256")


def _build_client(
    jwt_secret: str | None,
    tmp_path: Path,
    *,
    admin_emails: tuple[str, ...] = (),
) -> httpx.AsyncClient:
    clear_correlation()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        supabase_jwt_secret=jwt_secret,
        admin_emails=admin_emails,
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

    # Assert — no admin allowlist configured here, so the caller is not an admin.
    assert response.status_code == 200
    assert response.json() == {"userId": _TEST_USER_ID, "isAdmin": False}


async def test_get_me_reports_admin_for_an_allowlisted_email(tmp_path: Path) -> None:
    # Arrange — the caller's email is on the admin allowlist (case-insensitive).
    async with _build_client(_JWT_SECRET, tmp_path, admin_emails=("owner@lunaris.test",)) as client:
        token = _mint_token(email="Owner@Lunaris.TEST")

        # Act
        response = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

    # Assert
    assert response.status_code == 200
    assert response.json()["isAdmin"] is True


async def test_get_me_reports_non_admin_for_an_unlisted_email(tmp_path: Path) -> None:
    # Arrange — a valid user whose email is not on the allowlist.
    async with _build_client(_JWT_SECRET, tmp_path, admin_emails=("owner@lunaris.test",)) as client:
        token = _mint_token(email="someone-else@lunaris.test")

        # Act
        response = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

    # Assert
    assert response.status_code == 200
    assert response.json()["isAdmin"] is False


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


async def test_get_me_unsupported_alg_returns_401(client: httpx.AsyncClient) -> None:
    # Arrange — a valid signature but an algorithm no verifier is wired for (HS256-only here)
    now = int(time.time())
    payload = {"sub": _TEST_USER_ID, "aud": "authenticated", "iat": now, "exp": now + 3600}
    token = jwt.encode(payload, _JWT_SECRET, algorithm="HS512")

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

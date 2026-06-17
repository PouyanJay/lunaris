"""Signup invite-gate API: admin-only management of the shared invite code + a public status flag.

Hermetic (mirrors test_me_api / test_settings_api): mints HS256 tokens the API is configured to
trust, configures an admin email allowlist, and injects an in-memory gate store. Exercises the real
router → auth dependency → service → store path with no live Supabase. The Postgres
Before-User-Created hook (the actual signup enforcement) is verified separately at the DB layer.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from _auth import JWT_SECRET, auth_headers
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import get_signup_gate_store
from lunaris_api.signup_gate import InMemorySignupGateStore, SignupGate

ADMIN_EMAIL = "owner@lunaris.test"
ADMIN_USER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
MEMBER_USER = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _build_client(tmp_path: Path, store: InMemorySignupGateStore) -> httpx.AsyncClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        supabase_jwt_secret=JWT_SECRET,
        admin_emails=(ADMIN_EMAIL,),
    )
    app.dependency_overrides[get_signup_gate_store] = lambda: store
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def store() -> InMemorySignupGateStore:
    return InMemorySignupGateStore(SignupGate(invite_code="LUNARIS-BETA", enforced=True))


@pytest.fixture
async def client(
    tmp_path: Path, store: InMemorySignupGateStore
) -> AsyncIterator[httpx.AsyncClient]:
    async with _build_client(tmp_path, store) as http_client:
        yield http_client


def _admin() -> dict[str, str]:
    return auth_headers(ADMIN_USER, email=ADMIN_EMAIL)


def _member() -> dict[str, str]:
    return auth_headers(MEMBER_USER, email="member@lunaris.test")


# --- the public status flag (pre-login) ---------------------------------------------------------


async def test_public_status_returns_enforced_without_the_code(client: httpx.AsyncClient) -> None:
    # Act — no auth header; the public surface is unauthenticated by design.
    response = await client.get("/api/signup-gate")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body == {"enforced": True}
    # Never leak the plaintext code on the public surface.
    assert "LUNARIS-BETA" not in response.text
    assert "inviteCode" not in body
    # The request is correlated for log triangulation (CLAUDE.md "Correlation everywhere").
    assert response.headers["x-request-id"]


async def test_public_status_needs_no_auth(client: httpx.AsyncClient) -> None:
    # The sign-up screen calls this before anyone is logged in.
    assert (await client.get("/api/signup-gate")).status_code == 200


# --- the admin read surface ---------------------------------------------------------------------


async def test_admin_get_returns_the_code_for_an_admin(client: httpx.AsyncClient) -> None:
    # Act
    response = await client.get("/api/admin/signup-gate", headers=_admin())

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["inviteCode"] == "LUNARIS-BETA"
    assert body["enforced"] is True
    assert "updatedAt" in body
    assert response.headers["x-request-id"]


async def test_admin_get_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/admin/signup-gate")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_admin_get_forbidden_for_a_non_admin(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/admin/signup-gate", headers=_member())

    assert response.status_code == 403
    # A non-admin must not learn the code even via an error body.
    assert "LUNARIS-BETA" not in response.text


# --- the admin mutation surface -----------------------------------------------------------------


async def test_admin_put_rotates_the_code(client: httpx.AsyncClient) -> None:
    # Act
    updated = await client.put(
        "/api/admin/signup-gate", headers=_admin(), json={"inviteCode": "AUTUMN-2026"}
    )

    # Assert — the response carries the new code and a correlation id.
    assert updated.status_code == 200
    assert updated.json()["inviteCode"] == "AUTUMN-2026"
    assert updated.headers["x-request-id"]
    # And the rotation persists: a subsequent admin read returns it, enforced unchanged.
    after = (await client.get("/api/admin/signup-gate", headers=_admin())).json()
    assert after["inviteCode"] == "AUTUMN-2026"
    assert after["enforced"] is True


async def test_admin_put_toggles_enforcement_without_touching_the_code(
    client: httpx.AsyncClient,
) -> None:
    # Act
    response = await client.put(
        "/api/admin/signup-gate", headers=_admin(), json={"enforced": False}
    )

    # Assert — enforcement flips, the code is left untouched.
    assert response.status_code == 200
    body = response.json()
    assert body["enforced"] is False
    assert body["inviteCode"] == "LUNARIS-BETA"


async def test_admin_toggle_is_reflected_on_the_public_status(client: httpx.AsyncClient) -> None:
    # Arrange — an admin disables the gate.
    await client.put("/api/admin/signup-gate", headers=_admin(), json={"enforced": False})

    # Act / Assert — the public, pre-login status reflects it immediately (shared store).
    assert (await client.get("/api/signup-gate")).json() == {"enforced": False}


async def test_admin_put_empty_body_is_a_no_op(client: httpx.AsyncClient) -> None:
    # An empty change must not churn the gate (no spurious updated_at/updated_by write).
    response = await client.put("/api/admin/signup-gate", headers=_admin(), json={})

    assert response.status_code == 200
    body = response.json()
    assert body["inviteCode"] == "LUNARIS-BETA"
    assert body["enforced"] is True


async def test_admin_put_rejects_an_empty_code(client: httpx.AsyncClient) -> None:
    response = await client.put(
        "/api/admin/signup-gate", headers=_admin(), json={"inviteCode": "   "}
    )

    assert response.status_code == 400
    # The stored code is unchanged.
    after = (await client.get("/api/admin/signup-gate", headers=_admin())).json()
    assert after["inviteCode"] == "LUNARIS-BETA"


async def test_admin_put_forbidden_for_a_non_admin(client: httpx.AsyncClient) -> None:
    response = await client.put(
        "/api/admin/signup-gate", headers=_member(), json={"inviteCode": "HACKED"}
    )

    assert response.status_code == 403
    # The non-admin's write never landed.
    after = (await client.get("/api/admin/signup-gate", headers=_admin())).json()
    assert after["inviteCode"] == "LUNARIS-BETA"


async def test_admin_put_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.put("/api/admin/signup-gate", json={"inviteCode": "X"})

    assert response.status_code == 401

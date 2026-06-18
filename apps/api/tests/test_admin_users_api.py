"""Admin user-management API: list + delete Supabase Auth accounts, admin-gated.

Hermetic (mirrors test_signup_gate_api): HS256 tokens the API trusts, an admin allowlist, and an
in-memory user-directory double. Exercises the real router → admin dependency → directory path; the
Supabase GoTrue admin adapter is a thin wrapper verified separately.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from _auth import JWT_SECRET, auth_headers
from lunaris_api.admin_users import AdminAccount, InMemoryUserDirectory
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import get_user_directory

ADMIN_EMAIL = "owner@lunaris.test"
ADMIN_USER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
MEMBER_USER = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
OTHER_USER = "cccccccc-cccc-cccc-cccc-cccccccccccc"
_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def _seed() -> list[AdminAccount]:
    return [
        AdminAccount(ADMIN_USER, ADMIN_EMAIL, _NOW, _NOW, email_confirmed=True),
        AdminAccount(MEMBER_USER, "member@lunaris.test", _NOW, None, email_confirmed=False),
        AdminAccount(OTHER_USER, "someone@lunaris.test", _NOW, _NOW, email_confirmed=True),
    ]


def _build_client(tmp_path: Path, directory: InMemoryUserDirectory) -> httpx.AsyncClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        supabase_jwt_secret=JWT_SECRET,
        admin_emails=(ADMIN_EMAIL,),
    )
    app.dependency_overrides[get_user_directory] = lambda: directory
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def directory() -> InMemoryUserDirectory:
    return InMemoryUserDirectory(_seed())


@pytest.fixture
async def client(
    tmp_path: Path, directory: InMemoryUserDirectory
) -> AsyncIterator[httpx.AsyncClient]:
    async with _build_client(tmp_path, directory) as http_client:
        yield http_client


def _admin() -> dict[str, str]:
    return auth_headers(ADMIN_USER, email=ADMIN_EMAIL)


def _member() -> dict[str, str]:
    return auth_headers(MEMBER_USER, email="member@lunaris.test")


async def test_list_returns_accounts_with_admin_and_self_flags(client: httpx.AsyncClient) -> None:
    # Act
    response = await client.get("/api/admin/users", headers=_admin())

    # Assert
    assert response.status_code == 200
    accounts = {a["id"]: a for a in response.json()}
    assert set(accounts) == {ADMIN_USER, MEMBER_USER, OTHER_USER}
    # The requesting admin's own row is flagged admin + self.
    assert accounts[ADMIN_USER]["isAdmin"] is True
    assert accounts[ADMIN_USER]["isSelf"] is True
    # A plain member is neither, and its unconfirmed/never-signed-in status surfaces.
    assert accounts[MEMBER_USER]["isAdmin"] is False
    assert accounts[MEMBER_USER]["isSelf"] is False
    assert accounts[MEMBER_USER]["emailConfirmed"] is False
    assert accounts[MEMBER_USER]["lastSignInAt"] is None
    assert response.headers["x-request-id"]


async def test_list_unauthenticated_returns_401(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/admin/users")).status_code == 401


async def test_list_non_admin_returns_403(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/admin/users", headers=_member())).status_code == 403


async def test_delete_removes_the_account(client: httpx.AsyncClient) -> None:
    # Act
    deleted = await client.delete(f"/api/admin/users/{OTHER_USER}", headers=_admin())

    # Assert
    assert deleted.status_code == 204
    assert deleted.headers["x-request-id"]
    remaining = {a["id"] for a in (await client.get("/api/admin/users", headers=_admin())).json()}
    assert OTHER_USER not in remaining


async def test_delete_unknown_user_is_idempotent(client: httpx.AsyncClient) -> None:
    # A valid-but-absent id is a no-op 204 (the contract), not a 404, so delete races stay calm.
    absent = "dddddddd-dddd-dddd-dddd-dddddddddddd"
    response = await client.delete(f"/api/admin/users/{absent}", headers=_admin())
    assert response.status_code == 204


async def test_delete_malformed_id_is_422(client: httpx.AsyncClient) -> None:
    # A non-UUID path param is rejected at the boundary (422), never reaching the directory.
    response = await client.delete("/api/admin/users/not-a-uuid", headers=_admin())
    assert response.status_code == 422


async def test_admin_cannot_delete_their_own_account(client: httpx.AsyncClient) -> None:
    # Act — deleting self would lock the admin out mid-session.
    response = await client.delete(f"/api/admin/users/{ADMIN_USER}", headers=_admin())

    # Assert — rejected, and the account survives.
    assert response.status_code == 400
    remaining = {a["id"] for a in (await client.get("/api/admin/users", headers=_admin())).json()}
    assert ADMIN_USER in remaining


async def test_delete_requires_admin(client: httpx.AsyncClient) -> None:
    assert (await client.delete(f"/api/admin/users/{OTHER_USER}")).status_code == 401
    assert (
        await client.delete(f"/api/admin/users/{OTHER_USER}", headers=_member())
    ).status_code == 403
    # Neither anonymous nor a non-admin deleted anything.
    remaining = {a["id"] for a in (await client.get("/api/admin/users", headers=_admin())).json()}
    assert OTHER_USER in remaining
